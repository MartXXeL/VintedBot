"""Fábrica de la app FastAPI del panel.

Todo lo compartido (config, IA, sesiones del panel, bloqueo de fuerza bruta)
vive en `app.state`, y el trabajador en segundo plano
(`src/worker/scheduler.py::run_forever`) arranca y para con el ciclo de vida
de la propia app (`lifespan`), para no necesitar un proceso aparte.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.ai.providers import AIProvider, get_ai_provider
from src.core.env_file import update_env_file
from src.core.logger import logger
from src.core.security import generate_random_password, hash_password
from src.core.settings import Settings
from src.storage.db import init_db
from src.ui.deps import NotAuthenticatedError
from src.ui.login_guard import LoginGuard
from src.ui.routes_auth import router as auth_router
from src.ui.routes_dashboard import router as dashboard_router
from src.ui.sessions import SessionStore
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


def create_app(
    settings: Settings,
    ai_provider: AIProvider | None = None,
    sessions: SessionStore | None = None,
    login_guard: LoginGuard | None = None,
    start_worker: bool = True,
) -> FastAPI:
    init_db(settings.database_path)
    _bootstrap_dashboard_password(settings)

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
    app.state.templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.exception_handler(NotAuthenticatedError)
    async def _redirect_to_login(_request: Request, _exc: NotAuthenticatedError) -> RedirectResponse:
        return RedirectResponse("/login", status_code=303)

    app.include_router(auth_router)
    app.include_router(dashboard_router)

    return app
