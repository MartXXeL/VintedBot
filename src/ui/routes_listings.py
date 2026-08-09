"""Anuncios: subir fotos, generar el borrador con IA, revisar/editar y publicar.

La IA solo PROPONE (`build_listing_draft`): el anuncio se guarda como
`draft` y el vendedor lo revisa/edita en `/listings/{id}/edit` antes de que
"Publicar ahora" lo mande de verdad a Vinted — la publicación automática por
el trabajador en segundo plano (`auto_publish`) es un flag aparte, opt-in,
desde el dashboard.
"""

import uuid
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from src.ai.listing_writer import build_listing_draft
from src.ai.providers import AIProvider
from src.core.settings import Settings
from src.storage import accounts_store, listings_store
from src.ui.deps import (
    get_ai_provider,
    get_db_path,
    get_session_client_factory,
    get_settings,
    redirect_with_message,
    require_login,
)
from src.vinted.models import CONDITION_LABELS_ES, Listing
from src.vinted.session_client import VintedSessionClient
from src.worker.scheduler import publish_listing_now

router = APIRouter(dependencies=[Depends(require_login)])


def _photos_dir(settings: Settings) -> Path:
    return Path(settings.database_path).parent / "photos"


@router.get("/listings")
def list_listings_view(request: Request, db_path: str = Depends(get_db_path)):
    templates = request.app.state.templates
    accounts = {a.id: a for a in accounts_store.list_accounts(db_path)}
    return templates.TemplateResponse(
        request,
        "listings.html",
        {
            "active": "listings",
            "listings": listings_store.list_listings(db_path),
            "accounts": accounts,
            "ok": request.query_params.get("ok"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/listings/new")
def new_listing_form(request: Request, db_path: str = Depends(get_db_path)):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "listing_new.html",
        {
            "active": "listings",
            "accounts": accounts_store.list_accounts(db_path),
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
):
    if accounts_store.get_account(db_path, account_id) is None:
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
def get_listing_photo(listing_id: int, index: int, db_path: str = Depends(get_db_path)):
    """Sirve una foto ya subida — detrás de login, a diferencia de un `StaticFiles` suelto.

    Las fotos de un anuncio pueden incluir detalles del vendedor (matrículas,
    caras, direcciones de fondo); no tiene sentido que naveguen sin sesión
    cuando el resto del panel entero exige login.
    """
    listing = listings_store.get_listing(db_path, listing_id)
    if listing is None or not (0 <= index < len(listing.photo_paths)):
        raise HTTPException(status_code=404)
    return FileResponse(listing.photo_paths[index], media_type="image/jpeg")


@router.get("/listings/{listing_id}/edit")
def edit_listing_form(request: Request, listing_id: int, db_path: str = Depends(get_db_path)):
    templates = request.app.state.templates
    listing = listings_store.get_listing(db_path, listing_id)
    if listing is None:
        return redirect_with_message("/listings", error="Anuncio no encontrado")

    photo_urls = [f"/listings/{listing.id}/photos/{i}" for i in range(len(listing.photo_paths))]

    return templates.TemplateResponse(
        request,
        "listing_edit.html",
        {
            "active": "listings",
            "listing": listing,
            "photo_urls": photo_urls,
            "account": accounts_store.get_account(db_path, listing.account_id),
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
):
    if listings_store.get_listing(db_path, listing_id) is None:
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
    client_factory: Callable[[str, str], VintedSessionClient] = Depends(get_session_client_factory),
):
    listing = listings_store.get_listing(db_path, listing_id)
    if listing is None:
        return redirect_with_message("/listings", error="Anuncio no encontrado")

    account = accounts_store.get_account(db_path, listing.account_id)
    edit_url = f"/listings/{listing_id}/edit"
    if account is None or account.connection_mode != "session":
        return redirect_with_message(edit_url, error="Publicar desde aquí solo funciona con cuentas de sesión")
    if not listing.title or not listing.photo_paths or not listing.min_price:
        return redirect_with_message(edit_url, error="Completa título, fotos y precio mínimo antes de publicar")
    cookie = accounts_store.get_account_session_cookie(db_path, account.id)
    if not cookie:
        return redirect_with_message(edit_url, error="La cuenta no tiene una sesión guardada")

    client = client_factory(settings.vinted_domain, cookie)
    try:
        blocked = await publish_listing_now(db_path, account, listing, client, settings)
    finally:
        await client.aclose()

    if blocked is not None:
        return redirect_with_message(edit_url, error=f"Bloqueado por el ritmo seguro: {blocked.reason}")
    return redirect_with_message(edit_url, ok="Anuncio publicado")


@router.post("/listings/{listing_id}/delete")
def delete_listing_route(listing_id: int, db_path: str = Depends(get_db_path)):
    listings_store.delete_listing(db_path, listing_id)
    return redirect_with_message("/listings", ok="Anuncio borrado")
