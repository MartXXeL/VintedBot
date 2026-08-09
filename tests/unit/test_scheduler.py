import asyncio
from datetime import datetime, timedelta

import httpx
import pytest

from src.ai.providers import MockAIProvider
from src.core.settings import RateLimitSettings, Settings
from src.storage import accounts_store, actions_store, listings_store, offers_store
from src.storage.db import init_db
from src.vinted import endpoints
from src.vinted.api_client import VintedApiClient
from src.vinted.models import Listing, Offer, VintedAccount
from src.worker.scheduler import (
    publish_listing_now,
    publish_listing_via_api,
    run_account_cycle,
    run_forever,
    send_offer_reply_now,
)


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

    # `now` explícito y separado más que `min_seconds`: lo que se prueba aquí
    # es la deduplicación, no el limitador de ritmo — con el reloj real, dos
    # llamadas seguidas caen casi siempre dentro de la cadencia mínima y la
    # segunda da "rate_limited" en vez de "idle" (más probable aún en un
    # runner rápido/en CI que en una máquina de desarrollo más lenta).
    first_now = datetime.now()
    second_now = first_now + timedelta(seconds=SETTINGS.rate_limit.min_seconds + 1)

    first = await run_account_cycle(db_path, account, client, MockAIProvider(), SETTINGS, now=first_now)
    second = await run_account_cycle(db_path, account, client, MockAIProvider(), SETTINGS, now=second_now)

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
async def test_sin_auto_reply_offers_prepara_pero_no_manda_nada_a_vinted(tmp_path) -> None:
    db_path, account = _setup(tmp_path, auto_reply_offers=False)
    listings_store.create_listing(
        db_path, Listing(account_id=account.id, price=30.0, min_price=20.0, status="published", vinted_item_id="item-9")
    )
    conversations = [
        {"id": "conv-1", "item": {"id": "item-9"}, "offer": {"id": "offer-1", "amount": 30, "status": "pending"}}
    ]
    client = _FakeSessionClient(conversations=conversations)

    # Sin auto_reply_offers, la oferta se decide y se redacta igualmente (para
    # que espere ya lista en el panel) pero se queda 'pending': nada se manda
    # a Vinted sin aprobación humana, ni cuenta para el límite diario.
    result = await run_account_cycle(db_path, account, client, MockAIProvider(), SETTINGS)

    assert result.action == "processed_offer"
    assert client.accepted == []
    assert client.sent_messages == []
    offer = offers_store.list_offers(db_path, account_id=account.id)[0]
    assert offer.status == "pending"
    assert offer.decision == "accept"
    assert offer.reply_text


@pytest.mark.asyncio
async def test_publish_listing_now_publica_si_hay_ritmo(tmp_path) -> None:
    db_path, account = _setup(tmp_path, auto_publish=False)  # el botón manual no depende del flag
    photo = tmp_path / "foto.jpg"
    photo.write_bytes(b"\xff\xd8\xff-jpeg-falso")
    listing = listings_store.create_listing(
        db_path,
        Listing(account_id=account.id, title="Zapatillas", price=40.0, min_price=25.0, photo_paths=[str(photo)]),
    )
    client = _FakeSessionClient(publish_result={"id": "item-55"})

    blocked = await publish_listing_now(db_path, account, listing, client, SETTINGS)

    assert blocked is None
    published = listings_store.get_listing(db_path, listing.id)
    assert published.status == "published"
    assert published.vinted_item_id == "item-55"


@pytest.mark.asyncio
async def test_publish_listing_now_respeta_el_limite_diario(tmp_path) -> None:
    db_path, account = _setup(tmp_path)
    for _ in range(50):
        actions_store.record_action(db_path, account.id, "publish_listing")
    listing = listings_store.create_listing(
        db_path, Listing(account_id=account.id, title="X", price=10.0, min_price=5.0, photo_paths=["a.jpg"])
    )
    client = _FakeSessionClient()

    blocked = await publish_listing_now(db_path, account, listing, client, SETTINGS)

    assert blocked is not None
    assert not blocked.allowed
    assert client.published_payloads == []


def _fake_api_client(handler) -> VintedApiClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(base_url="https://api.vinted.test", transport=transport)
    return VintedApiClient(
        base_url="https://api.vinted.test", client_id="cid", client_secret="secret", http_client=http_client
    )


@pytest.mark.asyncio
async def test_publish_listing_via_api_publica_con_fotos_en_base64(tmp_path) -> None:
    db_path, account = _setup(tmp_path)
    photo = tmp_path / "foto.jpg"
    photo.write_bytes(b"\xff\xd8\xff-jpeg-falso")
    listing = listings_store.create_listing(
        db_path,
        Listing(account_id=account.id, title="Bolso", price=25.0, min_price=15.0, photo_paths=[str(photo)]),
    )

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == endpoints.OAUTH_TOKEN:
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        import json

        body = json.loads(request.content)
        assert body["title"] == "Bolso"
        assert len(body["photos_base64"]) == 1
        return httpx.Response(201, json={"id": "official-item-1"})

    api_client = _fake_api_client(handler)

    blocked = await publish_listing_via_api(db_path, account, listing, api_client, SETTINGS)

    assert blocked is None
    assert calls == [endpoints.OAUTH_TOKEN, endpoints.API_ITEMS]
    published = listings_store.get_listing(db_path, listing.id)
    assert published.status == "published"
    assert published.vinted_item_id == "official-item-1"


@pytest.mark.asyncio
async def test_publish_listing_via_api_respeta_el_limite_de_ritmo(tmp_path) -> None:
    db_path, account = _setup(tmp_path)
    for _ in range(50):
        actions_store.record_action(db_path, account.id, "publish_listing")
    listing = listings_store.create_listing(
        db_path, Listing(account_id=account.id, title="X", price=10.0, min_price=5.0)
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no debería llamar a Vinted si el ritmo lo bloquea")

    api_client = _fake_api_client(handler)

    blocked = await publish_listing_via_api(db_path, account, listing, api_client, SETTINGS)

    assert blocked is not None
    assert not blocked.allowed


@pytest.mark.asyncio
async def test_send_offer_reply_now_manda_la_decision_ya_tomada(tmp_path) -> None:
    db_path, account = _setup(tmp_path, auto_reply_offers=False)
    listing = listings_store.create_listing(
        db_path, Listing(account_id=account.id, price=30.0, min_price=20.0, status="published")
    )
    offer = offers_store.create_offer(
        db_path,
        Offer(
            listing_id=listing.id,
            account_id=account.id,
            offer_amount=30.0,
            external_conversation_id="conv-9",
            external_offer_id="offer-9",
        ),
    )
    offers_store.set_offer_decision(db_path, offer.id, "accept", None, "¡Trato hecho!")
    offer = offers_store.get_offer(db_path, offer.id)
    client = _FakeSessionClient()

    blocked = await send_offer_reply_now(db_path, account, offer, client, SETTINGS)

    assert blocked is None
    assert client.accepted == [("conv-9", "offer-9")]
    assert client.sent_messages == [("conv-9", "¡Trato hecho!")]
    assert offers_store.get_offer(db_path, offer.id).status == "sent"


@pytest.mark.asyncio
async def test_send_offer_reply_now_sin_decision_todavia_lanza_error(tmp_path) -> None:
    db_path, account = _setup(tmp_path)
    listing = listings_store.create_listing(db_path, Listing(account_id=account.id, price=30.0, min_price=20.0))
    offer = offers_store.create_offer(
        db_path, Offer(listing_id=listing.id, account_id=account.id, offer_amount=25.0)
    )

    with pytest.raises(ValueError):
        await send_offer_reply_now(db_path, account, offer, _FakeSessionClient(), SETTINGS)


@pytest.mark.asyncio
async def test_run_forever_termina_si_el_stop_event_ya_esta_activo(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    stop_event = asyncio.Event()
    stop_event.set()

    await asyncio.wait_for(
        run_forever(db_path, SETTINGS, MockAIProvider(), stop_event=stop_event), timeout=2
    )
