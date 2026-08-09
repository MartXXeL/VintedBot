"""Umbrales del motor de negociación.

Valores por defecto tal y como se plantea la idea original: aceptar a partir
del 75% del precio mínimo, contraofertar entre el 40% y el 75%, y rechazar
por debajo del 40%. Configurables por si un vendedor quiere ser más o menos
agresivo, pero con estos valores como punto de partida razonable.
"""

from dataclasses import dataclass
from typing import Literal

CounterStrategy = Literal["midpoint"]


@dataclass(frozen=True)
class NegotiationPolicy:
    accept_ratio: float = 0.75
    reject_ratio: float = 0.40
    counter_strategy: CounterStrategy = "midpoint"

    def __post_init__(self) -> None:
        if not (0.0 <= self.reject_ratio < self.accept_ratio <= 1.0):
            raise ValueError(
                "reject_ratio debe ser menor que accept_ratio, y ambos estar entre 0 y 1"
            )


DEFAULT_POLICY = NegotiationPolicy()
