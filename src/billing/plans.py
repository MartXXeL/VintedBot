"""Planes de precio: por cuenta conectada y volumen de anuncios, no por usuario.

Un mismo cliente suele conectar varias cuentas de Vinted (marca personal +
cuentas de familiares, o varios nichos), así que cobrar "por usuario" no
refleja el uso real ni el coste (cada cuenta conectada es trabajo del
limitador de ritmo y de la cola de negociación, con independencia de cuántas
personas la usen). Los tres planes son un punto de partida razonable a partir
del rango citado (30-120€/mes): cada uno incluye una cuota de cuentas y de
anuncios generados/publicados al mes, y el exceso se cobra por unidad.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class BillingPlan:
    id: str
    name: str
    monthly_price_eur: float
    included_accounts: int
    included_listings_per_month: int
    price_per_extra_account_eur: float
    price_per_extra_100_listings_eur: float
    stripe_price_env_var: str


PLANS: dict[str, BillingPlan] = {
    "starter": BillingPlan(
        id="starter",
        name="Starter",
        monthly_price_eur=30.0,
        included_accounts=2,
        included_listings_per_month=150,
        price_per_extra_account_eur=8.0,
        price_per_extra_100_listings_eur=5.0,
        stripe_price_env_var="STRIPE_PRICE_STARTER_ID",
    ),
    "pro": BillingPlan(
        id="pro",
        name="Pro",
        monthly_price_eur=60.0,
        included_accounts=5,
        included_listings_per_month=500,
        price_per_extra_account_eur=7.0,
        price_per_extra_100_listings_eur=4.0,
        stripe_price_env_var="STRIPE_PRICE_PRO_ID",
    ),
    "scale": BillingPlan(
        id="scale",
        name="Scale",
        monthly_price_eur=120.0,
        included_accounts=15,
        included_listings_per_month=1500,
        price_per_extra_account_eur=6.0,
        price_per_extra_100_listings_eur=3.0,
        stripe_price_env_var="STRIPE_PRICE_SCALE_ID",
    ),
}


@dataclass(frozen=True)
class BillingCalculation:
    plan_id: str
    base_price_eur: float
    extra_accounts: int
    extra_accounts_cost_eur: float
    extra_listings: int
    extra_listings_cost_eur: float
    total_eur: float


def calculate_monthly_price(
    plan: BillingPlan, connected_accounts: int, listings_used: int
) -> BillingCalculation:
    """Calcula el coste mensual real de un cliente en un plan dado.

    El exceso de anuncios se cobra por bloques de 100 (empezados): 1 anuncio
    de más ya cuenta como un bloque, igual que hacen la mayoría de SaaS con
    tarificación por volumen.
    """
    if connected_accounts < 0 or listings_used < 0:
        raise ValueError("connected_accounts y listings_used no pueden ser negativos")

    extra_accounts = max(0, connected_accounts - plan.included_accounts)
    extra_listings = max(0, listings_used - plan.included_listings_per_month)
    extra_listing_blocks = math.ceil(extra_listings / 100)

    accounts_cost = extra_accounts * plan.price_per_extra_account_eur
    listings_cost = extra_listing_blocks * plan.price_per_extra_100_listings_eur
    total = plan.monthly_price_eur + accounts_cost + listings_cost

    return BillingCalculation(
        plan_id=plan.id,
        base_price_eur=plan.monthly_price_eur,
        extra_accounts=extra_accounts,
        extra_accounts_cost_eur=accounts_cost,
        extra_listings=extra_listings,
        extra_listings_cost_eur=listings_cost,
        total_eur=total,
    )


def recommend_plan(connected_accounts: int, listings_used: int) -> BillingCalculation:
    """De los planes disponibles, el de coste total más bajo para este uso."""
    calculations = [
        calculate_monthly_price(plan, connected_accounts, listings_used) for plan in PLANS.values()
    ]
    return min(calculations, key=lambda calc: calc.total_eur)


def estimate_ai_cost_usd(
    input_tokens: int,
    output_tokens: int,
    price_per_million_input_usd: float = 3.0,
    price_per_million_output_usd: float = 15.0,
) -> float:
    """Coste aproximado de UNA llamada a la IA, dado su consumo de tokens.

    Los precios por defecto son los de Claude Sonnet 5 citados como
    referencia (3 $/M tokens de entrada, 15 $/M de salida): generar un
    anuncio completo (unas pocas fotos + un prompt corto de salida) cuesta
    del orden de un céntimo de dólar, muy por debajo de cualquiera de los
    planes anteriores.
    """
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("input_tokens y output_tokens no pueden ser negativos")
    input_cost = (input_tokens / 1_000_000) * price_per_million_input_usd
    output_cost = (output_tokens / 1_000_000) * price_per_million_output_usd
    return input_cost + output_cost
