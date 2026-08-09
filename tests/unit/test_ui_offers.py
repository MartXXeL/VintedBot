from fastapi.testclient import TestClient

from src.core.security import hash_password
from src.core.settings import Settings
from src.storage import accounts_store, listings_store, offers_store
from src.ui.app import create_app
from src.vinted.models import Listing, Offer, VintedAccount

TEST_PASSWORD = "una-contraseña-de-prueba"


class _FakeSessionClient:
    def __init__(self):
        self.accepted = []
        self.sent_messages = []
        self.closed = False

    async def accept_offer(self, conversation_id: str, offer_id: str) -> dict:
        self.accepted.append((conversation_id, offer_id))
        return {"ok": True}

    async def send_message(self, conversation_id: str, text: str) -> dict:
        self.sent_messages.append((conversation_id, text))
        return {"ok": True}

    async def aclose(self) -> None:
        self.closed = True


def _make_client(tmp_path, fake_session_client=None):
    settings = Settings(
        database_path=tmp_path / "test.db",
        env_path=tmp_path / ".env",
        dashboard_password_hash=hash_password(TEST_PASSWORD),
    )
    app = create_app(
        settings,
        start_worker=False,
        session_client_factory=(lambda domain, cookie: fake_session_client) if fake_session_client else None,
    )
    client = TestClient(app)
    client.post("/login", data={"password": TEST_PASSWORD})
    return client, settings


def _setup_offer(db_path: str, *, with_cookie: bool = True) -> tuple[int, int]:
    account = accounts_store.create_account(
        db_path, VintedAccount(label="X"), session_cookie="access_token_web=abc" if with_cookie else None
    )
    listing = listings_store.create_listing(
        db_path, Listing(account_id=account.id, title="Camiseta", price=30.0, min_price=20.0)
    )
    offer = offers_store.create_offer(
        db_path,
        Offer(
            listing_id=listing.id,
            account_id=account.id,
            offer_amount=30.0,
            external_conversation_id="conv-1",
            external_offer_id="offer-1",
        ),
    )
    offers_store.set_offer_decision(db_path, offer.id, "accept", None, "¡Trato hecho!")
    return account.id, offer.id


def test_lista_vacia_sin_ofertas(tmp_path) -> None:
    client, _settings = _make_client(tmp_path)
    response = client.get("/offers")
    assert response.status_code == 200
    assert "No hay ninguna oferta" in response.text


def test_lista_muestra_la_oferta_pendiente(tmp_path) -> None:
    client, settings = _make_client(tmp_path)
    _setup_offer(str(settings.database_path))

    response = client.get("/offers")

    assert "Camiseta" in response.text
    assert "¡Trato hecho!" in response.text


def test_aprobar_oferta_la_manda_y_la_marca_enviada(tmp_path) -> None:
    fake_client = _FakeSessionClient()
    client, settings = _make_client(tmp_path, fake_session_client=fake_client)
    _account_id, offer_id = _setup_offer(str(settings.database_path))

    response = client.post(f"/offers/{offer_id}/approve", follow_redirects=False)

    assert "ok=" in response.headers["location"]
    assert fake_client.accepted == [("conv-1", "offer-1")]
    assert fake_client.closed is True
    assert offers_store.get_offer(str(settings.database_path), offer_id).status == "sent"


def test_aprobar_oferta_inexistente_da_error(tmp_path) -> None:
    client, _settings = _make_client(tmp_path)
    response = client.post("/offers/999/approve", follow_redirects=False)
    assert "error=" in response.headers["location"]


def test_aprobar_sin_sesion_guardada_da_error(tmp_path) -> None:
    client, settings = _make_client(tmp_path)
    _account_id, offer_id = _setup_offer(str(settings.database_path), with_cookie=False)

    response = client.post(f"/offers/{offer_id}/approve", follow_redirects=False)

    assert "error=" in response.headers["location"]


def test_descartar_oferta(tmp_path) -> None:
    client, settings = _make_client(tmp_path)
    _account_id, offer_id = _setup_offer(str(settings.database_path))

    response = client.post(f"/offers/{offer_id}/discard", follow_redirects=False)

    assert "ok=" in response.headers["location"]
    assert offers_store.get_offer(str(settings.database_path), offer_id).status == "discarded"
    # Una vez descartada, ya no debe aparecer en la lista de pendientes.
    assert "Camiseta" not in client.get("/offers").text


def test_descartar_oferta_inexistente_da_error(tmp_path) -> None:
    client, _settings = _make_client(tmp_path)
    response = client.post("/offers/999/discard", follow_redirects=False)
    assert "error=" in response.headers["location"]
