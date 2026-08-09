import httpx
import pytest

from src.vinted import endpoints
from src.vinted.errors import VintedApiError
from src.vinted.session_client import VintedSessionClient, parse_pending_offers


def _client_with_handler(handler) -> VintedSessionClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(
        base_url="https://www.vinted.es",
        headers={"Cookie": "access_token_web=abc"},
        transport=transport,
    )
    return VintedSessionClient(domain="www.vinted.es", session_cookie="access_token_web=abc", http_client=http_client)


def test_requiere_cookie_de_sesion() -> None:
    with pytest.raises(ValueError):
        VintedSessionClient(domain="www.vinted.es", session_cookie="")


@pytest.mark.asyncio
async def test_manda_la_cookie_en_cada_peticion() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["cookie"] == "access_token_web=abc"
        return httpx.Response(200, json={"id": "42", "login": "revendedor1"})

    client = _client_with_handler(handler)
    user = await client.get_user("42")
    assert user["login"] == "revendedor1"


@pytest.mark.asyncio
async def test_upload_photo_devuelve_el_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == endpoints.SESSION_PHOTOS
        assert request.method == "POST"
        return httpx.Response(201, json={"id": 999})

    client = _client_with_handler(handler)
    photo_id = await client.upload_photo(b"\xff\xd8\xff-jpeg-falso")
    assert photo_id == "999"


@pytest.mark.asyncio
async def test_publish_listing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == endpoints.SESSION_ITEMS
        return httpx.Response(201, json={"id": "item-1", "title": "Camiseta"})

    client = _client_with_handler(handler)
    result = await client.publish_listing({"title": "Camiseta", "photo_ids": ["999"]})
    assert result["id"] == "item-1"


@pytest.mark.asyncio
async def test_send_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == endpoints.SESSION_CONVERSATION_MESSAGES.format(conversation_id="7")
        return httpx.Response(201, json={"ok": True})

    client = _client_with_handler(handler)
    result = await client.send_message("7", "¡Gracias por tu oferta!")
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_accept_reject_counter_offer() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"status": "ok"})

    client = _client_with_handler(handler)
    await client.accept_offer("7", "o1")
    await client.reject_offer("7", "o2")
    await client.counter_offer("7", "o3", amount=15.0)

    assert calls == [
        endpoints.SESSION_OFFER_ACCEPT.format(conversation_id="7", offer_id="o1"),
        endpoints.SESSION_OFFER_REJECT.format(conversation_id="7", offer_id="o2"),
        endpoints.SESSION_OFFER_COUNTER.format(conversation_id="7", offer_id="o3"),
    ]


@pytest.mark.asyncio
async def test_error_de_sesion_expirada_lanza_vinted_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="session expired")

    client = _client_with_handler(handler)
    with pytest.raises(VintedApiError) as exc_info:
        await client.list_conversations()
    assert exc_info.value.status_code == 401


# --------------------------------------------------------------------------- #
#  parse_pending_offers (función pura, sin red)
# --------------------------------------------------------------------------- #


def test_parse_pending_offers_extrae_solo_las_pendientes() -> None:
    conversations = [
        {
            "id": "c1",
            "buyer": {"login": "compradora1"},
            "offer": {"id": "o1", "amount": 12.5, "status": "pending"},
        },
        {"id": "c2", "offer": {"id": "o2", "amount": 5, "status": "accepted"}},
        {"id": "c3"},  # sin oferta
    ]

    pending = parse_pending_offers(conversations)

    assert pending == [
        {"conversation_id": "c1", "offer_id": "o1", "amount": 12.5, "buyer_name": "compradora1"}
    ]


def test_parse_pending_offers_lista_vacia() -> None:
    assert parse_pending_offers([]) == []


def test_parse_pending_offers_conversacion_malformada_no_revienta() -> None:
    conversations = [{"id": "raro", "offer": {"status": "pending"}}]
    pending = parse_pending_offers(conversations)
    assert pending[0]["offer_id"] is None
