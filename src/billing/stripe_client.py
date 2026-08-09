"""Cliente de Stripe: checkout de la suscripción y verificación de webhooks.

Sin `STRIPE_SECRET_KEY` configurada, la pantalla de suscripción del panel
sigue mostrando el plan recomendado y el desglose de precio (eso es cálculo
puro, ver `src/billing/plans.py`) pero oculta el botón de pago — no hace
falta cuenta de Stripe para usar el resto de VintedBot.

`stripe_module` es inyectable (igual que el cliente de Anthropic en
`src/ai/providers.py`) para poder probar la construcción de la sesión de
checkout y la verificación de la firma del webhook sin llamar a la API de
Stripe de verdad.
"""

from typing import Any


class WebhookVerificationError(Exception):
    """La firma del webhook no es válida (o falta `STRIPE_WEBHOOK_SECRET`)."""


class StripeClient:
    def __init__(self, secret_key: str, webhook_secret: str = "", stripe_module: Any = None) -> None:
        if not secret_key:
            raise ValueError("secret_key es obligatoria para hablar con Stripe")
        if stripe_module is not None:
            self._stripe = stripe_module
        else:
            import stripe as _stripe

            self._stripe = _stripe
        self._stripe.api_key = secret_key
        self._webhook_secret = webhook_secret

    def create_checkout_session(
        self,
        price_id: str,
        success_url: str,
        cancel_url: str,
        customer_email: str | None = None,
    ) -> str:
        """Crea una sesión de Checkout en modo suscripción y devuelve la URL a la que redirigir."""
        params: dict[str, Any] = {
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
        }
        if customer_email:
            params["customer_email"] = customer_email
        session = self._stripe.checkout.Session.create(**params)
        return session.url

    def verify_webhook_event(self, payload: bytes, sig_header: str) -> dict:
        """Verifica la firma de un webhook entrante y devuelve el evento ya validado.

        Sin esto, cualquiera que conozca la URL del webhook podría mandar
        eventos falsos (p. ej. un "pago completado" inventado) — la firma
        demuestra que el evento viene de verdad de Stripe.
        """
        if not self._webhook_secret:
            raise WebhookVerificationError("STRIPE_WEBHOOK_SECRET no está configurado")
        try:
            return self._stripe.Webhook.construct_event(payload, sig_header, self._webhook_secret)
        except Exception as error:  # noqa: BLE001 — cualquier fallo de verificación es el mismo caso para quien llama
            raise WebhookVerificationError(str(error)) from error
