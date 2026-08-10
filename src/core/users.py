"""Usuarios del panel: quién puede entrar, con qué rol y con qué suscripción.

Un `admin` ve y gestiona las cuentas de Vinted de todo el mundo (más una
pantalla aparte para gestionar los propios perfiles y sus suscripciones); un
`member` solo ve y gestiona las suyas — ver `src/ui/deps.py` para cómo se
resuelve el usuario de cada petición, y `src/storage/accounts_store.py` para
cómo se filtran las cuentas por propietario.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

Role = Literal["admin", "member"]
SubscriptionStatus = Literal["none", "active", "canceled", "past_due"]


class User(BaseModel):
    id: int | None = None
    email: EmailStr
    role: Role = "member"
    is_active: bool = True
    # Suscripción asignada a mano por un admin — independiente de que el
    # propio usuario inicie un Stripe Checkout desde /billing (eso es
    # autoservicio; esto es lo que ve/edita un admin sobre cualquier perfil).
    plan_id: str | None = None
    subscription_status: SubscriptionStatus = "none"
    created_at: datetime = Field(default_factory=datetime.now)
