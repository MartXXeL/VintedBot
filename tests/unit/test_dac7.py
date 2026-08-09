from datetime import datetime

from src.compliance.dac7 import evaluate_dac7
from src.core.settings import Dac7Settings
from src.vinted.models import Sale

SETTINGS = Dac7Settings(alert_amount_eur=2000.0, alert_transactions=30)


def _sale(account_id: int, amount: float, year: int = 2026, month: int = 6) -> Sale:
    return Sale(account_id=account_id, sale_amount=amount, sold_at=datetime(year, month, 15))


def test_por_debajo_de_ambos_umbrales_no_requiere_reporte() -> None:
    sales = [_sale(1, 100) for _ in range(5)]
    status = evaluate_dac7(1, sales, 2026, SETTINGS)
    assert not status.reporting_required
    assert status.total_amount == 500
    assert status.total_transactions == 5


def test_supera_el_umbral_de_importe() -> None:
    sales = [_sale(1, 1000), _sale(1, 1500)]  # 2500€, 2 transacciones
    status = evaluate_dac7(1, sales, 2026, SETTINGS)
    assert status.reporting_required
    assert "2000" in status.reason or "€" in status.reason


def test_supera_el_umbral_de_transacciones_aunque_el_importe_sea_bajo() -> None:
    sales = [_sale(1, 10) for _ in range(30)]  # 300€, 30 transacciones
    status = evaluate_dac7(1, sales, 2026, SETTINGS)
    assert status.reporting_required
    assert "transacciones" in status.reason


def test_justo_en_el_umbral_de_importe_no_dispara_reporte() -> None:
    """El umbral real es "supera" 2.000€ (no "alcanza"): exactamente 2.000€ no reporta."""
    sales = [_sale(1, 2000)]
    status = evaluate_dac7(1, sales, 2026, SETTINGS)
    assert not status.reporting_required


def test_justo_en_el_umbral_de_transacciones_si_dispara_reporte() -> None:
    """A diferencia del importe, el umbral de transacciones es "30 o más"."""
    sales = [_sale(1, 1) for _ in range(30)]
    status = evaluate_dac7(1, sales, 2026, SETTINGS)
    assert status.reporting_required


def test_acercandose_al_umbral_marca_approaching() -> None:
    sales = [_sale(1, 1700)]  # 85% de 2000
    status = evaluate_dac7(1, sales, 2026, SETTINGS)
    assert not status.reporting_required
    assert status.approaching


def test_filtra_por_cuenta() -> None:
    sales = [_sale(1, 3000), _sale(2, 10)]
    status = evaluate_dac7(2, sales, 2026, SETTINGS)
    assert not status.reporting_required
    assert status.total_amount == 10


def test_filtra_por_anio() -> None:
    sales = [_sale(1, 3000, year=2025), _sale(1, 10, year=2026)]
    status = evaluate_dac7(1, sales, 2026, SETTINGS)
    assert status.total_amount == 10
    assert not status.reporting_required
