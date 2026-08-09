"""Login del panel: contraseña única (un solo operador), con bloqueo por fuerza bruta."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from src.core.security import verify_password
from src.core.settings import Settings
from src.ui.deps import SESSION_COOKIE_NAME, client_ip, get_login_guard, get_sessions, get_settings
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
    password: str = Form(...),
    settings: Settings = Depends(get_settings),
    sessions: SessionStore = Depends(get_sessions),
    login_guard: LoginGuard = Depends(get_login_guard),
):
    ip = client_ip(request)
    if login_guard.is_locked_out(ip):
        return RedirectResponse(
            "/login?error=Demasiados+intentos+fallidos%2C+espera+unos+minutos", status_code=303
        )

    if not verify_password(password, settings.dashboard_password_hash):
        login_guard.register_failure(ip)
        return RedirectResponse("/login?error=Contrase%C3%B1a+incorrecta", status_code=303)

    login_guard.register_success(ip)
    token = sessions.create()
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
