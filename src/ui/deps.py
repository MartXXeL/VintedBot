"""Dependencias compartidas de las rutas del panel: sesión y acceso al estado de la app.

Todo el estado compartido (config, IA, sesiones) vive en `app.state` — lo
monta `create_app()` (`src/ui/app.py`) — así que estas funciones son solo
atajos tipados para leerlo desde un `Request`, sin repetir `request.app.state...`
por todas partes.
"""

from collections.abc import Callable
from urllib.parse import urlencode

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse

from src.ai.providers import AIProvider
from src.billing.stripe_client import StripeClient
from src.core.settings import Settings
from src.core.users import User
from src.storage import users_store
from src.ui.login_guard import LoginGuard
from src.ui.sessions import SessionStore
from src.vinted.api_client import VintedApiClient
from src.vinted.session_client import VintedSessionClient

SESSION_COOKIE_NAME = "vintedbot_session"


class NotAuthenticatedError(Exception):
    """Sin sesión válida (o sesión de un usuario desactivado): redirige a /login."""


class NotAuthorizedError(Exception):
    """Sesión válida pero sin permiso para la ruta (solo admin): devuelve 403."""


def get_current_user(request: Request) -> User:
    """El usuario de la sesión actual, o `NotAuthenticatedError` si no hay una válida.

    FastAPI cachea el resultado de una dependencia por petición, así que
    tanto `require_login` como cualquier ruta que pida el usuario para
    filtrar sus propias cuentas comparten esta única consulta a la base de
    datos, en vez de repetirla.
    """
    sessions: SessionStore = request.app.state.sessions
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user_id = sessions.get_user_id(token)
    if user_id is None:
        raise NotAuthenticatedError()

    db_path = str(request.app.state.settings.database_path)
    user = users_store.get_user(db_path, user_id)
    if user is None or not user.is_active:
        raise NotAuthenticatedError()
    return user


def require_login(user: User = Depends(get_current_user)) -> None:
    return None


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Como `get_current_user`, pero exige rol admin — para las rutas de gestión."""
    if user.role != "admin":
        raise NotAuthorizedError()
    return user


def owner_filter_for(user: User) -> int | None:
    """`None` para un admin (sin filtro: ve todo), o su propio id para un member."""
    return None if user.role == "admin" else user.id


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


def get_session_client_factory(request: Request) -> Callable[[str, str], VintedSessionClient]:
    return request.app.state.session_client_factory


def get_api_client_factory(request: Request) -> Callable[[Settings], VintedApiClient]:
    return request.app.state.api_client_factory


def get_stripe_client_factory(request: Request) -> Callable[[Settings], StripeClient]:
    return request.app.state.stripe_client_factory


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "desconocida"


def redirect_with_message(
    path: str, *, ok: str | None = None, error: str | None = None, status_code: int = 303
) -> RedirectResponse:
    """Redirige a `path` con un aviso en la query (`?ok=...` o `?error=...`), bien escapado.

    A mano (`f"...?error={texto}"`) rompe en cuanto el texto trae un espacio,
    una tilde o cualquier carácter especial (p. ej. el motivo del limitador
    de ritmo); `urlencode` es lo único que hace falta para no reinventarlo
    peor en cada ruta.
    """
    params = {}
    if ok:
        params["ok"] = ok
    if error:
        params["error"] = error
    query = f"?{urlencode(params)}" if params else ""
    return RedirectResponse(f"{path}{query}", status_code=status_code)
