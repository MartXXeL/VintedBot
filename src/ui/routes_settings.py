"""Ajustes: edita `.env` desde un formulario tipado (no en texto libre).

Los campos sensibles (claves de API, credenciales) nunca se vuelven a
mostrar en el HTML una vez guardados — solo un indicador de que ya están
configurados — para no dejarlos expuestos en el código fuente de la página.
Guardar escribe en `.env`, pero algunos cambios (sobre todo el proveedor de
IA) solo se aplican del todo al reiniciar el proceso: este panel no
reinicia nada solo, se avisa en el mensaje de confirmación.
"""

from fastapi import APIRouter, Depends, Form, Request

from src.core.env_file import update_env_file
from src.core.settings import Settings
from src.ui.deps import get_settings, redirect_with_message, require_login

router = APIRouter(dependencies=[Depends(require_login)])


@router.get("/settings")
def settings_view(request: Request, settings: Settings = Depends(get_settings)):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "active": "settings",
            "settings": settings,
            "ok": request.query_params.get("ok"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/settings")
def update_settings(
    anthropic_api_key: str = Form(""),
    anthropic_model: str = Form("claude-sonnet-5"),
    ai_provider: str = Form("auto"),
    vinted_domain: str = Form("www.vinted.es"),
    vinted_api_client_id: str = Form(""),
    vinted_api_client_secret: str = Form(""),
    rate_limit_min_seconds: int = Form(180),
    rate_limit_max_seconds: int = Form(600),
    rate_limit_max_actions_per_day: int = Form(50),
    rate_limit_night_start_hour: int = Form(23),
    rate_limit_night_end_hour: int = Form(8),
    dac7_alert_amount_eur: float = Form(2000.0),
    dac7_alert_transactions: int = Form(30),
    stripe_secret_key: str = Form(""),
    stripe_webhook_secret: str = Form(""),
    stripe_price_starter_id: str = Form(""),
    stripe_price_pro_id: str = Form(""),
    stripe_price_scale_id: str = Form(""),
    settings: Settings = Depends(get_settings),
):
    if rate_limit_min_seconds > rate_limit_max_seconds:
        return redirect_with_message(
            "/settings", error="La cadencia mínima no puede ser mayor que la máxima"
        )
    if not (0 <= rate_limit_night_start_hour <= 23) or not (0 <= rate_limit_night_end_hour <= 23):
        return redirect_with_message("/settings", error="Las horas de la pausa nocturna van de 0 a 23")

    updates = {
        "ANTHROPIC_MODEL": anthropic_model,
        "AI_PROVIDER": ai_provider,
        "VINTED_DOMAIN": vinted_domain,
        "RATE_LIMIT_MIN_SECONDS": str(rate_limit_min_seconds),
        "RATE_LIMIT_MAX_SECONDS": str(rate_limit_max_seconds),
        "RATE_LIMIT_MAX_ACTIONS_PER_DAY": str(rate_limit_max_actions_per_day),
        "RATE_LIMIT_NIGHT_START_HOUR": str(rate_limit_night_start_hour),
        "RATE_LIMIT_NIGHT_END_HOUR": str(rate_limit_night_end_hour),
        "DAC7_ALERT_AMOUNT_EUR": str(dac7_alert_amount_eur),
        "DAC7_ALERT_TRANSACTIONS": str(dac7_alert_transactions),
    }
    # Los secretos solo se pisan si se ha escrito algo nuevo: un campo dejado
    # en blanco significa "no tocar", no "borrar la clave que ya había".
    if anthropic_api_key.strip():
        updates["ANTHROPIC_API_KEY"] = anthropic_api_key.strip()
    if vinted_api_client_id.strip():
        updates["VINTED_API_CLIENT_ID"] = vinted_api_client_id.strip()
    if vinted_api_client_secret.strip():
        updates["VINTED_API_CLIENT_SECRET"] = vinted_api_client_secret.strip()
    if stripe_secret_key.strip():
        updates["STRIPE_SECRET_KEY"] = stripe_secret_key.strip()
    if stripe_webhook_secret.strip():
        updates["STRIPE_WEBHOOK_SECRET"] = stripe_webhook_secret.strip()
    # Los ID de precio no son secretos (son visibles en cualquier Checkout de
    # Stripe), así que estos sí se guardan y se muestran tal cual.
    updates["STRIPE_PRICE_STARTER_ID"] = stripe_price_starter_id.strip()
    updates["STRIPE_PRICE_PRO_ID"] = stripe_price_pro_id.strip()
    updates["STRIPE_PRICE_SCALE_ID"] = stripe_price_scale_id.strip()

    update_env_file(settings.env_path, updates)

    # Refleja el cambio en el panel al instante; lo que ya usa una IA o un
    # cliente HTTP creados al arrancar (p. ej. la clave de Anthropic del
    # trabajador en segundo plano) solo lo recoge un reinicio de verdad.
    settings.anthropic_model = anthropic_model
    settings.ai_provider = ai_provider
    settings.vinted_domain = vinted_domain
    if anthropic_api_key.strip():
        settings.anthropic_api_key = anthropic_api_key.strip()
    if vinted_api_client_id.strip():
        settings.vinted_api_client_id = vinted_api_client_id.strip()
    if vinted_api_client_secret.strip():
        settings.vinted_api_client_secret = vinted_api_client_secret.strip()
    settings.rate_limit.min_seconds = rate_limit_min_seconds
    settings.rate_limit.max_seconds = rate_limit_max_seconds
    settings.rate_limit.max_actions_per_day = rate_limit_max_actions_per_day
    settings.rate_limit.night_start_hour = rate_limit_night_start_hour
    settings.rate_limit.night_end_hour = rate_limit_night_end_hour
    settings.dac7.alert_amount_eur = dac7_alert_amount_eur
    settings.dac7.alert_transactions = dac7_alert_transactions
    if stripe_secret_key.strip():
        settings.stripe_secret_key = stripe_secret_key.strip()
    if stripe_webhook_secret.strip():
        settings.stripe_webhook_secret = stripe_webhook_secret.strip()
    settings.stripe_price_starter_id = stripe_price_starter_id.strip()
    settings.stripe_price_pro_id = stripe_price_pro_id.strip()
    settings.stripe_price_scale_id = stripe_price_scale_id.strip()

    return redirect_with_message(
        "/settings", ok="Cambios guardados. Algunos (como cambiar de proveedor de IA) piden reiniciar la aplicación."
    )
