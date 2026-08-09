"""Cliente de la vía oficial: Vinted Pro Integrations (OAuth2, artículos y pedidos).

No cubre mensajería ni ofertas (ver `docs/vinted_api_notes.md`): para eso
está `src/vinted/session_client.py`. `http_client` es inyectable para poder
probar este cliente entero sin red (ver `tests/unit/test_api_client.py`,
que usa `httpx.MockTransport`).
"""

from datetime import datetime, timedelta

import httpx

from src.vinted import endpoints
from src.vinted.errors import raise_for_status

_TOKEN_SAFETY_MARGIN_SECONDS = 30


class VintedApiClient:
    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not client_id or not client_secret:
            raise ValueError("client_id y client_secret son obligatorios para la vía oficial")
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http_client or httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=20.0)
        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _ensure_token(self) -> str:
        if (
            self._access_token is not None
            and self._token_expires_at is not None
            and datetime.now() < self._token_expires_at
        ):
            return self._access_token

        response = await self._http.post(
            endpoints.OAUTH_TOKEN,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        raise_for_status(response, "Autenticación OAuth2")
        payload = response.json()
        self._access_token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 3600))
        self._token_expires_at = datetime.now() + timedelta(
            seconds=max(expires_in - _TOKEN_SAFETY_MARGIN_SECONDS, 0)
        )
        return self._access_token

    async def _auth_headers(self) -> dict[str, str]:
        token = await self._ensure_token()
        return {"Authorization": f"Bearer {token}"}

    async def create_item(self, payload: dict) -> dict:
        headers = await self._auth_headers()
        response = await self._http.post(endpoints.API_ITEMS, json=payload, headers=headers)
        raise_for_status(response, "Crear artículo")
        return response.json()

    async def update_item(self, item_id: str, payload: dict) -> dict:
        headers = await self._auth_headers()
        url = endpoints.API_ITEM_DETAIL.format(item_id=item_id)
        response = await self._http.patch(url, json=payload, headers=headers)
        raise_for_status(response, f"Actualizar artículo {item_id}")
        return response.json()

    async def list_orders(self, **params: str) -> list[dict]:
        headers = await self._auth_headers()
        response = await self._http.get(endpoints.API_ORDERS, params=params, headers=headers)
        raise_for_status(response, "Listar pedidos")
        return response.json().get("orders", [])

    async def register_webhook(self, url: str, events: list[str]) -> dict:
        headers = await self._auth_headers()
        response = await self._http.post(
            endpoints.API_WEBHOOKS, json={"url": url, "events": events}, headers=headers
        )
        raise_for_status(response, "Registrar webhook")
        return response.json()
