import io

import pytest
from PIL import Image

from src.ai.listing_writer import build_listing_draft
from src.ai.providers import MockAIProvider


def _fake_photo(width: int = 800, height: int = 600) -> bytes:
    image = Image.new("RGB", (width, height), (100, 150, 200))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_build_listing_draft_preprocesa_y_delega_en_el_proveedor() -> None:
    draft = build_listing_draft(MockAIProvider(), [_fake_photo(3000, 2000)])
    assert draft.title


def test_build_listing_draft_sin_fotos_lanza_error() -> None:
    with pytest.raises(ValueError):
        build_listing_draft(MockAIProvider(), [])


def test_build_listing_draft_pasa_el_contexto_extra() -> None:
    calls = {}

    class _SpyProvider(MockAIProvider):
        def generate_listing(self, photos_jpeg, extra_context=""):
            calls["extra_context"] = extra_context
            return super().generate_listing(photos_jpeg, extra_context)

    build_listing_draft(_SpyProvider(), [_fake_photo()], extra_context="Comprado en 2023, apenas usado")
    assert calls["extra_context"] == "Comprado en 2023, apenas usado"
