"""Anuncios: subir fotos, generar el borrador con IA, revisar/editar y publicar.

La IA solo PROPONE (`build_listing_draft`): el anuncio se guarda como
`draft` y el vendedor lo revisa/edita en `/listings/{id}/edit` antes de que
"Publicar ahora" lo mande de verdad a Vinted — la publicación automática por
el trabajador en segundo plano (`auto_publish`) es un flag aparte, opt-in,
desde el dashboard.

Un member solo ve y toca los anuncios de sus propias cuentas; un admin, los
de todas (`_owned_listing` es la única puerta de entrada a un anuncio por id).
"""

import uuid
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from src.ai.listing_writer import build_listing_draft
from src.ai.providers import AIProvider
from src.core.logger import logger
from src.core.settings import Settings
from src.core.users import User
from src.storage import accounts_store, listings_store, sales_store
from src.ui.deps import (
    get_ai_provider,
    get_api_client_factory,
    get_current_user,
    get_db_path,
    get_session_client_factory,
    get_settings,
    owner_filter_for,
    redirect_with_message,
    require_login,
)
from src.vinted.api_client import VintedApiClient
from src.vinted.models import CONDITION_LABELS_ES, Listing, Sale, VintedAccount
from src.vinted.session_client import VintedSessionClient
from src.worker.scheduler import publish_listing_now, publish_listing_via_api

router = APIRouter(dependencies=[Depends(require_login)])


def _photos_dir(settings: Settings) -> Path:
    return Path(settings.database_path).parent / "photos"


def _owned_listing(db_path: str, listing_id: int, user: User) -> tuple[Listing, VintedAccount] | None:
    """El anuncio y su cuenta si existen Y son del usuario (o si es admin); si no, `None`."""
    listing = listings_store.get_listing(db_path, listing_id)
    if listing is None:
        return None
    account = accounts_store.get_account(db_path, listing.account_id)
    if account is None:
        return None
    if user.role != "admin" and account.owner_user_id != user.id:
        return None
    return listing, account


@router.get("/listings")
def list_listings_view(request: Request, db_path: str = Depends(get_db_path), user: User = Depends(get_current_user)):
    templates = request.app.state.templates
    accounts = {a.id: a for a in accounts_store.list_accounts(db_path, owner_user_id=owner_filter_for(user))}
    visible_listings = [
        listing for listing in listings_store.list_listings(db_path) if listing.account_id in accounts
    ]
    return templates.TemplateResponse(
        request,
        "listings.html",
        {
            "active": "listings",
            "current_user": user,
            "listings": visible_listings,
            "accounts": accounts,
            "ok": request.query_params.get("ok"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/listings/new")
def new_listing_form(request: Request, db_path: str = Depends(get_db_path), user: User = Depends(get_current_user)):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "listing_new.html",
        {
            "active": "listings",
            "current_user": user,
            "accounts": accounts_store.list_accounts(db_path, owner_user_id=owner_filter_for(user)),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/listings/generate")
async def generate_listing(
    account_id: int = Form(...),
    price: float = Form(...),
    min_price: float = Form(...),
    extra_context: str = Form(""),
    photos: list[UploadFile] = File(...),
    db_path: str = Depends(get_db_path),
    settings: Settings = Depends(get_settings),
    ai_provider: AIProvider = Depends(get_ai_provider),
    user: User = Depends(get_current_user),
):
    account = accounts_store.get_account(db_path, account_id)
    if account is None or (user.role != "admin" and account.owner_user_id != user.id):
        return redirect_with_message("/listings/new", error="Cuenta no encontrada")

    raw_photos = []
    for photo in photos:
        if not photo.filename:
            continue
        content = await photo.read()
        if content:  # un input de archivo vacío (o un adjunto corrupto) no debe tumbar la petición
            raw_photos.append(content)
    if not raw_photos:
        return redirect_with_message("/listings/new", error="Sube al menos una foto válida")

    draft = build_listing_draft(ai_provider, raw_photos, extra_context=extra_context)

    listing_dir = _photos_dir(settings) / uuid.uuid4().hex
    listing_dir.mkdir(parents=True, exist_ok=True)
    photo_paths = []
    for index, raw in enumerate(raw_photos):
        path = listing_dir / f"{index}.jpg"
        path.write_bytes(raw)
        photo_paths.append(str(path))

    listing = listings_store.create_listing(
        db_path,
        Listing(
            account_id=account_id,
            title=draft.title,
            description=draft.description,
            category=draft.category,
            brand=draft.brand,
            size=draft.size,
            item_condition=draft.item_condition,
            price=price,
            min_price=min_price,
            photo_paths=photo_paths,
            ai_generated=True,
        ),
    )
    return redirect_with_message(f"/listings/{listing.id}/edit", ok="Borrador generado, revísalo antes de publicar")


@router.get("/listings/{listing_id}/photos/{index}")
def get_listing_photo(
    listing_id: int, index: int, db_path: str = Depends(get_db_path), user: User = Depends(get_current_user)
):
    """Sirve una foto ya subida — detrás de login, a diferencia de un `StaticFiles` suelto.

    Las fotos de un anuncio pueden incluir detalles del vendedor (matrículas,
    caras, direcciones de fondo); no tiene sentido que naveguen sin sesión
    cuando el resto del panel entero exige login, ni que las vea nadie que
    no sea el dueño de la cuenta (o un admin).
    """
    owned = _owned_listing(db_path, listing_id, user)
    if owned is None:
        raise HTTPException(status_code=404)
    listing, _account = owned
    if not (0 <= index < len(listing.photo_paths)):
        raise HTTPException(status_code=404)
    return FileResponse(listing.photo_paths[index], media_type="image/jpeg")


@router.get("/listings/{listing_id}/edit")
def edit_listing_form(
    request: Request, listing_id: int, db_path: str = Depends(get_db_path), user: User = Depends(get_current_user)
):
    templates = request.app.state.templates
    owned = _owned_listing(db_path, listing_id, user)
    if owned is None:
        return redirect_with_message("/listings", error="Anuncio no encontrado")
    listing, account = owned

    photo_urls = [f"/listings/{listing.id}/photos/{i}" for i in range(len(listing.photo_paths))]

    return templates.TemplateResponse(
        request,
        "listing_edit.html",
        {
            "active": "listings",
            "current_user": user,
            "listing": listing,
            "photo_urls": photo_urls,
            "account": account,
            "conditions": CONDITION_LABELS_ES,
            "ok": request.query_params.get("ok"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/listings/{listing_id}")
def update_listing(
    listing_id: int,
    title: str = Form(...),
    description: str = Form(""),
    category: str = Form(""),
    brand: str = Form(""),
    size: str = Form(""),
    item_condition: str = Form(""),
    price: float = Form(...),
    min_price: float = Form(...),
    db_path: str = Depends(get_db_path),
    user: User = Depends(get_current_user),
):
    if _owned_listing(db_path, listing_id, user) is None:
        return redirect_with_message("/listings", error="Anuncio no encontrado")

    listings_store.update_listing_fields(
        db_path,
        listing_id,
        title=title,
        description=description,
        category=category or None,
        brand=brand or None,
        size=size or None,
        item_condition=item_condition or None,
        price=price,
        min_price=min_price,
    )
    return redirect_with_message(f"/listings/{listing_id}/edit", ok="Cambios guardados")


@router.post("/listings/{listing_id}/publish")
async def publish_listing_route(
    listing_id: int,
    db_path: str = Depends(get_db_path),
    settings: Settings = Depends(get_settings),
    session_client_factory: Callable[[str, str], VintedSessionClient] = Depends(get_session_client_factory),
    api_client_factory: Callable[[Settings], VintedApiClient] = Depends(get_api_client_factory),
    user: User = Depends(get_current_user),
):
    owned = _owned_listing(db_path, listing_id, user)
    edit_url = f"/listings/{listing_id}/edit"
    if owned is None:
        return redirect_with_message("/listings", error="Anuncio no encontrado")
    listing, account = owned
    if not listing.title or not listing.photo_paths or not listing.min_price:
        return redirect_with_message(edit_url, error="Completa título, fotos y precio mínimo antes de publicar")

    if account.connection_mode == "session":
        cookie = accounts_store.get_account_session_cookie(db_path, account.id)
        if not cookie:
            return redirect_with_message(edit_url, error="La cuenta no tiene una sesión guardada")
        client = session_client_factory(settings.vinted_domain, cookie)
        try:
            blocked = await publish_listing_now(db_path, account, listing, client, settings)
        except Exception as error:  # noqa: BLE001 — cualquier fallo al hablar con Vinted se trata igual de cara al usuario
            return _publish_failure_redirect(db_path, account, edit_url, error)
        finally:
            await client.aclose()
    elif account.connection_mode == "api":
        if not settings.vinted_api_client_id or not settings.vinted_api_client_secret:
            return redirect_with_message(
                edit_url, error="Faltan las credenciales de la API oficial en Ajustes"
            )
        api_client = api_client_factory(settings)
        try:
            blocked = await publish_listing_via_api(db_path, account, listing, api_client, settings)
        except Exception as error:  # noqa: BLE001
            return _publish_failure_redirect(db_path, account, edit_url, error)
        finally:
            await api_client.aclose()
    else:
        return redirect_with_message(edit_url, error=f"Vía de conexión desconocida: {account.connection_mode}")

    if blocked is not None:
        return redirect_with_message(edit_url, error=f"Bloqueado por el ritmo seguro: {blocked.reason}")
    # Si venía marcada como error de un fallo anterior, esta publicación
    # correcta demuestra que la sesión vuelve a funcionar.
    if account.status != "connected":
        accounts_store.update_account_status(db_path, account.id, "connected")
    return redirect_with_message(edit_url, ok="Anuncio publicado")


def _publish_failure_redirect(db_path: str, account: VintedAccount, edit_url: str, error: Exception):
    """Vinted rechazó la petición (sesión caducada, token inválido...) o no hubo red.

    Nunca debe llegar como un 500 sin más: quien lo ve es la persona que
    acaba de pulsar "Publicar ahora", no alguien mirando logs. Además se
    marca la cuenta como "error" — sin esto, el dashboard seguiría diciendo
    "Conectada" indefinidamente aunque la sesión ya no sirva para nada.
    """
    logger.warning(f"Fallo al publicar en Vinted (cuenta {account.id}): {error}")
    accounts_store.update_account_status(db_path, account.id, "error")
    return redirect_with_message(edit_url, error=f"Vinted rechazó la publicación: {error}")


@router.post("/listings/{listing_id}/sold")
def mark_sold_route(
    listing_id: int,
    sale_amount: float = Form(...),
    db_path: str = Depends(get_db_path),
    user: User = Depends(get_current_user),
):
    """Marca un anuncio publicado como vendido y registra la venta.

    Sin esto, `src/compliance/dac7.py` nunca tendría datos reales que
    evaluar: es el único sitio del panel que crea una fila en `sales`.
    """
    owned = _owned_listing(db_path, listing_id, user)
    if owned is None:
        return redirect_with_message("/listings", error="Anuncio no encontrado")
    listing, _account = owned
    if listing.status != "published":
        return redirect_with_message(
            f"/listings/{listing_id}/edit", error="Solo se puede marcar como vendido un anuncio publicado"
        )
    if sale_amount <= 0:
        return redirect_with_message(f"/listings/{listing_id}/edit", error="El importe de venta debe ser mayor que cero")

    listings_store.mark_sold(db_path, listing_id)
    sales_store.record_sale(
        db_path, Sale(account_id=listing.account_id, listing_id=listing_id, sale_amount=sale_amount)
    )
    return redirect_with_message(f"/listings/{listing_id}/edit", ok="Anuncio marcado como vendido")


@router.post("/listings/{listing_id}/delete")
def delete_listing_route(
    listing_id: int, db_path: str = Depends(get_db_path), user: User = Depends(get_current_user)
):
    if _owned_listing(db_path, listing_id, user) is None:
        return redirect_with_message("/listings", error="Anuncio no encontrado")
    listings_store.delete_listing(db_path, listing_id)
    return redirect_with_message("/listings", ok="Anuncio borrado")
