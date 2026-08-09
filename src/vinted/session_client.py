"""Cliente de la vía de respaldo: sesión de navegador, sin alta previa.

Cubre lo que la vía oficial no cubre — publicar (si no se tiene acceso a
Pro Integrations) y, sobre todo, mensajería y ofertas. Es HTTP normal con la
cookie de sesión del propio usuario: nada de anti-detección (ver
`docs/vinted_api_notes.md`). La protección de la cuenta es responsabilidad
de quien llama a este cliente, consultando
`src/vinted/rate_limiter.py::check_rate_limit` ANTES de cada acción que
escribe algo (publicar, mandar mensaje, responder a una oferta) — este
cliente no lo hace por sí mismo para no acoplar HTTP con la política de
ritmo, ver `src/worker/scheduler.py`.
"""

import httpx

from src.vinted import endpoints
from src.vinted.errors import raise_for_status

_USER_AGENT = "VintedBot/0.1 (panel personal, no automatizacion en masa)"


class VintedSessionClient:
    def __init__(
        self,
        domain: str,
        session_cookie: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not session_cookie:
            raise ValueError("session_cookie es obligatorio para la vía de sesión")
        self._http = http_client or httpx.AsyncClient(
            base_url=f"https://{domain}",
            headers={"Cookie": session_cookie, "User-Agent": _USER_AGENT},
            timeout=20.0,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_user(self, user_id: str) -> dict:
        response = await self._http.get(endpoints.SESSION_USER.format(user_id=user_id))
        raise_for_status(response, f"Consultar usuario {user_id}")
        return response.json()

    async def upload_photo(self, image_jpeg: bytes, filename: str = "foto.jpg") -> str:
        """Sube una foto ya preprocesada (ver `src/ai/image_prep.py`) y devuelve su id temporal."""
        files = {"photo[file]": (filename, image_jpeg, "image/jpeg")}
        response = await self._http.post(endpoints.SESSION_PHOTOS, files=files)
        raise_for_status(response, "Subir foto")
        payload = response.json()
        return str(payload["id"])

    async def publish_listing(self, payload: dict) -> dict:
        """`payload` ya con `photo_ids` (de `upload_photo`) y los campos del anuncio."""
        response = await self._http.post(endpoints.SESSION_ITEMS, json=payload)
        raise_for_status(response, "Publicar anuncio")
        return response.json()

    async def list_conversations(self) -> list[dict]:
        response = await self._http.get(endpoints.SESSION_CONVERSATIONS)
        raise_for_status(response, "Listar conversaciones")
        return response.json().get("conversations", [])

    async def send_message(self, conversation_id: str, text: str) -> dict:
        url = endpoints.SESSION_CONVERSATION_MESSAGES.format(conversation_id=conversation_id)
        response = await self._http.post(url, json={"body": text})
        raise_for_status(response, f"Responder en la conversación {conversation_id}")
        return response.json()

    async def accept_offer(self, conversation_id: str, offer_id: str) -> dict:
        url = endpoints.SESSION_OFFER_ACCEPT.format(conversation_id=conversation_id, offer_id=offer_id)
        response = await self._http.post(url)
        raise_for_status(response, f"Aceptar oferta {offer_id}")
        return response.json()

    async def reject_offer(self, conversation_id: str, offer_id: str) -> dict:
        url = endpoints.SESSION_OFFER_REJECT.format(conversation_id=conversation_id, offer_id=offer_id)
        response = await self._http.post(url)
        raise_for_status(response, f"Rechazar oferta {offer_id}")
        return response.json()

    async def counter_offer(self, conversation_id: str, offer_id: str, amount: float) -> dict:
        url = endpoints.SESSION_OFFER_COUNTER.format(conversation_id=conversation_id, offer_id=offer_id)
        response = await self._http.post(url, json={"amount": amount})
        raise_for_status(response, f"Contraofertar {offer_id}")
        return response.json()


def parse_pending_offers(conversations: list[dict]) -> list[dict]:
    """Extrae las ofertas pendientes de una lista de conversaciones.

    Forma esperada de cada conversación (ver `docs/vinted_api_notes.md` — es
    la parte de MENOR certeza de toda la integración):
    `{"id": ..., "offer": {"id": ..., "amount": ..., "status": "pending", ...}, ...}`.
    Cualquier conversación sin bloque `offer` o con `status` distinto de
    `"pending"` se ignora en vez de fallar, para que un cambio de formato en
    una sola conversación no tumbe el listado entero.
    """
    pending = []
    for conversation in conversations:
        offer = conversation.get("offer")
        if not offer or offer.get("status") != "pending":
            continue
        pending.append(
            {
                "conversation_id": conversation.get("id"),
                "offer_id": offer.get("id"),
                "amount": offer.get("amount"),
                "buyer_name": conversation.get("buyer", {}).get("login"),
            }
        )
    return pending
