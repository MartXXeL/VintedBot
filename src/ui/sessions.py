"""Sesiones del panel: un token opaco por login, atado a un usuario, en memoria.

Nada de JWT ni de cookies autofirmadas: un diccionario en memoria (token
aleatorio -> a quién pertenece y cuándo caduca) es toda la complejidad que
hace falta para un panel con pocos usuarios. Reiniciar el proceso cierra
todas las sesiones, que es justo lo que se espera de un panel así.
"""

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta

_DEFAULT_TTL = timedelta(hours=12)


@dataclass(frozen=True)
class _SessionRecord:
    user_id: int
    expires_at: datetime


@dataclass
class SessionStore:
    ttl: timedelta = _DEFAULT_TTL
    _sessions: dict[str, _SessionRecord] = field(default_factory=dict)

    def create(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        self._sessions[token] = _SessionRecord(user_id=user_id, expires_at=datetime.now() + self.ttl)
        return token

    def get_user_id(self, token: str | None) -> int | None:
        """El `user_id` de una sesión válida, o `None` si no hay sesión (o ha caducado)."""
        if not token:
            return None
        record = self._sessions.get(token)
        if record is None:
            return None
        if datetime.now() > record.expires_at:
            del self._sessions[token]
            return None
        return record.user_id

    def is_valid(self, token: str | None) -> bool:
        return self.get_user_id(token) is not None

    def invalidate(self, token: str | None) -> None:
        if token:
            self._sessions.pop(token, None)
