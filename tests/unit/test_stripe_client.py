import types

import pytest

from src.billing.stripe_client import StripeClient, WebhookVerificationError


class _FakeStripeModule:
    """Doble de prueba del paquete `stripe`: sin red, con historial de llamadas."""

    def __init__(self, session_url="https://checkout.stripe.test/s1", event=None, fail_verification=False):
        self.api_key = None
        self.last_create_kwargs: dict | None = None
        self._session_url = session_url
        self._event = event if event is not None else {"type": "checkout.session.completed"}
        self._fail_verification = fail_verification
        self.checkout = types.SimpleNamespace(Session=types.SimpleNamespace(create=self._create))
        self.Webhook = types.SimpleNamespace(construct_event=self._construct_event)

    def _create(self, **kwargs):
        self.last_create_kwargs = kwargs
        return types.SimpleNamespace(url=self._session_url)

    def _construct_event(self, payload, sig_header, secret):
        if self._fail_verification:
            raise ValueError("firma inválida")
        return self._event


def test_requiere_secret_key() -> None:
    with pytest.raises(ValueError):
        StripeClient(secret_key="", stripe_module=_FakeStripeModule())


def test_create_checkout_session_manda_los_parametros_correctos() -> None:
    fake = _FakeStripeModule(session_url="https://checkout.stripe.test/abc")
    client = StripeClient(secret_key="sk_test_x", stripe_module=fake)

    url = client.create_checkout_session(
        price_id="price_123",
        success_url="https://panel.local/billing?ok=1",
        cancel_url="https://panel.local/billing?cancel=1",
    )

    assert url == "https://checkout.stripe.test/abc"
    assert fake.last_create_kwargs["mode"] == "subscription"
    assert fake.last_create_kwargs["line_items"] == [{"price": "price_123", "quantity": 1}]
    assert "customer_email" not in fake.last_create_kwargs
    assert fake.api_key == "sk_test_x"


def test_create_checkout_session_con_email() -> None:
    fake = _FakeStripeModule()
    client = StripeClient(secret_key="sk_test_x", stripe_module=fake)

    client.create_checkout_session(
        price_id="price_123",
        success_url="https://panel.local/billing",
        cancel_url="https://panel.local/billing",
        customer_email="vendedora@example.com",
    )

    assert fake.last_create_kwargs["customer_email"] == "vendedora@example.com"


def test_verify_webhook_event_devuelve_el_evento() -> None:
    fake = _FakeStripeModule(event={"type": "checkout.session.completed", "id": "evt_1"})
    client = StripeClient(secret_key="sk_test_x", webhook_secret="whsec_x", stripe_module=fake)

    event = client.verify_webhook_event(b"payload", "sig_header")

    assert event["id"] == "evt_1"


def test_verify_webhook_event_sin_secret_configurado_lanza_error() -> None:
    fake = _FakeStripeModule()
    client = StripeClient(secret_key="sk_test_x", stripe_module=fake)  # sin webhook_secret

    with pytest.raises(WebhookVerificationError):
        client.verify_webhook_event(b"payload", "sig_header")


def test_verify_webhook_event_firma_invalida_lanza_error() -> None:
    fake = _FakeStripeModule(fail_verification=True)
    client = StripeClient(secret_key="sk_test_x", webhook_secret="whsec_x", stripe_module=fake)

    with pytest.raises(WebhookVerificationError):
        client.verify_webhook_event(b"payload", "sig_header-malo")
