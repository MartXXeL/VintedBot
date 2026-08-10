from fastapi.testclient import TestClient

from src.core.security import hash_password
from src.core.settings import Settings
from src.storage import accounts_store, listings_store, users_store
from src.storage.db import init_db
from src.ui.app import create_app
from src.vinted.models import Listing, VintedAccount

TEST_EMAIL = "admin@example.com"
TEST_PASSWORD = "una-contraseña-de-prueba"


class _FakeStripeClient:
    def __init__(self, checkout_url=None, raise_on_checkout=False):
        self.checkout_url = checkout_url or "https://checkout.stripe.test/session-abc"
        self.raise_on_checkout = raise_on_checkout
        self.create_checkout_calls: list[dict] = []
        self.verify_calls: list[tuple[bytes, str]] = []
        self.event_to_return = {"type": "checkout.session.completed"}
        self.raise_on_verify = False

    def create_checkout_session(self, price_id, success_url, cancel_url, customer_email=None):
        if self.raise_on_checkout:
            raise RuntimeError("Stripe no responde")
        self.create_checkout_calls.append(
            {"price_id": price_id, "success_url": success_url, "cancel_url": cancel_url}
        )
        return self.checkout_url

    def verify_webhook_event(self, payload, sig_header):
        from src.billing.stripe_client import WebhookVerificationError

        self.verify_calls.append((payload, sig_header))
        if self.raise_on_verify:
            raise WebhookVerificationError("firma inválida")
        return self.event_to_return


def _make_client(tmp_path, fake_stripe_client=None, **settings_kwargs):
    settings = Settings(database_path=tmp_path / "test.db", env_path=tmp_path / ".env", **settings_kwargs)
    init_db(settings.database_path)
    users_store.create_user(str(settings.database_path), TEST_EMAIL, hash_password(TEST_PASSWORD), role="admin")
    app = create_app(
        settings,
        start_worker=False,
        stripe_client_factory=(lambda s: fake_stripe_client) if fake_stripe_client else None,
    )
    client = TestClient(app)
    client.post("/login", data={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    return client, settings


def test_ver_suscripcion_sin_stripe_configurado(tmp_path) -> None:
    client, _settings = _make_client(tmp_path)

    response = client.get("/billing")

    assert response.status_code == 200
    assert "Stripe no está configurado" in response.text
    assert "Suscribirse" not in response.text


def test_ver_suscripcion_muestra_el_plan_recomendado(tmp_path) -> None:
    client, settings = _make_client(tmp_path)
    # El uso de la suscripción es siempre el propio, aunque quien mire sea
    # admin: hay que darle un dueño a la cuenta para que cuente.
    admin = users_store.get_user_by_email(str(settings.database_path), TEST_EMAIL)
    account = accounts_store.create_account(
        str(settings.database_path), VintedAccount(label="X"), owner_user_id=admin.id
    )
    listings_store.create_listing(str(settings.database_path), Listing(account_id=account.id))

    response = client.get("/billing")

    assert "Recomendado" in response.text
    assert "Starter" in response.text


def test_ver_suscripcion_con_stripe_configurado_muestra_boton(tmp_path) -> None:
    client, _settings = _make_client(tmp_path, stripe_secret_key="sk_test_x")

    response = client.get("/billing")

    assert "Suscribirse" in response.text


def test_checkout_sin_price_id_configurado_da_error(tmp_path) -> None:
    fake_stripe = _FakeStripeClient()
    client, _settings = _make_client(tmp_path, fake_stripe, stripe_secret_key="sk_test_x")

    response = client.post("/billing/checkout/starter", follow_redirects=False)

    assert "error=" in response.headers["location"]
    assert fake_stripe.create_checkout_calls == []


def test_checkout_redirige_a_stripe(tmp_path) -> None:
    fake_stripe = _FakeStripeClient(checkout_url="https://checkout.stripe.test/xyz")
    client, _settings = _make_client(
        tmp_path, fake_stripe, stripe_secret_key="sk_test_x", stripe_price_starter_id="price_starter_1"
    )

    response = client.post("/billing/checkout/starter", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "https://checkout.stripe.test/xyz"
    assert fake_stripe.create_checkout_calls[0]["price_id"] == "price_starter_1"


def test_checkout_plan_desconocido_da_error(tmp_path) -> None:
    client, _settings = _make_client(tmp_path, stripe_secret_key="sk_test_x")

    response = client.post("/billing/checkout/no-existe", follow_redirects=False)

    assert "error=" in response.headers["location"]


def test_checkout_sin_stripe_configurado_da_error(tmp_path) -> None:
    client, _settings = _make_client(tmp_path)

    response = client.post("/billing/checkout/starter", follow_redirects=False)

    assert "error=" in response.headers["location"]


def test_checkout_fallo_de_stripe_da_error_amigable(tmp_path) -> None:
    fake_stripe = _FakeStripeClient(raise_on_checkout=True)
    client, _settings = _make_client(
        tmp_path, fake_stripe, stripe_secret_key="sk_test_x", stripe_price_starter_id="price_1"
    )

    response = client.post("/billing/checkout/starter", follow_redirects=False)

    assert "error=" in response.headers["location"]


# --------------------------------------------------------------------------- #
#  Webhook — sin login, autenticado por firma
# --------------------------------------------------------------------------- #


def test_webhook_no_exige_sesion(tmp_path) -> None:
    fake_stripe = _FakeStripeClient()
    settings = Settings(
        database_path=tmp_path / "test.db",
        stripe_secret_key="sk_test_x",
        stripe_webhook_secret="whsec_x",
    )
    from src.ui.app import create_app as _create_app

    app = _create_app(settings, start_worker=False, stripe_client_factory=lambda s: fake_stripe)
    client = TestClient(app)  # sin login

    response = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "sig123"})

    assert response.status_code == 200
    assert fake_stripe.verify_calls == [(b"{}", "sig123")]


def test_webhook_firma_invalida_da_400(tmp_path) -> None:
    fake_stripe = _FakeStripeClient()
    fake_stripe.raise_on_verify = True
    settings = Settings(
        database_path=tmp_path / "test.db",
        stripe_secret_key="sk_test_x",
        stripe_webhook_secret="whsec_x",
    )
    from src.ui.app import create_app as _create_app

    app = _create_app(settings, start_worker=False, stripe_client_factory=lambda s: fake_stripe)
    client = TestClient(app)

    response = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "sig-malo"})

    assert response.status_code == 400


def test_webhook_sin_stripe_configurado_da_404(tmp_path) -> None:
    client, _settings = _make_client(tmp_path)  # sin stripe_secret_key ni webhook_secret

    response = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "sig"})

    assert response.status_code == 404
