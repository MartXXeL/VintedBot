"""Suscripción: uso actual, plan recomendado y checkout de Stripe.

Dos routers separados a propósito: `router` (plan, checkout) vive detrás de
login como el resto del panel; `webhook_router` NO — a ese lo llama Stripe
directamente, sin cookie de sesión, así que su única autenticación es la
firma verificada por `StripeClient.verify_webhook_event`.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.billing.plans import PLANS, calculate_monthly_price, recommend_plan
from src.billing.stripe_client import WebhookVerificationError
from src.core.logger import logger
from src.core.settings import Settings
from src.core.users import User
from src.storage import accounts_store, listings_store
from src.ui.deps import (
    get_current_user,
    get_db_path,
    get_settings,
    get_stripe_client_factory,
    redirect_with_message,
    require_login,
)

router = APIRouter(dependencies=[Depends(require_login)])
webhook_router = APIRouter()

# El nombre de la variable de entorno de cada plan (`BillingPlan.stripe_price_env_var`,
# p. ej. "STRIPE_PRICE_STARTER_ID") coincide, en minúsculas, con el atributo
# de `Settings` que lo guarda — así no hace falta un mapeo aparte.


def _current_usage(db_path: str, owner_user_id: int) -> tuple[int, int]:
    """(cuentas propias conectadas, anuncios generados/publicados este mes natural).

    Deliberadamente siempre las del usuario que mira la pantalla (incluso si
    es admin): la suscripción es personal, no una vista agregada de todo el
    panel — para eso está `/admin`.
    """
    accounts = accounts_store.list_accounts(db_path, owner_user_id=owner_user_id)
    since_month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    listings_this_month = sum(
        listings_store.count_listings_since(db_path, account.id, since_month_start) for account in accounts
    )
    return len(accounts), listings_this_month


@router.get("/billing")
def billing_view(
    request: Request,
    db_path: str = Depends(get_db_path),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
):
    templates = request.app.state.templates
    connected_accounts, listings_this_month = _current_usage(db_path, user.id)
    calculations = {
        plan_id: calculate_monthly_price(plan, connected_accounts, listings_this_month)
        for plan_id, plan in PLANS.items()
    }
    recommended = recommend_plan(connected_accounts, listings_this_month)

    return templates.TemplateResponse(
        request,
        "billing.html",
        {
            "active": "billing",
            "current_user": user,
            "plans": PLANS,
            "calculations": calculations,
            "recommended_plan_id": recommended.plan_id,
            "connected_accounts": connected_accounts,
            "listings_this_month": listings_this_month,
            "stripe_configured": bool(settings.stripe_secret_key),
            "ok": request.query_params.get("ok"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/billing/checkout/{plan_id}")
def start_checkout(
    request: Request, plan_id: str, settings: Settings = Depends(get_settings)
):
    plan = PLANS.get(plan_id)
    if plan is None:
        return redirect_with_message("/billing", error="Plan desconocido")
    if not settings.stripe_secret_key:
        return redirect_with_message("/billing", error="Stripe no está configurado en Ajustes")

    price_id = getattr(settings, plan.stripe_price_env_var.lower(), "")
    if not price_id:
        return redirect_with_message("/billing", error=f"Falta el ID de precio de Stripe del plan {plan.name}")

    base_url = str(request.base_url).rstrip("/")
    stripe_client_factory = request.app.state.stripe_client_factory
    stripe_client = stripe_client_factory(settings)
    try:
        checkout_url = stripe_client.create_checkout_session(
            price_id=price_id,
            success_url=f"{base_url}/billing?ok=Suscripci%C3%B3n+iniciada",
            cancel_url=f"{base_url}/billing?error=Pago+cancelado",
        )
    except Exception as error:  # noqa: BLE001 — cualquier fallo de Stripe se trata igual de cara al usuario
        logger.warning(f"No se pudo crear la sesión de Stripe Checkout: {error}")
        return redirect_with_message("/billing", error="No se pudo iniciar el pago con Stripe")

    return RedirectResponse(checkout_url, status_code=303)


@webhook_router.post("/billing/webhook")
async def stripe_webhook(
    request: Request,
    settings: Settings = Depends(get_settings),
    stripe_client_factory=Depends(get_stripe_client_factory),
    stripe_signature: str = Header(default=""),
):
    if not settings.stripe_secret_key or not settings.stripe_webhook_secret:
        # Sin Stripe configurado esta ruta no debería recibir nada de nadie;
        # 404 en vez de un 500 al construir un StripeClient sin clave.
        raise HTTPException(status_code=404)

    payload = await request.body()
    stripe_client = stripe_client_factory(settings)
    try:
        event = stripe_client.verify_webhook_event(payload, stripe_signature)
    except WebhookVerificationError as error:
        raise HTTPException(status_code=400, detail="Firma de webhook inválida") from error

    # Sin un modelo de clientes/suscripciones propio (el panel es de un solo
    # operador), de momento solo se registra el evento; el sitio para
    # engancharlo a algo persistente es aquí.
    logger.info(f"Evento de Stripe recibido: {event.get('type', 'desconocido')}")
    return {"received": True}
