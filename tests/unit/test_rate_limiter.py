from datetime import datetime, timedelta

from src.core.settings import RateLimitSettings
from src.vinted.rate_limiter import check_rate_limit, pick_next_delay_seconds

SETTINGS = RateLimitSettings(
    min_seconds=180,
    max_seconds=600,
    max_actions_per_day=50,
    night_start_hour=23,
    night_end_hour=8,
)


def test_permite_la_primera_accion_sin_historial() -> None:
    now = datetime(2026, 8, 9, 12, 0, 0)
    decision = check_rate_limit(now, [], SETTINGS)
    assert decision.allowed


def test_bloquea_por_pausa_nocturna_pasada_medianoche() -> None:
    now = datetime(2026, 8, 9, 2, 0, 0)  # 02:00, dentro de 23:00-08:00
    decision = check_rate_limit(now, [], SETTINGS)
    assert not decision.allowed
    assert "nocturna" in decision.reason
    assert decision.retry_at == datetime(2026, 8, 9, 8, 0, 0)


def test_bloquea_por_pausa_nocturna_antes_de_medianoche() -> None:
    now = datetime(2026, 8, 9, 23, 30, 0)
    decision = check_rate_limit(now, [], SETTINGS)
    assert not decision.allowed
    assert decision.retry_at == datetime(2026, 8, 10, 8, 0, 0)


def test_permite_fuera_de_la_pausa_nocturna() -> None:
    now = datetime(2026, 8, 9, 8, 0, 0)  # justo al terminar la pausa
    decision = check_rate_limit(now, [], SETTINGS)
    assert decision.allowed


def test_pausa_nocturna_desactivada_si_start_igual_end() -> None:
    settings = RateLimitSettings(night_start_hour=5, night_end_hour=5)
    now = datetime(2026, 8, 9, 5, 0, 0)
    decision = check_rate_limit(now, [], settings)
    assert decision.allowed


def test_bloquea_por_tope_diario() -> None:
    now = datetime(2026, 8, 9, 12, 0, 0)
    actions = [now - timedelta(minutes=i * 20) for i in range(50)]  # 50 en las últimas 24h
    decision = check_rate_limit(now, actions, SETTINGS)
    assert not decision.allowed
    assert "tope diario" in decision.reason


def test_tope_diario_libera_cuando_la_accion_mas_vieja_sale_de_la_ventana() -> None:
    now = datetime(2026, 8, 9, 12, 0, 0)
    oldest = now - timedelta(hours=23, minutes=59)
    actions = [oldest] + [now - timedelta(minutes=i * 20) for i in range(1, 50)]
    decision = check_rate_limit(now, actions, SETTINGS)
    assert not decision.allowed
    assert decision.retry_at == oldest + timedelta(hours=24)


def test_bloquea_por_cadencia_minima() -> None:
    now = datetime(2026, 8, 9, 12, 0, 0)
    last_action = now - timedelta(seconds=60)  # menos de los 180s mínimos
    decision = check_rate_limit(now, [last_action], SETTINGS)
    assert not decision.allowed
    assert "cadencia" in decision.reason
    assert decision.retry_at == last_action + timedelta(seconds=180)


def test_permite_tras_cumplir_la_cadencia_minima() -> None:
    now = datetime(2026, 8, 9, 12, 0, 0)
    last_action = now - timedelta(seconds=181)
    decision = check_rate_limit(now, [last_action], SETTINGS)
    assert decision.allowed


def test_pick_next_delay_seconds_dentro_del_rango() -> None:
    for _ in range(50):
        delay = pick_next_delay_seconds(SETTINGS)
        assert SETTINGS.min_seconds <= delay <= SETTINGS.max_seconds
