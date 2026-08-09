import pytest
from pydantic import ValidationError

from src.vinted.models import Listing, NegotiationDecision, Offer, VintedAccount


def test_vinted_account_valores_por_defecto() -> None:
    account = VintedAccount(label="Cuenta principal")
    assert account.connection_mode == "session"
    assert account.status == "disconnected"
    assert account.auto_reply_offers is False


def test_listing_min_price_no_es_obligatorio_pero_existe_el_campo() -> None:
    listing = Listing(account_id=1, price=25.0)
    assert listing.min_price is None
    assert listing.photo_paths == []


def test_offer_requiere_offer_amount() -> None:
    with pytest.raises(ValidationError):
        Offer(listing_id=1, account_id=1)  # type: ignore[call-arg]

    offer = Offer(listing_id=1, account_id=1, offer_amount=10)
    assert offer.status == "pending"


def test_negotiation_decision_ratio_fuera_de_rango_no_se_valida_como_probabilidad() -> None:
    # ratio puede superar 1.0 (oferta por encima del mínimo): no debe fallar.
    decision = NegotiationDecision(action="accept", offer_amount=30, min_price=20, ratio=1.5)
    assert decision.ratio == 1.5
