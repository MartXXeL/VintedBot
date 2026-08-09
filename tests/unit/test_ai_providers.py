from dataclasses import dataclass, field
from typing import Any

import pytest

from src.ai.providers import AnthropicAIProvider, MockAIProvider, get_ai_provider

# --------------------------------------------------------------------------- #
#  Doble de prueba del cliente de Anthropic: sin red, verifica la forma de la
#  petición y permite fabricar la respuesta que se quiera parsear.
# --------------------------------------------------------------------------- #


@dataclass
class _FakeBlock:
    type: str
    text: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class _FakeResponse:
    content: list[_FakeBlock]


class _FakeMessages:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.last_call_kwargs: dict[str, Any] | None = None

    def create(self, **kwargs: Any) -> _FakeResponse:
        self.last_call_kwargs = kwargs
        return self.response


class _FakeAnthropicClient:
    def __init__(self, response: _FakeResponse) -> None:
        self.messages = _FakeMessages(response)


# --------------------------------------------------------------------------- #
#  MockAIProvider
# --------------------------------------------------------------------------- #


def test_mock_provider_genera_borrador_con_confianza_cero() -> None:
    provider = MockAIProvider()
    draft = provider.generate_listing([b"foto-falsa"])
    assert draft.confidence == 0.0
    assert draft.title


def test_mock_provider_respuesta_de_aceptar() -> None:
    provider = MockAIProvider()
    reply = provider.draft_negotiation_reply({"action": "accept", "offer_amount": 20})
    assert "acepto" in reply.lower() or "trato" in reply.lower()


def test_mock_provider_respuesta_de_contraoferta_incluye_el_importe() -> None:
    provider = MockAIProvider()
    reply = provider.draft_negotiation_reply(
        {"action": "counter", "offer_amount": 10, "counter_amount": 15.0}
    )
    assert "15.0" in reply or "15" in reply


def test_mock_provider_respuesta_de_rechazo_no_menciona_importe_alguno() -> None:
    provider = MockAIProvider()
    reply = provider.draft_negotiation_reply({"action": "reject", "offer_amount": 3})
    assert "3" not in reply


# --------------------------------------------------------------------------- #
#  AnthropicAIProvider (con cliente inyectado, sin red)
# --------------------------------------------------------------------------- #


def test_generate_listing_manda_las_fotos_en_base64() -> None:
    fake_response = _FakeResponse(
        content=[
            _FakeBlock(
                type="tool_use",
                name="submit_listing_draft",
                input={
                    "category": "Camisetas",
                    "brand": "Nike",
                    "size": "M",
                    "item_condition": "good",
                    "title": "Camiseta Nike talla M",
                    "description": "Poco uso, sin manchas.",
                    "confidence": 0.9,
                },
            )
        ]
    )
    client = _FakeAnthropicClient(fake_response)
    provider = AnthropicAIProvider(api_key="sk-test", client=client)

    draft = provider.generate_listing([b"\xff\xd8\xff-foto-jpeg-falsa"])

    assert draft.brand == "Nike"
    assert draft.item_condition == "good"
    assert draft.confidence == 0.9

    sent = client.messages.last_call_kwargs
    assert sent["tool_choice"] == {"type": "tool", "name": "submit_listing_draft"}
    image_blocks = [b for b in sent["messages"][0]["content"] if b["type"] == "image"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["source"]["media_type"] == "image/jpeg"


def test_generate_listing_sin_fotos_lanza_error() -> None:
    provider = AnthropicAIProvider(api_key="sk-test", client=_FakeAnthropicClient(_FakeResponse([])))
    with pytest.raises(ValueError):
        provider.generate_listing([])


def test_generate_listing_sin_tool_use_lanza_error() -> None:
    fake_response = _FakeResponse(content=[_FakeBlock(type="text", text="no debería pasar")])
    provider = AnthropicAIProvider(api_key="sk-test", client=_FakeAnthropicClient(fake_response))
    with pytest.raises(ValueError):
        provider.generate_listing([b"foto"])


def test_generate_listing_condicion_desconocida_se_ignora_sin_reventar() -> None:
    fake_response = _FakeResponse(
        content=[
            _FakeBlock(
                type="tool_use",
                name="submit_listing_draft",
                input={"title": "x", "description": "y", "confidence": 0.5, "item_condition": "impecable"},
            )
        ]
    )
    provider = AnthropicAIProvider(api_key="sk-test", client=_FakeAnthropicClient(fake_response))
    draft = provider.generate_listing([b"foto"])
    assert draft.item_condition is None


def test_draft_negotiation_reply_nunca_manda_min_price(monkeypatch) -> None:
    fake_response = _FakeResponse(content=[_FakeBlock(type="text", text="¡Genial, trato hecho!")])
    client = _FakeAnthropicClient(fake_response)
    provider = AnthropicAIProvider(api_key="sk-test", client=client)

    reply = provider.draft_negotiation_reply({"action": "accept", "offer_amount": 20})

    assert reply == "¡Genial, trato hecho!"
    sent_content = client.messages.last_call_kwargs["messages"][0]["content"]
    assert "min_price" not in sent_content
    assert "ratio" not in sent_content


def test_draft_negotiation_reply_sin_texto_lanza_error() -> None:
    fake_response = _FakeResponse(content=[_FakeBlock(type="tool_use", name="algo", input={})])
    provider = AnthropicAIProvider(api_key="sk-test", client=_FakeAnthropicClient(fake_response))
    with pytest.raises(ValueError):
        provider.draft_negotiation_reply({"action": "accept", "offer_amount": 1})


# --------------------------------------------------------------------------- #
#  Fábrica
# --------------------------------------------------------------------------- #


def test_get_ai_provider_mock() -> None:
    assert isinstance(get_ai_provider("mock"), MockAIProvider)


def test_get_ai_provider_anthropic_sin_clave_lanza_error() -> None:
    with pytest.raises(ValueError):
        get_ai_provider("anthropic", anthropic_api_key="")


def test_get_ai_provider_desconocido_lanza_error() -> None:
    with pytest.raises(ValueError):
        get_ai_provider("no-existe")
