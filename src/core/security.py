"""Hash de las contraseñas de los usuarios del panel (PBKDF2-HMAC-SHA256, solo librería estándar).

No es cifrado reversible como `src/storage/crypto.py` (eso protege datos que
hay que poder volver a leer, como el precio mínimo o la sesión de Vinted):
una contraseña solo hace falta poder VERIFICARLA, nunca recuperarla, así que
se guarda un hash de un solo sentido en `users.password_hash`
(`src/storage/users_store.py`). Así, aunque alguien copie la base de datos,
no obtiene ninguna contraseña en claro.
"""

import base64
import hashlib
import hmac
import os

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    """Devuelve un hash autocontenido (algoritmo + iteraciones + sal + hash)
    listo para guardar en `users.password_hash`."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_ALGO}${_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored_hash: str | None) -> bool:
    """Comprueba `password` contra un hash generado por `hash_password`.

    `hmac.compare_digest` evita que el tiempo de respuesta filtre cuántos
    bytes del hash coinciden (ataque de canal lateral por temporización)."""
    if not stored_hash:
        return False
    try:
        algo, iterations_text, salt_b64, hash_b64 = stored_hash.split("$")
        if algo != _ALGO:
            return False
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, TypeError):
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)


def generate_random_password(length: int = 16) -> str:
    """Genera una contraseña aleatoria para el primer arranque (se muestra una sola vez)."""
    alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(alphabet[b % len(alphabet)] for b in os.urandom(length))
