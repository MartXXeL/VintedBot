"""Orquesta la generación de un anuncio: preprocesa fotos y llama al proveedor de IA."""

from src.ai.image_prep import prepare_image_for_ai
from src.ai.providers import AIProvider
from src.vinted.models import ListingDraftFields


def build_listing_draft(
    provider: AIProvider, raw_photos: list[bytes], extra_context: str = ""
) -> ListingDraftFields:
    """Genera el borrador de un anuncio a partir de las fotos originales (sin preprocesar).

    Las fotos se redimensionan/recomprimen (`prepare_image_for_ai`) ANTES de
    llegar al proveedor: así el coste de tokens y las reglas de tamaño son
    iguales sin importar qué proveedor esté activo.
    """
    if not raw_photos:
        raise ValueError("Hace falta al menos una foto para generar un anuncio")
    prepared = [prepare_image_for_ai(photo) for photo in raw_photos]
    return provider.generate_listing(prepared, extra_context=extra_context)
