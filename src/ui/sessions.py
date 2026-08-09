"""Sesiones del panel: un token opaco por login, guardado en memoria.

Nada de JWT ni de cookies autofirmadas: el panel es de un solo operador y
corre en local, así que un diccionario en memoria (token aleatorio -> caduca
en) es toda la complejidad que hace falta. Reiniciar el proceso cierra todas
las sesiones, que es justo lo que se espera de un panel así.
"""

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta

_DEFAULT_TTL = timedelta(hours=12)


@dataclass
class SessionStore:
    ttl: timedelta = _DEFAULT_TTL
    _sessions: dict[str, datetime] = field(default_factory=dict)

    def create(self) -> str:
        token = secrets.token_urlsafe(32)
        self._sessions[token] = datetime.now() + self.ttl
        return token

    def is_valid(self, token: str | None) -> bool:
        if not token:
            return False
        expires_at = self._sessions.get(token)
        if expires_at is None:
            return False
        if datetime.now() > expires_at:
            del self._sessions[token]
            return False
        return True

    def invalidate(self, token: str | None) -> None:
        if token:
            self._sessions.pop(token, None)
