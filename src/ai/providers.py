"""Proveedores de IA: visión para anuncios y redacción de respuestas de negociación.

Dos implementaciones detrás de la misma interfaz (`AIProvider`):

- `AnthropicAIProvider`: Claude Sonnet 5 de verdad, con visión. Necesita
  `ANTHROPIC_API_KEY`.
- `MockAIProvider`: no llama a ningún sitio; genera campos y texto
  deterministas y razonables. Es el proveedor por defecto sin API key, para
  que la app entera (subir fotos, generar anuncio, recibir una oferta,
  contraofertar) se pueda probar de punta a punta sin gastar un céntimo ni
  depender de una cuenta de Anthropic.

Punto de diseño importante: `draft_negotiation_reply` recibe SOLO
`NegotiationDecision.to_ai_context()` (acción + importe final, nunca el
precio mínimo ni la proporción) — el proveedor de IA físicamente no puede
filtrar el mínimo porque nunca lo tiene.
"""

import base64
import json
from abc import ABC, abstractmethod

from src.core.logger import logger
from src.vinted.models import CONDITION_LABELS_ES, ListingDraftFields

_LISTING_SYSTEM_PROMPT = """\
Eres el redactor de anuncios de VintedBot, una herramienta para revendedores \
de ropa y artículos de segunda mano en Vinted. A partir de las fotos de un \
artículo, identifica categoría, marca (si es visible o reconocible), talla y \
estado de conservación, y redacta un título corto y una descripción en tono \
informal y cercano, como la escribiría una persona real vendiendo algo que \
ya no usa — nunca en tono publicitario ni corporativo. Si no puedes \
determinar un campo con confianza razonable, déjalo vacío en vez de \
inventarlo. Llama siempre a `submit_listing_draft` con el resultado.\
"""

_NEGOTIATION_SYSTEM_PROMPT = """\
Eres el asistente de negociación de VintedBot. La decisión de aceptar, \
contraofertar o rechazar YA ESTÁ TOMADA por otro sistema — tu único trabajo \
es redactar la respuesta al comprador en un mensaje corto, amable y en tono \
informal (como hablaría una persona vendiendo en Vinted, no una empresa). \
Nunca menciones un precio distinto del que se te da. Si la acción es \
"counter", el mensaje debe proponer exactamente `counter_amount`. Si es \
"reject", declina con amabilidad sin dar detalles del precio mínimo (no lo \
conoces). Si es "accept", confirma con entusiasmo moderado.\
"""

_LISTING_TOOL = {
    "name": "submit_listing_draft",
    "description": "Envía los campos estructurados y el texto redactado del anuncio.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "Categoría del artículo, p. ej. 'Camisetas'"},
            "brand": {"type": "string", "description": "Marca, vacío si no se reconoce"},
            "size": {"type": "string", "description": "Talla tal y como aparece en la prenda/etiqueta"},
            "item_condition": {
                "type": "string",
                "enum": list(CONDITION_LABELS_ES.keys()),
            },
            "title": {"type": "string", "description": "Título corto y atractivo, sin mayúsculas gritonas"},
            "description": {"type": "string", "description": "Descripción en tono informal, 2-4 frases"},
            "confidence": {
                "type": "number",
                "description": "0-1: cuánta confianza tiene en los campos estructurados extraídos",
            },
        },
        "required": ["title", "description", "confidence"],
    },
}


class AIProvider(ABC):
    """Interfaz común: visión para anuncios + redacción de negociación."""

    @abstractmethod
    def generate_listing(self, photos_jpeg: list[bytes], extra_context: str = "") -> ListingDraftFields: ...

    @abstractmethod
    def draft_negotiation_reply(self, decision_context: dict[str, float | str]) -> str: ...


class MockAIProvider(AIProvider):
    """Sin red, sin coste, determinista: para desarrollo, tests y demos."""

    def generate_listing(self, photos_jpeg: list[bytes], extra_context: str = "") -> ListingDraftFields:
        photo_count = len(photos_jpeg)
        return ListingDraftFields(
            category="Ropa",
            brand=None,
            size=None,
            item_condition="good",
            title="Artículo en buen estado (revisar antes de publicar)",
            description=(
                "Borrador generado sin conexión a la IA real: conecta "
                "ANTHROPIC_API_KEY para que el modelo lea las fotos de verdad. "
                f"Se recibieron {photo_count} foto(s)."
            ),
            confidence=0.0,
        )

    def draft_negotiation_reply(self, decision_context: dict[str, float | str]) -> str:
        action = decision_context["action"]
        if action == "accept":
            return "¡Trato hecho! Acepto tu oferta, te aviso en cuanto prepare el envío 😊"
        if action == "counter":
            amount = decision_context["counter_amount"]
            return f"¡Gracias por tu oferta! No puedo bajar tanto, pero te lo dejo en {amount}€, ¿qué te parece?"
        return "¡Gracias por el interés! No puedo bajar tanto el precio esta vez, pero un saludo 🙂"


class AnthropicAIProvider(AIProvider):
    """Claude Sonnet 5 con visión, vía SDK oficial de Anthropic.

    `client` es inyectable para poder probar la construcción de los mensajes
    y el parseo de la respuesta sin llamar de verdad a la API (ver
    `tests/unit/test_ai_providers.py`).
    """

    def __init__(self, api_key: str, model: str = "claude-sonnet-5", client: object | None = None) -> None:
        if client is not None:
            self._client = client
        else:
            from anthropic import Anthropic

            self._client = Anthropic(api_key=api_key)
        self._model = model

    def generate_listing(self, photos_jpeg: list[bytes], extra_context: str = "") -> ListingDraftFields:
        if not photos_jpeg:
            raise ValueError("generate_listing necesita al menos una foto")

        content: list[dict] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.b64encode(photo).decode("ascii"),
                },
            }
            for photo in photos_jpeg
        ]
        prompt_text = "Genera el anuncio a partir de estas fotos."
        if extra_context:
            prompt_text += f" Contexto adicional del vendedor: {extra_context}"
        content.append({"type": "text", "text": prompt_text})

        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=_LISTING_SYSTEM_PROMPT,
            tools=[_LISTING_TOOL],
            tool_choice={"type": "tool", "name": "submit_listing_draft"},
            messages=[{"role": "user", "content": content}],
        )
        return self._parse_listing_response(response)

    def draft_negotiation_reply(self, decision_context: dict[str, float | str]) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=256,
            system=_NEGOTIATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(decision_context, ensure_ascii=False)}],
        )
        for block in response.content:
            if getattr(block, "type", None) == "text":
                return block.text.strip()
        raise ValueError("La respuesta de la IA no contenía texto")

    @staticmethod
    def _parse_listing_response(response: object) -> ListingDraftFields:
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "submit_listing_draft":
                data = dict(block.input)
                condition = data.get("item_condition") or None
                if condition is not None and condition not in CONDITION_LABELS_ES:
                    logger.warning(f"Estado de artículo desconocido de la IA: {condition!r}")
                    condition = None
                return ListingDraftFields(
                    category=data.get("category") or None,
                    brand=data.get("brand") or None,
                    size=data.get("size") or None,
                    item_condition=condition,
                    title=data.get("title", ""),
                    description=data.get("description", ""),
                    confidence=float(data.get("confidence", 0.0)),
                )
        raise ValueError("La respuesta de la IA no llamó a submit_listing_draft")


def get_ai_provider(
    provider_name: str,
    anthropic_api_key: str = "",
    anthropic_model: str = "claude-sonnet-5",
) -> AIProvider:
    """Fábrica: `provider_name` ya resuelto (ver `Settings.resolve_ai_provider`)."""
    if provider_name == "anthropic":
        if not anthropic_api_key:
            raise ValueError("AI_PROVIDER=anthropic pero falta ANTHROPIC_API_KEY")
        return AnthropicAIProvider(api_key=anthropic_api_key, model=anthropic_model)
    if provider_name == "mock":
        return MockAIProvider()
    raise ValueError(f"Proveedor de IA desconocido: {provider_name!r}")
