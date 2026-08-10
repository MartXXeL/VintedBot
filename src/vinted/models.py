"""Modelos de datos compartidos entre el panel, la IA y los clientes de Vinted."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ConnectionMode = Literal["api", "session"]
AccountStatus = Literal["disconnected", "connected", "error", "suspended"]
ListingStatus = Literal["draft", "published", "sold", "archived"]
OfferStatus = Literal["pending", "approved", "sent", "discarded", "expired"]
NegotiationAction = Literal["accept", "counter", "reject"]

# Los mismos cinco estados que usa Vinted en su formulario de publicar.
ItemCondition = Literal[
    "new_with_tags", "new_without_tags", "very_good", "good", "satisfactory"
]

CONDITION_LABELS_ES: dict[ItemCondition, str] = {
    "new_with_tags": "Nuevo con etiquetas",
    "new_without_tags": "Nuevo sin etiquetas",
    "very_good": "Muy bueno",
    "good": "Bueno",
    "satisfactory": "Satisfactorio",
}


class VintedAccount(BaseModel):
    """Una cuenta de Vinted conectada al panel.

    `session_cookie` y los tokens de la API oficial se cifran en reposo (ver
    `src/storage/crypto.py`) y nunca deben llegar a un log ni a un prompt de IA.
    """

    id: int | None = None
    label: str
    connection_mode: ConnectionMode = "session"
    vinted_user_id: str | None = None
    status: AccountStatus = "disconnected"
    auto_publish: bool = False
    auto_reply_offers: bool = False
    # A quién pertenece dentro del panel — None solo en cuentas de antes de
    # que existieran los usuarios (una migración las deja sin dueño; un
    # admin las ve igualmente, un member no).
    owner_user_id: int | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class ListingDraftFields(BaseModel):
    """Lo que la IA con visión extrae de las fotos de un artículo.

    Campos editables por el usuario antes de publicar: la IA propone, nunca
    decide sola. `confidence` es orientativo, para resaltar en la UI los
    campos que convendría revisar a mano.
    """

    category: str | None = None
    brand: str | None = None
    size: str | None = None
    item_condition: ItemCondition | None = None
    title: str = ""
    description: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class Listing(BaseModel):
    """Un anuncio, desde borrador hasta vendido."""

    id: int | None = None
    account_id: int
    title: str = ""
    description: str = ""
    category: str | None = None
    brand: str | None = None
    size: str | None = None
    item_condition: ItemCondition | None = None
    price: float = 0.0
    # Nunca se manda a la IA: es el dato que protege el margen del vendedor.
    min_price: float | None = None
    photo_paths: list[str] = Field(default_factory=list)
    status: ListingStatus = "draft"
    vinted_item_id: str | None = None
    ai_generated: bool = False
    created_at: datetime = Field(default_factory=datetime.now)
    published_at: datetime | None = None


class Offer(BaseModel):
    """Una oferta de un comprador sobre un anuncio publicado."""

    id: int | None = None
    listing_id: int
    account_id: int
    buyer_name: str | None = None
    offer_amount: float
    # Identificadores del lado de Vinted (conversación + oferta dentro de
    # ella): permiten reconocer, al volver a consultar conversaciones, una
    # oferta que ya se procesó, en vez de duplicarla en cada sondeo.
    external_conversation_id: str | None = None
    external_offer_id: str | None = None
    decision: NegotiationAction | None = None
    counter_amount: float | None = None
    reply_text: str | None = None
    status: OfferStatus = "pending"
    received_at: datetime = Field(default_factory=datetime.now)
    answered_at: datetime | None = None


class NegotiationDecision(BaseModel):
    """Salida del motor de reglas: qué hacer con una oferta y por qué.

    `min_price` se incluye aquí solo para trazabilidad interna (logs, tests);
    `to_ai_context()` es la única vista de este objeto que debe llegar a un
    prompt, y deliberadamente NO incluye `min_price` ni `ratio`.
    """

    action: NegotiationAction
    offer_amount: float
    min_price: float
    counter_amount: float | None = None
    ratio: float = Field(description="offer_amount / min_price")

    def to_ai_context(self) -> dict[str, float | str]:
        """Lo único que la IA recibe: la decisión ya tomada, nunca el precio mínimo."""
        context: dict[str, float | str] = {
            "action": self.action,
            "offer_amount": self.offer_amount,
        }
        if self.counter_amount is not None:
            context["counter_amount"] = self.counter_amount
        return context


class Sale(BaseModel):
    """Una venta cerrada, usada por el seguimiento fiscal DAC7."""

    id: int | None = None
    account_id: int
    listing_id: int | None = None
    sale_amount: float
    sold_at: datetime = Field(default_factory=datetime.now)
