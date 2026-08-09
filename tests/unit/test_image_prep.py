import io

from PIL import Image

from src.ai.image_prep import prepare_image_for_ai


def _make_jpeg(width: int, height: int, mode: str = "RGB") -> bytes:
    image = Image.new(mode, (width, height), color=(200, 50, 50) if mode == "RGB" else 255)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG" if mode == "RGB" else "PNG")
    return buffer.getvalue()


def test_reduce_una_foto_grande_al_limite() -> None:
    original = _make_jpeg(3000, 2000)
    result = prepare_image_for_ai(original, max_long_edge=1568)

    with Image.open(io.BytesIO(result)) as resized:
        assert max(resized.size) <= 1568
        assert resized.format == "JPEG"


def test_no_agranda_una_foto_ya_pequena() -> None:
    original = _make_jpeg(400, 300)
    result = prepare_image_for_ai(original, max_long_edge=1568)

    with Image.open(io.BytesIO(result)) as unchanged:
        assert unchanged.size == (400, 300)


def test_conserva_la_proporcion_al_reducir() -> None:
    original = _make_jpeg(4000, 1000)  # 4:1
    result = prepare_image_for_ai(original, max_long_edge=1568)

    with Image.open(io.BytesIO(result)) as resized:
        width, height = resized.size
        assert width == 1568
        assert abs(width / height - 4.0) < 0.05


def test_convierte_png_con_transparencia_a_rgb() -> None:
    image = Image.new("RGBA", (200, 200), (10, 20, 30, 128))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    result = prepare_image_for_ai(buffer.getvalue())

    with Image.open(io.BytesIO(result)) as converted:
        assert converted.mode == "RGB"
        assert converted.format == "JPEG"
