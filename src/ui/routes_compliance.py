"""DAC7: aviso anticipado de qué cuentas van a tener que reportarse este año."""

from datetime import datetime

from fastapi import APIRouter, Depends, Request

from src.compliance.dac7 import evaluate_dac7
from src.core.settings import Settings
from src.core.users import User
from src.storage import accounts_store, sales_store
from src.ui.deps import get_current_user, get_db_path, get_settings, owner_filter_for, require_login

router = APIRouter(dependencies=[Depends(require_login)])


@router.get("/compliance")
def compliance_view(
    request: Request,
    db_path: str = Depends(get_db_path),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
):
    templates = request.app.state.templates
    year = datetime.now().year
    all_sales = sales_store.list_sales(db_path)
    rows = [
        {"account": account, "status": evaluate_dac7(account.id, all_sales, year, settings.dac7)}
        for account in accounts_store.list_accounts(db_path, owner_user_id=owner_filter_for(user))
    ]
    return templates.TemplateResponse(
        request,
        "compliance.html",
        {"active": "compliance", "current_user": user, "rows": rows, "year": year, "settings": settings},
    )
