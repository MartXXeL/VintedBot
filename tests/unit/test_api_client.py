import httpx
import pytest

from src.vinted import endpoints
from src.vinted.api_client import VintedApiClient
from src.vinted.errors import VintedApiError


def _client_with_handler(handler) -> VintedApiClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(base_url="https://api.vinted.test", transport=transport)
    return VintedApiClient(
        base_url="https://api.vinted.test",
        client_id="cid",
        client_secret="secret",
        http_client=http_client,
    )


def test_requiere_client_id_y_secret() -> None:
    with pytest.raises(ValueError):
        VintedApiClient(base_url="https://api.vinted.test", client_id="", client_secret="")


@pytest.mark.asyncio
async def test_create_item_pide_token_y_luego_crea(monkeypatch) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == endpoints.OAUTH_TOKEN:
            return httpx.Response(200, json={"access_token": "tok-123", "expires_in": 3600})
        if request.url.path == endpoints.API_ITEMS:
            assert request.headers["authorization"] == "Bearer tok-123"
            return httpx.Response(201, json={"id": "item-1"})
        raise AssertionError(f"Ruta inesperada: {request.url.path}")

    client = _client_with_handler(handler)
    result = await client.create_item({"title": "Camiseta"})

    assert result == {"id": "item-1"}
    assert calls == [endpoints.OAUTH_TOKEN, endpoints.API_ITEMS]


@pytest.mark.asyncio
async def test_el_token_se_reutiliza_sin_pedirlo_dos_veces() -> None:
    token_requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_requests
        if request.url.path == endpoints.OAUTH_TOKEN:
            token_requests += 1
            return httpx.Response(200, json={"access_token": "tok-456", "expires_in": 3600})
        return httpx.Response(200, json={"orders": []})

    client = _client_with_handler(handler)
    await client.list_orders()
    await client.list_orders()

    assert token_requests == 1


@pytest.mark.asyncio
async def test_error_http_lanza_vinted_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == endpoints.OAUTH_TOKEN:
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return httpx.Response(403, text="forbidden")

    client = _client_with_handler(handler)
    with pytest.raises(VintedApiError) as exc_info:
        await client.create_item({})

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_update_item_usa_patch_con_el_id_en_la_ruta() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == endpoints.OAUTH_TOKEN:
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        assert request.method == "PATCH"
        assert request.url.path == "/v2/items/item-99"
        return httpx.Response(200, json={"id": "item-99", "price": "15.0"})

    client = _client_with_handler(handler)
    result = await client.update_item("item-99", {"price": "15.0"})
    assert result["id"] == "item-99"


@pytest.mark.asyncio
async def test_register_webhook() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == endpoints.OAUTH_TOKEN:
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        assert request.url.path == endpoints.API_WEBHOOKS
        return httpx.Response(201, json={"id": "wh-1"})

    client = _client_with_handler(handler)
    result = await client.register_webhook("https://ejemplo.test/webhook", ["order.created"])
    assert result == {"id": "wh-1"}
