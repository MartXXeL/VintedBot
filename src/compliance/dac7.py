"""Seguimiento del régimen fiscal europeo DAC7 (Directiva (UE) 2021/514).

Las plataformas digitales (Vinted incluida) están obligadas a reportar a la
Agencia Tributaria los datos de un vendedor cuando, en un año natural, supera
**cualquiera** de los dos umbrales: 30 transacciones o 2.000€ de ingresos
(el vendedor queda excluido del reporte solo si está por DEBAJO de los dos a
la vez). Este módulo solo avisa con antelación para que el vendedor no se
lleve la sorpresa en enero — no presenta nada ante Hacienda ni sustituye
asesoría fiscal (ver el aviso en el README).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from src.core.settings import Dac7Settings
from src.vinted.models import Sale

_APPROACHING_RATIO = 0.8


@dataclass(frozen=True)
class Dac7Status:
    account_id: int
    year: int
    total_amount: float
    total_transactions: int
    reporting_required: bool
    approaching: bool
    reason: str


def evaluate_dac7(
    account_id: int,
    sales: Sequence[Sale],
    year: int,
    settings: Dac7Settings,
) -> Dac7Status:
    """Calcula el estado DAC7 de una cuenta para un año natural dado.

    `sales` puede venir sin filtrar (de varias cuentas/años); aquí se filtra
    por `account_id` y por `year` a partir de `sold_at`.
    """
    year_sales = [s for s in sales if s.account_id == account_id and s.sold_at.year == year]
    total_amount = sum(s.sale_amount for s in year_sales)
    total_transactions = len(year_sales)

    over_amount = total_amount > settings.alert_amount_eur
    over_transactions = total_transactions >= settings.alert_transactions
    reporting_required = over_amount or over_transactions

    if reporting_required:
        reason = _required_reason(over_amount, over_transactions, settings)
        approaching = False
    else:
        approaching = (
            total_amount >= settings.alert_amount_eur * _APPROACHING_RATIO
            or total_transactions >= settings.alert_transactions * _APPROACHING_RATIO
        )
        reason = "acercándose a los umbrales de reporte" if approaching else "por debajo de los umbrales"

    return Dac7Status(
        account_id=account_id,
        year=year,
        total_amount=total_amount,
        total_transactions=total_transactions,
        reporting_required=reporting_required,
        approaching=approaching,
        reason=reason,
    )


def _required_reason(over_amount: bool, over_transactions: bool, settings: Dac7Settings) -> str:
    if over_amount and over_transactions:
        return (
            f"supera los {settings.alert_amount_eur:.0f}€ y las "
            f"{settings.alert_transactions} transacciones anuales"
        )
    if over_amount:
        return f"supera los {settings.alert_amount_eur:.0f}€ anuales"
    return f"supera las {settings.alert_transactions} transacciones anuales"
