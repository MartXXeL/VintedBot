"""Motor de decisión de ofertas: código puro, sin IA y sin red.

La idea central del proyecto es separar la lógica de decisión de la
redacción: este módulo decide un NÚMERO (aceptar / contraofertar con cuánto /
rechazar) comparando la oferta contra el precio mínimo, que nunca sale de
aquí. La IA (`src/ai/negotiation_writer.py`) solo redacta la respuesta a
partir de la decisión ya tomada — recibe `NegotiationDecision.to_ai_context()`,
que nunca incluye el precio mínimo ni la proporción calculada.
"""

from src.negotiation.policy import DEFAULT_POLICY, NegotiationPolicy
from src.vinted.models import NegotiationDecision


def decide(
    offer_amount: float,
    min_price: float,
    listing_price: float | None = None,
    policy: NegotiationPolicy = DEFAULT_POLICY,
) -> NegotiationDecision:
    """Decide qué hacer con una oferta, dado el precio mínimo del anuncio.

    - `ratio >= policy.accept_ratio`  -> aceptar.
    - `policy.reject_ratio <= ratio < policy.accept_ratio` -> contraofertar.
    - `ratio < policy.reject_ratio`   -> rechazar.

    `listing_price` (el precio de venta publicado) es opcional pero
    recomendado: es la referencia que usa la contraoferta para dejar margen
    de negociación por encima del mínimo (ver `_compute_counter_amount`). Sin
    él, la contraoferta cae directamente al mínimo.

    Lanza `ValueError` si `min_price` no es positivo (un anuncio sin precio
    mínimo configurado no debe poder negociarse automáticamente) o si
    `offer_amount` es negativo.
    """
    if min_price <= 0:
        raise ValueError("min_price debe ser mayor que cero para poder negociar")
    if offer_amount < 0:
        raise ValueError("offer_amount no puede ser negativo")

    ratio = offer_amount / min_price

    if ratio >= policy.accept_ratio:
        return NegotiationDecision(
            action="accept",
            offer_amount=offer_amount,
            min_price=min_price,
            ratio=ratio,
        )

    if ratio < policy.reject_ratio:
        return NegotiationDecision(
            action="reject",
            offer_amount=offer_amount,
            min_price=min_price,
            ratio=ratio,
        )

    counter_amount = _compute_counter_amount(offer_amount, min_price, listing_price, policy)
    return NegotiationDecision(
        action="counter",
        offer_amount=offer_amount,
        min_price=min_price,
        counter_amount=counter_amount,
        ratio=ratio,
    )


def _compute_counter_amount(
    offer_amount: float,
    min_price: float,
    listing_price: float | None,
    policy: NegotiationPolicy,
) -> float:
    """Punto medio entre la oferta y una referencia "alta", acotado al mínimo.

    La referencia alta es el precio de venta publicado (`listing_price`) si
    se conoce y es mayor que el mínimo: así la contraoferta deja margen de
    negociación real (p. ej. oferta 14€, mínimo 20€, precio 36€ -> 25€), en
    vez de ir directa al suelo. Sin `listing_price`, la referencia es el
    propio mínimo y la contraoferta se convierte en "pedir justo el mínimo".

    El resultado se acota siempre a `[min_price, referencia]` y se redondea a
    0,50€ (el paso habitual de precio en Vinted), para no proponer céntimos
    sueltos poco naturales (p. ej. 14,37€).
    """
    if policy.counter_strategy != "midpoint":
        raise ValueError(f"Estrategia de contraoferta desconocida: {policy.counter_strategy}")

    reference = listing_price if listing_price is not None and listing_price > min_price else min_price
    midpoint = (offer_amount + reference) / 2
    rounded = round(midpoint * 2) / 2
    return min(max(rounded, min_price), reference)
