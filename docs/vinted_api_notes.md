# Notas sobre la integración con Vinted

Vinted no publica una especificación pública y estable de su API — a
diferencia de Winamax (una web con DOM que se podía inventariar selector a
selector), aquí la referencia es necesariamente de menor certeza. Esta hoja
resume lo que usa `src/vinted/api_client.py` y `src/vinted/session_client.py`,
y por qué, para que quien la toque después sepa qué es un hecho verificable y
qué es una suposición razonable a confirmar contra tráfico real.

## Vía oficial — Vinted Pro Integrations

Programa de vendedor profesional con alta y verificación (hasta 14 días
según se describe en la idea original). Da acceso a:

- Artículos (crear, actualizar, listar)
- Pedidos
- Webhooks de eventos

**No cubre mensajería ni ofertas** — es la limitación citada como motivo
para necesitar una vía de respaldo. `VintedApiClient`
(`src/vinted/api_client.py`) implementa un cliente OAuth2
(client credentials) contra `VINTED_API_BASE_URL` con esa superficie; las
rutas exactas (`/oauth/token`, `/v2/items`, `/v2/orders`,
`/v2/webhooks`) son las convenciones estándar de una API REST con OAuth2 y
deben confirmarse/ajustarse con la documentación que Vinted entregue al
darte de alta como partner — el cliente centraliza las rutas en
`src/vinted/endpoints.py` precisamente para que ese ajuste sea de una línea.

## Vía de sesión (respaldo)

Sin alta ni aprobación, autenticada con las cookies de una sesión web
iniciada por el propio usuario (`access_token_web` / `refresh_token_web`,
el patrón que usan los wrappers no oficiales de Vinted en Python — ver
[fxd-gif/vinted-api-python](https://github.com/fxd-gif/vinted-api-python),
[Pawikoski/vinted-api-wrapper](https://github.com/Pawikoski/vinted-api-wrapper) y
[herissondev/vinted-api-wrapper](https://github.com/herissondev/vinted-api-wrapper)).
Endpoints usados por `VintedSessionClient`:

| Endpoint | Uso | Certeza |
|---|---|---|
| `GET /api/v2/users/{id}` | Verificar sesión activa | Alta — documentado por varios wrappers independientes |
| `POST /api/v2/photos` | Subir una foto (multipart), devuelve un id temporal | Alta |
| `POST /api/v2/items` | Crear/publicar un anuncio con los ids de foto | Alta |
| `GET /api/v2/conversations` | Listar conversaciones (incluye ofertas pendientes) | Media — la forma exacta del payload de una oferta dentro de una conversación no está confirmada |
| `POST /api/v2/conversations/{id}/messages` | Responder en una conversación | Media |
| `POST /api/v2/conversations/{id}/offers/{offer_id}/accept` \| `/reject` | Aceptar/rechazar una oferta | **Baja** — sin confirmar contra tráfico real; la idea original señala explícitamente que "ni siquiera la vía oficial cubre... ofertas", lo que sugiere que esta parte del flujo de Vinted cambia con frecuencia |

Este cliente **no implementa nada de anti-detección** (sin proxies, sin
huellas de navegador falsas, sin rotación de user-agent): solo hace
peticiones HTTP normales con la sesión del propio usuario. La protección de
la cuenta viene entera de `src/vinted/rate_limiter.py` (cadencia, tope
diario, pausa nocturna), no de intentar parecer "más humano" ante Vinted.

## Qué hacer cuando un endpoint deja de funcionar

1. Confirmar con una petición manual (navegador + herramientas de red) si la
   ruta o el formato cambiaron.
2. Actualizar `src/vinted/endpoints.py` — es la única fuente de rutas, tanto
   el cliente oficial como el de sesión las importan de ahí.
3. Añadir/actualizar el caso correspondiente en
   `tests/unit/test_session_client.py` o `test_api_client.py` con el nuevo
   formato de respuesta esperado.
