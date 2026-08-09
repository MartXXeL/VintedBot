import asyncio
from datetime import datetime

import pytest

from src.ai.providers import MockAIProvider
from src.core.settings import RateLimitSettings, Settings
from src.storage import accounts_store, actions_store, listings_store, offers_store
from src.storage.db import init_db
from src.vinted.models import Listing, VintedAccount
from src.worker.scheduler import run_account_cycle, run_forever


class _FakeSessionClient:
    """Doble de prueba de VintedSessionClient: sin red, con historial de llamadas."""

    def __init__(self, conversations=None, publish_result=None):
        self.conversations = conversations or []
        self.publish_result = publish_result or {"id": "item-nuevo"}
        self.uploaded_photos: list[bytes] = []
        self.published_payloads: list[dict] = []
        self.sent_messages: list[tuple[str, str]] = []
        self.accepted: list[tuple[str, str]] = []
        self.rejected: list[tuple[str, str]] = []
        self.countered: list[tuple[str, str, float]] = []

    async def upload_photo(self, photo_bytes: bytes, filename: str = "foto.jpg") -> str:
        self.uploaded_photos.append(photo_bytes)
        return f"photo-{len(self.uploaded_photos)}"

    async def publish_listing(self, payload: dict) -> dict:
        self.published_payloads.append(payload)
        return self.publish_result

    async def list_conversations(self) -> list[dict]:
        return self.conversations

    async def send_message(self, conversation_id: str, text: str) -> dict:
        self.sent_messages.append((conversation_id, text))
        return {"ok": True}

    async def accept_offer(self, conversation_id: str, offer_id: str) -> dict:
        self.accepted.append((conversation_id, offer_id))
        return {"ok": True}

    async def reject_offer(self, conversation_id: str, offer_id: str) -> dict:
        self.rejected.append((conversation_id, offer_id))
        return {"ok": True}

    async def counter_offer(self, conversation_id: str, offer_id: str, amount: float) -> dict:
        self.countered.append((conversation_id, offer_id, amount))
        return {"ok": True}


def _setup(tmp_path, **account_kwargs):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    account = accounts_store.create_account(
        db_path, VintedAccount(label="X", connection_mode="session", status="connected", **account_kwargs)
    )
    return db_path, account


SETTINGS = Settings(rate_limit=RateLimitSettings(min_seconds=1, max_seconds=2, max_actions_per_day=50))


@pytest.mark.asyncio
async def test_idle_si_no_hay_automatizacion_activada(tmp_path) -> None:
    db_path, account = _setup(tmp_path, auto_publish=False, auto_reply_offers=False)
    client = _FakeSessionClient()

    result = await run_account_cycle(db_path, account, client, MockAIProvider(), SETTINGS)

    assert result.action == "idle"
    assert client.published_payloads == []
    assert client.sent_messages == []


@pytest.mark.asyncio
async def test_bloqueado_por_el_limitador_de_ritmo(tmp_path) -> None:
    db_path, account = _setup(tmp_path, auto_publish=True)
    now = datetime.now()
    for _ in range(50):
        actions_store.record_action(db_path, account.id, "publish_listing")

    result = await run_account_cycle(db_path, account, _FakeSessionClient(), MockAIProvider(), SETTINGS, now=now)

    assert result.action == "rate_limited"


@pytest.mark.asyncio
async def test_publica_el_siguiente_borrador_listo(tmp_path) -> None:
    db_path, account = _setup(tmp_path, auto_publish=True)
    photo = tmp_path / "foto.jpg"
    photo.write_bytes(b"\xff\xd8\xff-contenido-jpeg-falso")
    listings_store.create_listing(
        db_path,
        Listing(
            account_id=account.id,
            title="Camiseta Nike",
            price=20.0,
            min_price=15.0,
            photo_paths=[str(photo)],
            status="draft",
        ),
    )
    client = _FakeSessionClient(publish_result={"id": "item-123"})

    result = await run_account_cycle(db_path, account, client, MockAIProvider(), SETTINGS)

    assert result.action == "published_listing"
    assert len(client.uploaded_photos) == 1
    assert client.published_payloads[0]["title"] == "Camiseta Nike"
    published = listings_store.list_listings(db_path, account_id=account.id, status="published")
    assert published[0].vinted_item_id == "item-123"


@pytest.mark.asyncio
async def test_no_publica_borradores_incompletos(tmp_path) -> None:
    db_path, account = _setup(tmp_path, auto_publish=True)
    # Sin min_price: no se puede negociar con seguridad, así que tampoco se publica.
    listings_store.create_listing(
        db_path, Listing(account_id=account.id, title="X", photo_paths=["a.jpg"], status="draft")
    )
    client = _FakeSessionClient()

    result = await run_account_cycle(db_path, account, client, MockAIProvider(), SETTINGS)

    assert result.action == "idle"
    assert client.published_payloads == []


@pytest.mark.asyncio
async def test_procesa_una_oferta_pendiente_y_calcula_la_decision(tmp_path) -> None:
    db_path, account = _setup(tmp_path, auto_reply_offers=True)
    listing = listings_store.create_listing(
        db_path, Listing(account_id=account.id, price=30.0, min_price=20.0, status="published", vinted_item_id="item-9")
    )
    conversations = [
        {
            "id": "conv-1",
            "buyer": {"login": "compradora1"},
            "item": {"id": "item-9"},
            "offer": {"id": "offer-1", "amount": 10, "status": "pending"},  # ratio 10/20 = 0.50 -> counter
        }
    ]
    client = _FakeSessionClient(conversations=conversations)

    result = await run_account_cycle(db_path, account, client, MockAIProvider(), SETTINGS)

    assert result.action == "processed_offer"
    offers = offers_store.list_offers(db_path, account_id=account.id)
    assert len(offers) == 1
    assert offers[0].decision == "counter"
    assert offers[0].buyer_name == "compradora1"
    assert listing.id == offers[0].listing_id


@pytest.mark.asyncio
async def test_oferta_duplicada_no_se_reimporta(tmp_path) -> None:
    db_path, account = _setup(tmp_path, auto_reply_offers=True)
    listings_store.create_listing(
        db_path, Listing(account_id=account.id, price=30.0, min_price=20.0, status="published", vinted_item_id="item-9")
    )
    conversations = [
        {
            "id": "conv-1",
            "item": {"id": "item-9"},
            "offer": {"id": "offer-dup", "amount": 25, "status": "pending"},
        }
    ]
    client = _FakeSessionClient(conversations=conversations)

    first = await run_account_cycle(db_path, account, client, MockAIProvider(), SETTINGS)
    second = await run_account_cycle(db_path, account, client, MockAIProvider(), SETTINGS)

    assert first.action == "processed_offer"
    assert second.action == "idle"  # ya no queda ninguna oferta nueva que procesar
    assert len(offers_store.list_offers(db_path, account_id=account.id)) == 1


@pytest.mark.asyncio
async def test_oferta_sin_anuncio_interno_reconocible_se_ignora(tmp_path) -> None:
    db_path, account = _setup(tmp_path, auto_reply_offers=True)
    conversations = [
        {"id": "conv-1", "item": {"id": "item-desconocido"}, "offer": {"id": "o1", "amount": 5, "status": "pending"}}
    ]
    client = _FakeSessionClient(conversations=conversations)

    result = await run_account_cycle(db_path, account, client, MockAIProvider(), SETTINGS)

    assert result.action == "idle"
    assert offers_store.list_offers(db_path, account_id=account.id) == []


@pytest.mark.asyncio
async def test_auto_reply_offers_manda_la_decision_a_vinted(tmp_path) -> None:
    db_path, account = _setup(tmp_path, auto_reply_offers=True)
    listings_store.create_listing(
        db_path, Listing(account_id=account.id, price=30.0, min_price=20.0, status="published", vinted_item_id="item-9")
    )
    conversations = [
        {"id": "conv-1", "item": {"id": "item-9"}, "offer": {"id": "offer-accept", "amount": 30, "status": "pending"}}
    ]
    client = _FakeSessionClient(conversations=conversations)

    result = await run_account_cycle(db_path, account, client, MockAIProvider(), SETTINGS)

    assert result.action == "processed_offer"
    assert client.accepted == [("conv-1", "offer-accept")]
    assert len(client.sent_messages) == 1
    offer = offers_store.list_offers(db_path, account_id=account.id)[0]
    assert offer.status == "sent"


@pytest.mark.asyncio
async def test_sin_auto_reply_offers_no_manda_nada_a_vinted(tmp_path) -> None:
    db_path, account = _setup(tmp_path, auto_reply_offers=False)
    listings_store.create_listing(
        db_path, Listing(account_id=account.id, price=30.0, min_price=20.0, status="published", vinted_item_id="item-9")
    )
    conversations = [
        {"id": "conv-1", "item": {"id": "item-9"}, "offer": {"id": "offer-1", "amount": 30, "status": "pending"}}
    ]
    client = _FakeSessionClient(conversations=conversations)

    # auto_reply_offers en False hace que run_account_cycle ni entre en la rama
    # de ofertas: se queda "idle" a propósito (nadie pidió automatizar esto).
    result = await run_account_cycle(db_path, account, client, MockAIProvider(), SETTINGS)

    assert result.action == "idle"
    assert client.accepted == []
    assert client.sent_messages == []


@pytest.mark.asyncio
async def test_run_forever_termina_si_el_stop_event_ya_esta_activo(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    stop_event = asyncio.Event()
    stop_event.set()

    await asyncio.wait_for(
        run_forever(db_path, SETTINGS, MockAIProvider(), stop_event=stop_event), timeout=2
    )
