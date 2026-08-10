"""Login del panel: email + contraseña por usuario, con bloqueo por fuerza bruta."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from src.core.security import verify_password
from src.core.settings import Settings
from src.storage import users_store
from src.ui.deps import (
    SESSION_COOKIE_NAME,
    client_ip,
    get_db_path,
    get_login_guard,
    get_sessions,
    get_settings,
    redirect_with_message,
)
from src.ui.login_guard import LoginGuard
from src.ui.sessions import SessionStore

router = APIRouter()


@router.get("/login")
def login_form(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "login.html", {"error": request.query_params.get("error")})


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db_path: str = Depends(get_db_path),
    settings: Settings = Depends(get_settings),
    sessions: SessionStore = Depends(get_sessions),
    login_guard: LoginGuard = Depends(get_login_guard),
):
    ip = client_ip(request)
    if login_guard.is_locked_out(ip):
        return redirect_with_message("/login", error="Demasiados intentos fallidos, espera unos minutos")

    user = users_store.get_user_by_email(db_path, email)
    stored_hash = users_store.get_password_hash(db_path, user.id) if user else None
    # Se llama a `verify_password` aunque el email no exista (con un hash
    # `None` siempre da `False`, sin lanzar nada): así no se filtra por
    # temporización qué emails están dados de alta.
    password_ok = verify_password(password, stored_hash)
    if user is None or not password_ok:
        login_guard.register_failure(ip)
        return redirect_with_message("/login", error="Email o contraseña incorrectos")
    if not user.is_active:
        login_guard.register_failure(ip)
        return redirect_with_message("/login", error="Esta cuenta está desactivada, habla con tu administrador")

    login_guard.register_success(ip)
    token = sessions.create(user.id)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.dashboard_force_https,
        max_age=int(sessions.ttl.total_seconds()),
    )
    return response


@router.post("/logout")
def logout(request: Request, sessions: SessionStore = Depends(get_sessions)):
    sessions.invalidate(request.cookies.get(SESSION_COOKIE_NAME))
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response
