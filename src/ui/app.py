"""Fábrica de la app FastAPI del panel.

Todo lo compartido (config, IA, sesiones del panel, bloqueo de fuerza bruta)
vive en `app.state`, y el trabajador en segundo plano
(`src/worker/scheduler.py::run_forever`) arranca y para con el ciclo de vida
de la propia app (`lifespan`), para no necesitar un proceso aparte.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.ai.providers import AIProvider, get_ai_provider
from src.billing.stripe_client import StripeClient
from src.core.env_file import update_env_file
from src.core.logger import logger
from src.core.security import generate_random_password, hash_password
from src.core.settings import Settings
from src.storage.db import init_db
from src.ui.deps import NotAuthenticatedError
from src.ui.login_guard import LoginGuard
from src.ui.routes_auth import router as auth_router
from src.ui.routes_billing import router as billing_router
from src.ui.routes_billing import webhook_router as billing_webhook_router
from src.ui.routes_compliance import router as compliance_router
from src.ui.routes_dashboard import router as dashboard_router
from src.ui.routes_listings import router as listings_router
from src.ui.routes_offers import router as offers_router
from src.ui.routes_settings import router as settings_router
from src.ui.routes_tutorial import router as tutorial_router
from src.ui.sessions import SessionStore
from src.vinted.api_client import VintedApiClient
from src.vinted.session_client import VintedSessionClient
from src.worker.scheduler import run_forever

_UI_DIR = Path(__file__).resolve().parent
_TEMPLATES_DIR = _UI_DIR / "templates"
_STATIC_DIR = _UI_DIR / "static"


def _bootstrap_dashboard_password(settings: Settings) -> None:
    """Primer arranque sin contraseña configurada: genera una y la muestra UNA vez."""
    if settings.dashboard_password_hash:
        return
    password = generate_random_password()
    settings.dashboard_password_hash = hash_password(password)
    try:
        update_env_file(settings.env_path, {"DASHBOARD_PASSWORD_HASH": settings.dashboard_password_hash})
    except OSError:
        logger.warning("No se pudo guardar la contraseña generada en .env (no persistirá al reiniciar).")
    print("\n" + "=" * 60)
    print(f"  Contraseña del panel (guárdala, no se vuelve a mostrar):\n\n    {password}\n")
    print("=" * 60 + "\n")


def _warn_if_exposed_without_https(settings: Settings) -> None:
    """La cookie de sesión solo lleva `Secure` si `DASHBOARD_FORCE_HTTPS=true`.

    En loopback (host por defecto) da igual: no hay red de por medio que
    pueda interceptarla. Fuera de loopback, sin HTTPS delante, la cookie
    viaja en claro — un aviso alto y claro es mejor que confiar en que se
    lea la letra pequeña del README.
    """
    if settings.dashboard_host not in ("127.0.0.1", "localhost", "::1") and not settings.dashboard_force_https:
        logger.warning(
            f"DASHBOARD_HOST={settings.dashboard_host!r} no es loopback y DASHBOARD_FORCE_HTTPS "
            "está desactivado: la cookie de sesión viajaría sin cifrar. Pon un proxy con HTTPS "
            "delante y activa DASHBOARD_FORCE_HTTPS, o vuelve a 127.0.0.1."
        )


def create_app(
    settings: Settings,
    ai_provider: AIProvider | None = None,
    sessions: SessionStore | None = None,
    login_guard: LoginGuard | None = None,
    session_client_factory: Callable[[str, str], VintedSessionClient] | None = None,
    api_client_factory: Callable[[Settings], VintedApiClient] | None = None,
    stripe_client_factory: Callable[[Settings], StripeClient] | None = None,
    start_worker: bool = True,
) -> FastAPI:
    init_db(settings.database_path)
    _bootstrap_dashboard_password(settings)
    _warn_if_exposed_without_https(settings)

    ai_provider = ai_provider or get_ai_provider(
        settings.resolve_ai_provider(), settings.anthropic_api_key, settings.anthropic_model
    )
    stop_event = asyncio.Event()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        worker_task = (
            asyncio.create_task(run_forever(str(settings.database_path), settings, ai_provider, stop_event))
            if start_worker
            else None
        )
        try:
            yield
        finally:
            stop_event.set()
            if worker_task is not None:
                await worker_task

    app = FastAPI(title="VintedBot", lifespan=lifespan)
    app.state.settings = settings
    app.state.ai_provider = ai_provider
    app.state.sessions = sessions or SessionStore()
    app.state.login_guard = login_guard or LoginGuard()
    app.state.session_client_factory = session_client_factory or (
        lambda domain, cookie: VintedSessionClient(domain=domain, session_cookie=cookie)
    )
    app.state.api_client_factory = api_client_factory or (
        lambda s: VintedApiClient(
            base_url=s.vinted_api_base_url,
            client_id=s.vinted_api_client_id,
            client_secret=s.vinted_api_client_secret,
        )
    )
    app.state.stripe_client_factory = stripe_client_factory or (
        lambda s: StripeClient(secret_key=s.stripe_secret_key, webhook_secret=s.stripe_webhook_secret)
    )
    app.state.templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # Las fotos subidas para generar anuncios NO se montan como `StaticFiles`
    # (eso serviría cualquier archivo sin pasar por el login): se sirven desde
    # `GET /listings/{id}/photos/{i}` en `src/ui/routes_listings.py`, que sí
    # está detrás de `Depends(require_login)` como el resto del panel.

    @app.exception_handler(NotAuthenticatedError)
    async def _redirect_to_login(_request: Request, _exc: NotAuthenticatedError) -> RedirectResponse:
        return RedirectResponse("/login", status_code=303)

    app.include_router(auth_router)
    app.include_router(dashboard_router)
    app.include_router(listings_router)
    app.include_router(offers_router)
    app.include_router(compliance_router)
    app.include_router(settings_router)
    app.include_router(billing_router)
    app.include_router(billing_webhook_router)
    app.include_router(tutorial_router)

    return app
