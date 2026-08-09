import pytest

from src.negotiation.engine import decide
from src.negotiation.policy import NegotiationPolicy


def test_acepta_oferta_igual_al_minimo() -> None:
    decision = decide(offer_amount=20, min_price=20)
    assert decision.action == "accept"
    assert decision.counter_amount is None


def test_acepta_oferta_justo_en_el_75_por_ciento() -> None:
    decision = decide(offer_amount=15, min_price=20)  # ratio exacto 0.75
    assert decision.action == "accept"


def test_acepta_oferta_por_encima_del_minimo() -> None:
    decision = decide(offer_amount=25, min_price=20)
    assert decision.action == "accept"


def test_contraoferta_en_zona_intermedia() -> None:
    decision = decide(offer_amount=10, min_price=20)  # ratio 0.50
    assert decision.action == "counter"
    assert decision.counter_amount is not None
    assert decision.counter_amount >= 20  # nunca por debajo del mínimo


def test_contraoferta_justo_en_el_40_por_ciento() -> None:
    decision = decide(offer_amount=8, min_price=20)  # ratio exacto 0.40
    assert decision.action == "counter"


def test_rechaza_oferta_por_debajo_del_40_por_ciento() -> None:
    decision = decide(offer_amount=5, min_price=20)  # ratio 0.25
    assert decision.action == "reject"
    assert decision.counter_amount is None


def test_rechaza_oferta_cero() -> None:
    decision = decide(offer_amount=0, min_price=20)
    assert decision.action == "reject"


def test_contraoferta_sin_precio_de_venta_cae_al_minimo() -> None:
    """Sin `listing_price` de referencia, la contraoferta pide justo el mínimo."""
    decision = decide(offer_amount=10, min_price=20)
    assert decision.counter_amount == 20.0


def test_contraoferta_usa_el_precio_de_venta_como_referencia() -> None:
    # ratio = 14/20 = 0.70 (zona de contraoferta)
    decision = decide(offer_amount=14, min_price=20, listing_price=36)
    # punto medio entre la oferta (14) y el precio de venta (36) = 25.0
    assert decision.counter_amount == 25.0


def test_contraoferta_nunca_baja_del_minimo_aunque_haya_precio_de_venta() -> None:
    decision = decide(offer_amount=14.9, min_price=20, listing_price=21)
    assert decision.counter_amount >= 20


def test_compute_counter_amount_nunca_supera_la_referencia_alta() -> None:
    # Prueba directa del helper: en decide() esto no es alcanzable (la oferta
    # en zona de contraoferta siempre queda por debajo del mínimo, y este por
    # debajo de listing_price), pero el acotado debe sostenerse igual.
    from src.negotiation.engine import _compute_counter_amount
    from src.negotiation.policy import DEFAULT_POLICY

    counter = _compute_counter_amount(
        offer_amount=100, min_price=20, listing_price=22, policy=DEFAULT_POLICY
    )
    assert counter <= 22


def test_contraoferta_ignora_precio_de_venta_por_debajo_del_minimo() -> None:
    """Un listing_price mal configurado (<= mínimo) no debe usarse como referencia."""
    decision = decide(offer_amount=10, min_price=20, listing_price=18)
    assert decision.counter_amount == 20.0


def test_min_price_cero_o_negativo_lanza_error() -> None:
    with pytest.raises(ValueError):
        decide(offer_amount=10, min_price=0)
    with pytest.raises(ValueError):
        decide(offer_amount=10, min_price=-5)


def test_offer_amount_negativo_lanza_error() -> None:
    with pytest.raises(ValueError):
        decide(offer_amount=-1, min_price=20)


def test_to_ai_context_nunca_incluye_min_price_ni_ratio() -> None:
    decision = decide(offer_amount=10, min_price=20)
    context = decision.to_ai_context()

    assert "min_price" not in context
    assert "ratio" not in context
    assert context["action"] == "counter"
    assert context["counter_amount"] == decision.counter_amount


def test_to_ai_context_de_un_rechazo_no_incluye_counter_amount() -> None:
    decision = decide(offer_amount=1, min_price=20)
    context = decision.to_ai_context()

    assert "counter_amount" not in context


def test_policy_personalizada() -> None:
    policy = NegotiationPolicy(accept_ratio=0.9, reject_ratio=0.5)
    decision = decide(offer_amount=16, min_price=20, policy=policy)  # ratio 0.80
    assert decision.action == "counter"


def test_policy_invalida_lanza_error() -> None:
    with pytest.raises(ValueError):
        NegotiationPolicy(accept_ratio=0.3, reject_ratio=0.5)
