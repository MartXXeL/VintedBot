"""Lectura/escritura del archivo `.env`, preservando comentarios y orden.

Usado por la pantalla de Ajustes del panel: permite editar las variables de
entorno (incluidas las credenciales del propio panel) sin perder el resto del
archivo ni sus comentarios explicativos.
"""

from dataclasses import dataclass
from pathlib import Path

_SECRET_HINTS = ("PASS", "TOKEN", "KEY", "HASH", "SESSION", "SECRET")


@dataclass
class _EnvLine:
    raw: str
    key: str | None = None
    value: str | None = None


def _read_lines(path: str | Path) -> list[_EnvLine]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    lines: list[_EnvLine] = []
    for raw in file_path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _, value = stripped.partition("=")
            lines.append(_EnvLine(raw=raw, key=key.strip(), value=value.strip()))
        else:
            lines.append(_EnvLine(raw=raw))
    return lines


def read_env_pairs(path: str | Path) -> list[tuple[str, str]]:
    """Devuelve las variables definidas en `.env`, en el orden en que aparecen."""
    return [(line.key, line.value) for line in _read_lines(path) if line.key]


def is_secret_key(key: str) -> bool:
    """True si el nombre de la variable sugiere un valor sensible (para ocultarlo en la UI)."""
    upper = key.upper()
    return any(hint in upper for hint in _SECRET_HINTS)


def update_env_file(path: str | Path, updates: dict[str, str]) -> None:
    """Actualiza/añade las claves de `updates` en `.env`, preservando comentarios,
    líneas en blanco y el resto de variables tal cual."""
    lines = _read_lines(path)
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        if line.key and line.key in updates:
            out.append(f"{line.key}={updates[line.key]}")
            seen.add(line.key)
        else:
            out.append(line.raw)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    Path(path).write_text("\n".join(out) + "\n", encoding="utf-8")
