"""Dependencias compartidas de las rutas del panel: sesión y acceso al estado de la app.

Todo el estado compartido (config, IA, sesiones) vive en `app.state` — lo
monta `create_app()` (`src/ui/app.py`) — así que estas funciones son solo
atajos tipados para leerlo desde un `Request`, sin repetir `request.app.state...`
por todas partes.
"""

from fastapi import Request

from src.ai.providers import AIProvider
from src.core.settings import Settings
from src.ui.login_guard import LoginGuard
from src.ui.sessions import SessionStore

SESSION_COOKIE_NAME = "vintedbot_session"


class NotAuthenticatedError(Exception):
    """Sin sesión válida: el `exception_handler` de `create_app` redirige a /login."""


def require_login(request: Request) -> None:
    sessions: SessionStore = request.app.state.sessions
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not sessions.is_valid(token):
        raise NotAuthenticatedError()


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db_path(request: Request) -> str:
    return str(request.app.state.settings.database_path)


def get_ai_provider(request: Request) -> AIProvider:
    return request.app.state.ai_provider


def get_sessions(request: Request) -> SessionStore:
    return request.app.state.sessions


def get_login_guard(request: Request) -> LoginGuard:
    return request.app.state.login_guard


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "desconocida"
