"""Cifrado en reposo de los campos sensibles guardados en `data/vintedbot.db`.

La base de datos guarda cosas que no deben quedar en texto plano ni siquiera
estando ya fuera del control de versiones (`data/` está en `.gitignore`, pero
el archivo sigue viviendo en disco): la sesión/cookies de cada cuenta de
Vinted conectada, y el **precio mínimo** de cada anuncio — que es justo el
dato que el motor de negociación debe poder leer pero la IA nunca debe ver
sin cifrar en un log o volcado accidental.

Cifrado simétrico (Fernet, AES-128 + HMAC) con una clave guardada en `.env`:
si el archivo `.db` se copia o se filtra sin la clave, su contenido es
ilegible.
"""

import contextlib
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from src.core.env_file import read_env_pairs, update_env_file

_ENV_KEY_NAME = "DB_ENCRYPTION_KEY"
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

_fernet: Fernet | None = None


def _load_or_create_key() -> bytes:
    """Lee la clave de `.env`; si no existe, genera una nueva y la persiste.

    Se busca primero en `os.environ` (caso normal: `main.py` ya hizo
    `load_dotenv()`) y si no está ahí, se lee el archivo `.env` directamente
    antes de generar una clave nueva: un script que no llama a `load_dotenv()`
    (p. ej. un test) no debe pisar la clave real con una nueva cada vez que se
    ejecuta, o los datos cifrados con la clave anterior quedan ilegibles.
    """
    existing = os.getenv(_ENV_KEY_NAME)
    if existing:
        return existing.encode("utf-8")

    for key_name, value in read_env_pairs(_ENV_PATH):
        if key_name == _ENV_KEY_NAME and value:
            os.environ[_ENV_KEY_NAME] = value
            return value.encode("utf-8")

    key = Fernet.generate_key()
    # Sin .env escribible: se cifra igual, solo que con una clave que no sobrevive al reinicio.
    with contextlib.suppress(OSError):
        update_env_file(_ENV_PATH, {_ENV_KEY_NAME: key.decode("utf-8")})
    os.environ[_ENV_KEY_NAME] = key.decode("utf-8")
    return key


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_or_create_key())
    return _fernet


def reset_fernet_cache() -> None:
    """Fuerza a releer la clave en la siguiente llamada (usado por los tests)."""
    global _fernet
    _fernet = None


def encrypt_text(value: str | None) -> str | None:
    """Cifra una cadena para guardarla en la base de datos. `None` se conserva tal cual."""
    if value is None:
        return None
    return _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_text(value: str | None) -> str | None:
    """Descifra una cadena leída de la base de datos.

    Si el valor no está cifrado (filas escritas antes de añadir este cifrado,
    o un valor ya en claro) se devuelve tal cual en vez de fallar.
    """
    if value is None:
        return None
    try:
        return _get_fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return value
