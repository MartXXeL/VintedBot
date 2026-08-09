from src.ai.negotiation_writer import draft_reply
from src.ai.providers import MockAIProvider
from src.negotiation.engine import decide


def test_draft_reply_para_una_aceptacion() -> None:
    decision = decide(offer_amount=20, min_price=20)
    reply = draft_reply(MockAIProvider(), decision)
    assert isinstance(reply, str) and reply


def test_draft_reply_para_una_contraoferta_incluye_el_importe_correcto() -> None:
    decision = decide(offer_amount=10, min_price=20, listing_price=36)
    reply = draft_reply(MockAIProvider(), decision)
    assert str(decision.counter_amount) in reply


def test_draft_reply_de_un_rechazo_no_filtra_el_precio_minimo() -> None:
    decision = decide(offer_amount=1, min_price=999)
    reply = draft_reply(MockAIProvider(), decision)
    assert "999" not in reply
