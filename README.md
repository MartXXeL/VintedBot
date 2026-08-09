# VintedBot

[![Tests](https://github.com/MartXXeL/VintedBot/actions/workflows/tests.yml/badge.svg)](https://github.com/MartXXeL/VintedBot/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.12+-blue)
![Plataforma](https://img.shields.io/badge/plataforma-Windows%20%7C%20Linux-lightgrey)

Herramienta de automatización para revendedores en **Vinted**: sube fotos de un
artículo y una IA con visión rellena categoría, marca, talla y estado, y
redacta un título y una descripción listos para publicar; cuando llega una
oferta de un comprador, un motor de reglas (sin IA) decide si se acepta,
se contraoferta o se rechaza según un precio mínimo que la IA nunca ve, y solo
entonces la IA redacta la respuesta en tono amable.

Este proyecto está en construcción activa. Este README se actualiza en cada
paso — la sección [TODO](#todo) refleja el estado real.

## Índice

- [Idea y alcance](#idea-y-alcance)
- [Arquitectura](#arquitectura)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Puesta en marcha](#puesta-en-marcha)
- [Pruebas e integración continua](#pruebas-e-integración-continua)
- [TODO](#todo)

## Idea y alcance

Dos piezas independientes:

1. **Generador de anuncios**: interfaz web donde se suben fotos de un
   artículo; un modelo de IA con visión identifica marca, talla, estado y
   categoría, y redacta título y descripción en tono informal. Los campos son
   editables antes de publicar.
2. **Agente de negociación**: cuando llega una oferta, un módulo de código
   (sin IA) la compara contra un precio mínimo guardado aparte y decide
   **aceptar** (≥75% del mínimo), **contraofertar** (40-74%) o **rechazar**
   (<40%). Solo después la IA redacta la respuesta; no puede tocar el número.

Conexión con Vinted por dos vías, igual que se plantea el problema real: la
**vía oficial** (Vinted Pro Integrations, requiere alta como vendedor
profesional) para artículos y pedidos, y una **vía de sesión** de respaldo
para lo que la vía oficial no cubre (mensajería y ofertas), con un limitador
de ritmo que respeta la cadencia seguridad documentada para no arriesgar las
cuentas conectadas.

No hace falta pilotar un navegador completo: las acciones que importan
(crear anuncio, leer/responder ofertas) tienen forma de petición HTTP, así
que el cliente de la vía de sesión es HTTP directo (`httpx`), sin Playwright
ni ningún navegador de por medio.

## Arquitectura

*(Se documenta con detalle — diagramas incluidos — a medida que cada pieza
queda implementada. Ver el TODO.)*

## Estructura del proyecto

```
src/
  core/         Configuración, .env, logger, hash de contraseñas
  storage/      Cifrado en reposo (Fernet) y persistencia SQLite
  vinted/       Modelos de datos + clientes (API oficial y sesión)
  negotiation/  Motor de decisión puro (aceptar/contraofertar/rechazar)
  ai/           Proveedores de IA (Claude Sonnet 5 con visión + simulado)
  compliance/   Seguimiento fiscal DAC7 por cuenta
  billing/       Planes de precio y cobro por Stripe
  worker/       Trabajador en segundo plano (ritmo seguro)
  ui/           Panel web (FastAPI + plantillas + estáticos)
tests/unit/     Pruebas unitarias — lógica pura y dobles de prueba, sin red
.github/workflows/tests.yml   CI: lint + tests en cada push
```

## Puesta en marcha

```bash
git clone https://github.com/MartXXeL/VintedBot.git
cd VintedBot

pip install -r requirements.txt
cp .env.example .env

python -m src.main
```

*(La app arranca sin credenciales: sin `ANTHROPIC_API_KEY` usa un proveedor de
IA simulado, y sin cuentas de Vinted conectadas el panel se puede explorar
igual. Detalle completo más abajo a medida que se implementa cada pieza.)*

## Pruebas e integración continua

```bash
pip install -r requirements.txt
ruff check src tests
pytest tests/unit -q
```

Sin navegador ni credenciales: los clientes HTTP de Vinted se prueban con
`httpx.MockTransport`, el cliente de Anthropic con un doble inyectado, y el
proveedor de IA simulado (`MockAIProvider`) cubre todo el flujo de
generación de anuncios y negociación sin gastar un céntimo. GitHub Actions
(`.github/workflows/tests.yml`) ejecuta el linter y la suite completa en
cada push y pull request contra `main` — el badge de arriba refleja su
estado.

## TODO

- [x] Estructura del proyecto y dependencias
- [x] Utilidades base (configuración, cifrado en reposo, logger)
- [x] Modelos de datos de Vinted (cuenta, anuncio, oferta)
- [x] Motor de negociación puro (aceptar/contraofertar/rechazar) + tests
- [x] Limitador de ritmo (cadencia segura, tope diario, pausa nocturna) + tests
- [x] Seguimiento fiscal DAC7 por cuenta + tests
- [x] Planes de precio (por cuenta conectada + volumen) + tests
- [x] Proveedores de IA (Anthropic + simulado) para visión, anuncios y respuestas
- [x] Clientes de Vinted: API oficial + sesión de respaldo
- [x] Persistencia: cuentas, anuncios, ofertas, ventas, registro de acciones
- [x] Trabajador en segundo plano al ritmo seguro
- [x] Integración continua (tests + linter en cada push)
- [x] Panel web: login (con bloqueo por fuerza bruta) y vista general de cuentas
- [x] Panel web: anuncios (generar con IA, editar, publicar)
- [x] Panel web: negociación (aprobar/descartar ofertas)
- [x] Panel web: ajustes y seguimiento DAC7
- [ ] Documentación final (arquitectura con diagramas, variables de entorno, seguridad, avisos)
