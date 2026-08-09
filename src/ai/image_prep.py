"""Preprocesado de fotos antes de mandarlas a la IA.

Una foto de móvil moderna (4000×3000px o más) no aporta nada extra a un
modelo de visión frente a una versión mucho más pequeña, y sí que dispara el
número de tokens de entrada (y por tanto el coste — ver
`src/billing/plans.py::estimate_ai_cost_usd`). 1568px de lado largo es el
tamaño a partir del cual Claude deja de "ver" más detalle: por encima de eso
solo se paga más por lo mismo.
"""

import io

from PIL import Image, ImageOps

MAX_LONG_EDGE_PX = 1568
JPEG_QUALITY = 85


def prepare_image_for_ai(raw_bytes: bytes, max_long_edge: int = MAX_LONG_EDGE_PX) -> bytes:
    """Redimensiona (si hace falta) y recomprime una foto a JPEG.

    - Aplica la orientación EXIF antes de medir/recortar (una foto vertical
      tomada con el móvil de lado no debe llegar apaisada a la IA).
    - Nunca AGRANDA una foto ya pequeña: solo reduce.
    - Convierte a RGB (una PNG con transparencia rompería el encoder JPEG).
    """
    with Image.open(io.BytesIO(raw_bytes)) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode != "RGB":
            image = image.convert("RGB")

        longest_edge = max(image.size)
        if longest_edge > max_long_edge:
            scale = max_long_edge / longest_edge
            new_size = (round(image.width * scale), round(image.height * scale))
            image = image.resize(new_size, Image.LANCZOS)

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return buffer.getvalue()
