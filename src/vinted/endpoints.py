"""Rutas de la API de Vinted, centralizadas en un solo sitio.

Ver `docs/vinted_api_notes.md` para el nivel de certeza de cada una y qué
hacer cuando Vinted cambie algo: se actualiza aquí y solo aquí.
"""

# --- Vía oficial (Vinted Pro Integrations) ----------------------------------
OAUTH_TOKEN = "/oauth/token"
API_ITEMS = "/v2/items"
API_ITEM_DETAIL = "/v2/items/{item_id}"
API_ORDERS = "/v2/orders"
API_WEBHOOKS = "/v2/webhooks"

# --- Vía de sesión (respaldo, sin alta) -------------------------------------
SESSION_USER = "/api/v2/users/{user_id}"
SESSION_PHOTOS = "/api/v2/photos"  # multipart: sube UNA foto, devuelve un id temporal
SESSION_ITEMS = "/api/v2/items"
SESSION_CONVERSATIONS = "/api/v2/conversations"
SESSION_CONVERSATION_MESSAGES = "/api/v2/conversations/{conversation_id}/messages"
SESSION_OFFER_ACCEPT = "/api/v2/conversations/{conversation_id}/offers/{offer_id}/accept"
SESSION_OFFER_REJECT = "/api/v2/conversations/{conversation_id}/offers/{offer_id}/reject"
SESSION_OFFER_COUNTER = "/api/v2/conversations/{conversation_id}/offers/{offer_id}/counter"
