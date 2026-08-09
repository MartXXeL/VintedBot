"""Negociación: ofertas ya decididas y redactadas por el trabajador, a la espera
de que un humano las apruebe (o las descarte) antes de que se manden a Vinted.
"""

from collections.abc import Callable

from fastapi import APIRouter, Depends, Request

from src.core.logger import logger
from src.core.settings import Settings
from src.storage import accounts_store, listings_store, offers_store
from src.ui.deps import (
    get_db_path,
    get_session_client_factory,
    get_settings,
    redirect_with_message,
    require_login,
)
from src.vinted.session_client import VintedSessionClient
from src.worker.scheduler import send_offer_reply_now

router = APIRouter(dependencies=[Depends(require_login)])


@router.get("/offers")
def list_offers_view(request: Request, db_path: str = Depends(get_db_path)):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "offers.html",
        {
            "active": "offers",
            "offers": offers_store.list_offers(db_path, status="pending"),
            "listings": {listing.id: listing for listing in listings_store.list_listings(db_path)},
            "accounts": {account.id: account for account in accounts_store.list_accounts(db_path)},
            "ok": request.query_params.get("ok"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/offers/{offer_id}/approve")
async def approve_offer(
    offer_id: int,
    db_path: str = Depends(get_db_path),
    settings: Settings = Depends(get_settings),
    client_factory: Callable[[str, str], VintedSessionClient] = Depends(get_session_client_factory),
):
    offer = offers_store.get_offer(db_path, offer_id)
    if offer is None:
        return redirect_with_message("/offers", error="Oferta no encontrada")

    account = accounts_store.get_account(db_path, offer.account_id)
    if account is None:
        return redirect_with_message("/offers", error="Cuenta no encontrada")

    cookie = accounts_store.get_account_session_cookie(db_path, account.id)
    if not cookie:
        return redirect_with_message("/offers", error="La cuenta no tiene una sesión guardada")

    client = client_factory(settings.vinted_domain, cookie)
    try:
        blocked = await send_offer_reply_now(db_path, account, offer, client, settings)
    except ValueError as error:
        return redirect_with_message("/offers", error=str(error))
    except Exception as error:  # noqa: BLE001 — cualquier fallo al hablar con Vinted se trata igual de cara al usuario
        logger.warning(f"Fallo al mandar la respuesta de la oferta {offer_id} a Vinted: {error}")
        return redirect_with_message("/offers", error=f"Vinted rechazó el envío: {error}")
    finally:
        await client.aclose()

    if blocked is not None:
        return redirect_with_message("/offers", error=f"Bloqueado por el ritmo seguro: {blocked.reason}")
    return redirect_with_message("/offers", ok="Respuesta enviada a la compradora")


@router.post("/offers/{offer_id}/discard")
def discard_offer_route(offer_id: int, db_path: str = Depends(get_db_path)):
    if offers_store.get_offer(db_path, offer_id) is None:
        return redirect_with_message("/offers", error="Oferta no encontrada")
    offers_store.discard_offer(db_path, offer_id)
    return redirect_with_message("/offers", ok="Oferta descartada")
