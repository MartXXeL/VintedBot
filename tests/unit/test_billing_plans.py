import pytest

from src.billing.plans import PLANS, calculate_monthly_price, estimate_ai_cost_usd, recommend_plan


def test_uso_dentro_de_la_cuota_solo_paga_la_base() -> None:
    calc = calculate_monthly_price(PLANS["starter"], connected_accounts=2, listings_used=100)
    assert calc.extra_accounts == 0
    assert calc.extra_listings == 0
    assert calc.total_eur == 30.0


def test_cuentas_extra_se_cobran_por_unidad() -> None:
    calc = calculate_monthly_price(PLANS["starter"], connected_accounts=5, listings_used=0)
    assert calc.extra_accounts == 3
    assert calc.extra_accounts_cost_eur == 3 * 8.0
    assert calc.total_eur == 30.0 + 24.0


def test_anuncios_extra_se_cobran_por_bloques_de_100_empezados() -> None:
    calc = calculate_monthly_price(PLANS["starter"], connected_accounts=0, listings_used=151)
    # 1 anuncio de más ya cuenta como un bloque completo de 100
    assert calc.extra_listings == 1
    assert calc.extra_listings_cost_eur == 5.0


def test_dos_bloques_de_anuncios_extra() -> None:
    calc = calculate_monthly_price(PLANS["starter"], connected_accounts=0, listings_used=350)
    # 350 - 150 = 200 de más -> ceil(200/100) = 2 bloques
    assert calc.extra_listings_cost_eur == 2 * 5.0


def test_valores_negativos_lanzan_error() -> None:
    with pytest.raises(ValueError):
        calculate_monthly_price(PLANS["starter"], connected_accounts=-1, listings_used=0)


def test_recommend_plan_elige_el_mas_barato_para_uso_bajo() -> None:
    recommendation = recommend_plan(connected_accounts=1, listings_used=50)
    assert recommendation.plan_id == "starter"


def test_recommend_plan_elige_scale_para_uso_alto() -> None:
    recommendation = recommend_plan(connected_accounts=20, listings_used=2000)
    assert recommendation.plan_id == "scale"


def test_estimate_ai_cost_usd_orden_de_magnitud_un_centimo() -> None:
    # Unas pocas fotos (~1500 tokens de entrada) + una salida corta (~400 tokens)
    cost = estimate_ai_cost_usd(input_tokens=1500, output_tokens=400)
    assert 0.0 < cost < 0.02


def test_estimate_ai_cost_usd_valores_negativos_lanzan_error() -> None:
    with pytest.raises(ValueError):
        estimate_ai_cost_usd(input_tokens=-1, output_tokens=0)


def test_estimate_ai_cost_usd_cero_tokens_es_gratis() -> None:
    assert estimate_ai_cost_usd(0, 0) == 0.0
