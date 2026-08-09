"""Redacta la respuesta a una oferta, a partir de una decisión YA TOMADA.

Frontera de seguridad del proyecto: esta función es el ÚNICO punto por el que
una decisión de negociación llega a la IA, y lo hace ya convertida en
`to_ai_context()` — sin precio mínimo, sin la proporción oferta/mínimo, solo
la acción y (si aplica) el importe de la contraoferta que el motor de reglas
ya decidió. La IA no tiene forma de "negociar" el número: solo lo envuelve
en una frase.
"""

from src.ai.providers import AIProvider
from src.vinted.models import NegotiationDecision


def draft_reply(provider: AIProvider, decision: NegotiationDecision) -> str:
    return provider.draft_negotiation_reply(decision.to_ai_context())
