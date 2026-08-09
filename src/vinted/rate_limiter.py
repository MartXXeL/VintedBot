"""Limitador de ritmo de la vía de sesión: protege las cuentas conectadas.

Vinted no ofrece una vía oficial gratuita para mensajería ni ofertas (ver
README), así que la publicación y la negociación por sesión son la única
opción para esa parte y arrastran un riesgo real y documentado de
suspensión (24-72h) o shadowban (7-14 días) si se automatizan sin freno.

Este módulo NO intenta evadir la detección de Vinted (no hay proxies, no hay
huellas de navegador falsas, no hay nada pensado para parecer "más humano" de
lo que es): es justo lo contrario, un freno deliberadamente conservador —
igual o más estricto que la cadencia seguridad documentada — que existe para
que el propio usuario no se dispare en el pie con su propia cuenta.

Tres frenos independientes, cualquiera de los tres basta para bloquear:
1. Pausa nocturna configurable (por defecto 23:00-08:00).
2. Tope de acciones en una ventana móvil de 24 horas (por defecto 50).
3. Cadencia mínima entre acciones consecutivas (por defecto 180-600s; el
   límite duro que se COMPRUEBA es el mínimo, el máximo se usa solo para
   elegir cuánto esperar antes de la siguiente acción programada).
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.core.settings import RateLimitSettings


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    reason: str | None = None
    retry_at: datetime | None = None


def _in_night_pause(now: datetime, settings: RateLimitSettings) -> bool:
    start, end = settings.night_start_hour, settings.night_end_hour
    if start == end:
        return False  # ventana de 0 horas: pausa nocturna desactivada
    if start < end:
        return start <= now.hour < end
    return now.hour >= start or now.hour < end  # cruza medianoche (p. ej. 23 -> 8)


def _next_night_end(now: datetime, settings: RateLimitSettings) -> datetime:
    candidate = now.replace(hour=settings.night_end_hour, minute=0, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def check_rate_limit(
    now: datetime,
    actions_last_24h: Sequence[datetime],
    settings: RateLimitSettings,
) -> RateLimitDecision:
    """Decide si se puede realizar una acción AHORA para una cuenta.

    `actions_last_24h` son los instantes (cualquier orden) de las acciones ya
    realizadas por esa cuenta en las últimas 24 horas — lo calcula quien
    llama (normalmente leyendo `actions_log`, ver `src/storage/`).

    Se comprueban los tres frenos en orden y se devuelve en cuanto uno
    bloquea; no es necesario combinar retry_at de varios frenos porque, sea
    cual sea el resultado, quien automatiza debe volver a llamar a
    `check_rate_limit` antes de cada acción (nunca fiarse de un `retry_at`
    calculado de antemano para encadenar acciones sin comprobar de nuevo).
    """
    if _in_night_pause(now, settings):
        return RateLimitDecision(
            allowed=False,
            reason="pausa nocturna",
            retry_at=_next_night_end(now, settings),
        )

    if len(actions_last_24h) >= settings.max_actions_per_day:
        oldest = min(actions_last_24h)
        return RateLimitDecision(
            allowed=False,
            reason=f"tope diario alcanzado ({settings.max_actions_per_day} acciones/24h)",
            retry_at=oldest + timedelta(hours=24),
        )

    if actions_last_24h:
        last_action_at = max(actions_last_24h)
        elapsed = (now - last_action_at).total_seconds()
        if elapsed < settings.min_seconds:
            return RateLimitDecision(
                allowed=False,
                reason=f"cadencia mínima no cumplida ({settings.min_seconds}s)",
                retry_at=last_action_at + timedelta(seconds=settings.min_seconds),
            )

    return RateLimitDecision(allowed=True)


def pick_next_delay_seconds(settings: RateLimitSettings) -> float:
    """Elige cuánto esperar antes de la siguiente acción programada.

    Un valor fijo pegado siempre al mínimo concentraría todas las acciones de
    todas las cuentas justo en el borde del margen documentado como seguro;
    variar dentro del rango completo (`min_seconds`-`max_seconds`) reparte
    las acciones a lo largo de la ventana en vez de acumularlas en el límite.
    """
    return random.uniform(settings.min_seconds, settings.max_seconds)
