"""Bloqueo por fuerza bruta en el login: N intentos fallidos, bloqueo temporal por IP."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

_DEFAULT_MAX_ATTEMPTS = 5
_DEFAULT_LOCKOUT = timedelta(minutes=5)


@dataclass
class LoginGuard:
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS
    lockout: timedelta = _DEFAULT_LOCKOUT
    _failures: dict[str, list[datetime]] = field(default_factory=dict)

    def _recent_failures(self, ip: str) -> list[datetime]:
        cutoff = datetime.now() - self.lockout
        recent = [t for t in self._failures.get(ip, []) if t > cutoff]
        self._failures[ip] = recent
        return recent

    def is_locked_out(self, ip: str) -> bool:
        return len(self._recent_failures(ip)) >= self.max_attempts

    def register_failure(self, ip: str) -> None:
        recent = self._recent_failures(ip)
        recent.append(datetime.now())
        self._failures[ip] = recent

    def register_success(self, ip: str) -> None:
        self._failures.pop(ip, None)
