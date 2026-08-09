"""Fixtures compartidas por los tests unitarios."""

import os

import pytest

from src.storage import crypto


@pytest.fixture(autouse=True)
def _clave_de_cifrado_aislada(tmp_path, monkeypatch):
    """Cada test usa su propia clave Fernet y su propio `.env` de prueba.

    Sin esto, cualquier test que pase por `src/storage/crypto.py` (todos los
    stores que cifran algo en reposo) leería/escribiría la clave real del
    proyecto — o fallaría si no hay `.env` escribible en el entorno de CI.
    """
    monkeypatch.setattr(crypto, "_ENV_PATH", tmp_path / ".env")
    monkeypatch.delenv("DB_ENCRYPTION_KEY", raising=False)
    crypto.reset_fernet_cache()
    yield
    crypto.reset_fernet_cache()
    os.environ.pop("DB_ENCRYPTION_KEY", None)
