"""Vista general: cuentas conectadas, su estado y el hueco que les queda en el
límite de ritmo — lo primero que se ve al entrar al panel.

Un member solo ve y gestiona sus propias cuentas; un admin las ve y gestiona
todas (`owner_filter_for` decide el filtro según el rol).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request

from src.core.settings import Settings
from src.core.users import User
from src.storage import accounts_store, actions_store
from src.ui.deps import (
    get_current_user,
    get_db_path,
    get_settings,
    owner_filter_for,
    redirect_with_message,
    require_login,
)
from src.vinted.models import VintedAccount
from src.vinted.rate_limiter import check_rate_limit

router = APIRouter(dependencies=[Depends(require_login)])


def _owned_account(db_path: str, account_id: int, user: User) -> VintedAccount | None:
    """La cuenta si existe Y (el usuario es admin O es su propietario); si no, `None`.

    Devolver `None` en ambos casos (no encontrada / no es tuya) es a
    propósito: no hay que confirmarle a un member que el id de la cuenta de
    otra persona existe.
    """
    account = accounts_store.get_account(db_path, account_id)
    if account is None:
        return None
    if user.role != "admin" and account.owner_user_id != user.id:
        return None
    return account


@router.get("/")
def dashboard(
    request: Request,
    db_path: str = Depends(get_db_path),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
):
    templates = request.app.state.templates
    now = datetime.now()
    rows = []
    for account in accounts_store.list_accounts(db_path, owner_user_id=owner_filter_for(user)):
        recent = actions_store.actions_in_last_24h(db_path, account.id, now)
        rate_decision = check_rate_limit(now, recent, settings.rate_limit)
        rows.append(
            {
                "account": account,
                "actions_today": len(recent),
                "max_actions": settings.rate_limit.max_actions_per_day,
                "rate_ok": rate_decision.allowed,
                "rate_reason": rate_decision.reason,
            }
        )
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "active": "dashboard",
            "current_user": user,
            "rows": rows,
            "ok": request.query_params.get("ok"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/accounts")
def create_account(
    label: str = Form(...),
    connection_mode: str = Form("session"),
    session_cookie: str = Form(""),
    db_path: str = Depends(get_db_path),
    user: User = Depends(get_current_user),
):
    if connection_mode == "session" and not session_cookie.strip():
        return redirect_with_message("/", error="Falta la cookie de sesión")

    account = accounts_store.create_account(
        db_path,
        VintedAccount(
            label=label,
            connection_mode=connection_mode,
            status="connected" if session_cookie.strip() else "disconnected",
            owner_user_id=user.id,
        ),
        session_cookie=session_cookie.strip() or None,
    )
    return redirect_with_message("/", ok=f"Cuenta «{account.label}» conectada")


@router.post("/accounts/{account_id}/automation")
def update_automation(
    account_id: int,
    auto_publish: str = Form(None),
    auto_reply_offers: str = Form(None),
    db_path: str = Depends(get_db_path),
    user: User = Depends(get_current_user),
):
    if _owned_account(db_path, account_id, user) is None:
        return redirect_with_message("/", error="Cuenta no encontrada")

    accounts_store.set_automation_flags(
        db_path,
        account_id,
        auto_publish=auto_publish is not None,
        auto_reply_offers=auto_reply_offers is not None,
    )
    return redirect_with_message("/", ok="Ajustes de automatización guardados")


@router.post("/accounts/{account_id}/reconnect")
def reconnect_account(
    account_id: int,
    session_cookie: str = Form(...),
    db_path: str = Depends(get_db_path),
    user: User = Depends(get_current_user),
):
    """Renueva la cookie de sesión de una cuenta sin borrarla (y sin perder sus anuncios/ofertas).

    Necesario para cuando la sesión caduca de verdad: sin esto, la única
    forma de recuperar una cuenta marcada "error" sería borrarla y volver a
    crearla, perdiendo todo su historial por el `ON DELETE CASCADE`.
    """
    account = _owned_account(db_path, account_id, user)
    if account is None:
        return redirect_with_message("/", error="Cuenta no encontrada")
    if not session_cookie.strip():
        return redirect_with_message("/", error="Pega la cookie de sesión nueva")

    accounts_store.set_account_session_cookie(db_path, account_id, session_cookie.strip())
    accounts_store.update_account_status(db_path, account_id, "connected")
    return redirect_with_message("/", ok=f"Sesión de «{account.label}» renovada")


@router.post("/accounts/{account_id}/delete")
def delete_account(
    account_id: int, db_path: str = Depends(get_db_path), user: User = Depends(get_current_user)
):
    if _owned_account(db_path, account_id, user) is None:
        return redirect_with_message("/", error="Cuenta no encontrada")
    accounts_store.delete_account(db_path, account_id)
    return redirect_with_message("/", ok="Cuenta desconectada")
