"""Errores comunes de los clientes de Vinted."""

import httpx


class VintedApiError(Exception):
    """Una petición a Vinted (vía oficial o de sesión) devolvió un error."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def raise_for_status(response: httpx.Response, context: str) -> None:
    """Traduce un status HTTP de error en `VintedApiError` con contexto legible."""
    if response.status_code >= 400:
        raise VintedApiError(
            f"{context} falló con {response.status_code}: {response.text[:300]}",
            status_code=response.status_code,
        )
