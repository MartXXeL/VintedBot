"""Vista general: cuentas conectadas, su estado y el hueco que les queda en el
límite de ritmo — lo primero que se ve al entrar al panel.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from src.core.settings import Settings
from src.storage import accounts_store, actions_store
from src.ui.deps import get_db_path, get_settings, require_login
from src.vinted.models import VintedAccount
from src.vinted.rate_limiter import check_rate_limit

router = APIRouter(dependencies=[Depends(require_login)])


@router.get("/")
def dashboard(
    request: Request, db_path: str = Depends(get_db_path), settings: Settings = Depends(get_settings)
):
    templates = request.app.state.templates
    now = datetime.now()
    rows = []
    for account in accounts_store.list_accounts(db_path):
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
):
    if connection_mode == "session" and not session_cookie.strip():
        return RedirectResponse("/?error=Falta+la+cookie+de+sesi%C3%B3n", status_code=303)

    account = accounts_store.create_account(
        db_path,
        VintedAccount(
            label=label,
            connection_mode=connection_mode,
            status="connected" if session_cookie.strip() else "disconnected",
        ),
        session_cookie=session_cookie.strip() or None,
    )
    return RedirectResponse(f"/?ok=Cuenta+«{account.label}»+conectada", status_code=303)


@router.post("/accounts/{account_id}/automation")
def update_automation(
    account_id: int,
    auto_publish: str = Form(None),
    auto_reply_offers: str = Form(None),
    db_path: str = Depends(get_db_path),
):
    if accounts_store.get_account(db_path, account_id) is None:
        return RedirectResponse("/?error=Cuenta+no+encontrada", status_code=303)

    accounts_store.set_automation_flags(
        db_path,
        account_id,
        auto_publish=auto_publish is not None,
        auto_reply_offers=auto_reply_offers is not None,
    )
    return RedirectResponse("/?ok=Ajustes+de+automatizaci%C3%B3n+guardados", status_code=303)


@router.post("/accounts/{account_id}/delete")
def delete_account(account_id: int, db_path: str = Depends(get_db_path)):
    accounts_store.delete_account(db_path, account_id)
    return RedirectResponse("/?ok=Cuenta+desconectada", status_code=303)
