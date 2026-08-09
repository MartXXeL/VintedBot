"""Trabajador en segundo plano: publica borradores y negocia ofertas al ritmo seguro.

Un ciclo por cuenta conectada por sesión hace COMO MUCHO una cosa, y solo si
`check_rate_limit` lo permite — así el trabajador nunca puede saltarse el
límite que protege la cuenta, pase lo que pase en el resto del código. Leer
conversaciones y dejar una oferta decidida y redactada en 'pending' no
cuenta para el límite diario (no es una acción que Vinted vea); publicar un
anuncio o mandar de verdad la respuesta de una oferta, sí. La publicación no
espera a que la IA genere nada: solo publica anuncios que ya tienen título,
fotos y precio mínimo (ese trabajo lo hace el panel, ver
`src/ai/listing_writer.py`); aquí solo se decide CUÁNDO es seguro publicarlo.

`run_account_cycle` es la pieza con lógica real y está pensada para probarse
con dobles de prueba (sin red). `run_forever` es el bucle de orquestación de
verdad — con I/O real (HTTP, disco, reloj) — y deliberadamente no se prueba
unitariamente, igual que el bucle equivalente de Telescraperra.
"""

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.ai.negotiation_writer import draft_reply
from src.ai.providers import AIProvider
from src.core.logger import logger
from src.core.settings import Settings
from src.negotiation.engine import decide
from src.negotiation.policy import DEFAULT_POLICY
from src.storage import accounts_store, actions_store, listings_store, offers_store
from src.vinted.models import Listing, Offer, VintedAccount
from src.vinted.rate_limiter import RateLimitDecision, check_rate_limit, pick_next_delay_seconds
from src.vinted.session_client import VintedSessionClient, parse_pending_offers


@dataclass(frozen=True)
class CycleResult:
    account_id: int
    action: str  # "published_listing" | "processed_offer" | "rate_limited" | "idle"
    detail: str = ""


async def run_account_cycle(
    db_path: str,
    account: VintedAccount,
    session_client: VintedSessionClient,
    ai_provider: AIProvider,
    settings: Settings,
    now: datetime | None = None,
) -> CycleResult:
    """Un ciclo de trabajo para UNA cuenta: como mucho una acción que escribe algo."""
    now = now or datetime.now()
    if account.id is None:
        raise ValueError("La cuenta necesita id (debe venir ya persistida)")

    recent_actions = actions_store.actions_in_last_24h(db_path, account.id, now)
    rate_decision = check_rate_limit(now, recent_actions, settings.rate_limit)
    if not rate_decision.allowed:
        return CycleResult(account.id, "rate_limited", rate_decision.reason or "")

    if account.auto_publish:
        draft = _next_publishable_listing(db_path, account.id)
        if draft is not None:
            await _publish_listing(db_path, draft, session_client)
            actions_store.record_action(db_path, account.id, "publish_listing")
            return CycleResult(account.id, "published_listing", draft.title)

    # A diferencia de publicar, preparar una oferta (decidir + redactar la
    # respuesta) NO es una acción que Vinted vea: es una llamada de lectura
    # (list_conversations) más trabajo local. Se hace SIEMPRE que hay hueco
    # en el ritmo, deja la oferta en 'pending' para aprobación humana en el
    # panel, y solo cuenta como acción del límite diario (y solo se manda de
    # verdad a Vinted) si `auto_reply_offers` está activo — igual que
    # AUTO_CONFIRM en Telescraperra: por defecto, un humano aprueba.
    handled = await _process_one_offer(db_path, account, session_client, ai_provider)
    if handled:
        return CycleResult(account.id, "processed_offer", handled)

    return CycleResult(account.id, "idle")


async def publish_listing_now(
    db_path: str,
    account: VintedAccount,
    listing: Listing,
    session_client: VintedSessionClient,
    settings: Settings,
    now: datetime | None = None,
) -> RateLimitDecision | None:
    """Publica UN anuncio concreto ya, para el botón "Publicar ahora" del panel.

    Reutiliza el mismo `check_rate_limit` que el ciclo automático: un clic
    manual no puede saltarse el límite que protege la cuenta. Devuelve la
    `RateLimitDecision` de bloqueo si no era buen momento, o `None` si
    publicó sin problema.
    """
    now = now or datetime.now()
    recent_actions = actions_store.actions_in_last_24h(db_path, account.id, now)
    rate_decision = check_rate_limit(now, recent_actions, settings.rate_limit)
    if not rate_decision.allowed:
        return rate_decision

    await _publish_listing(db_path, listing, session_client)
    actions_store.record_action(db_path, account.id, "publish_listing")
    return None


async def send_offer_reply_now(
    db_path: str,
    account: VintedAccount,
    offer: Offer,
    session_client: VintedSessionClient,
    settings: Settings,
    now: datetime | None = None,
) -> RateLimitDecision | None:
    """Manda YA la respuesta ya decidida/redactada de una oferta (aprobación manual).

    Para el botón "Aceptar" del panel cuando `auto_reply_offers` está
    desactivado: la oferta ya tiene `decision`/`reply_text` (los puso el
    trabajador al sondear conversaciones), aquí solo se envían a Vinted, con
    el mismo límite de ritmo que cualquier otra acción.
    """
    if offer.decision is None or offer.reply_text is None:
        raise ValueError("La oferta todavía no tiene una decisión/respuesta que enviar")
    if not offer.external_conversation_id or not offer.external_offer_id:
        raise ValueError("A la oferta le faltan los identificadores de Vinted")

    now = now or datetime.now()
    recent_actions = actions_store.actions_in_last_24h(db_path, account.id, now)
    rate_decision = check_rate_limit(now, recent_actions, settings.rate_limit)
    if not rate_decision.allowed:
        return rate_decision

    await _send_offer_decision(
        session_client,
        offer.external_conversation_id,
        offer.external_offer_id,
        offer.decision,
        offer.counter_amount,
        offer.reply_text,
    )
    offers_store.mark_sent(db_path, offer.id)
    actions_store.record_action(db_path, account.id, "process_offer")
    return None


def _next_publishable_listing(db_path: str, account_id: int) -> Listing | None:
    drafts = listings_store.list_listings(db_path, account_id=account_id, status="draft")
    ready = [d for d in drafts if d.title and d.photo_paths and d.min_price]
    return ready[0] if ready else None


async def _publish_listing(db_path: str, listing: Listing, session_client: VintedSessionClient) -> None:
    photo_ids = []
    for path in listing.photo_paths:
        photo_bytes = await asyncio.to_thread(Path(path).read_bytes)
        photo_ids.append(await session_client.upload_photo(photo_bytes))

    payload = {
        "title": listing.title,
        "description": listing.description,
        "price": listing.price,
        "photo_ids": photo_ids,
        "brand": listing.brand,
        "size": listing.size,
        "category": listing.category,
        "status": listing.item_condition,
    }
    result = await session_client.publish_listing(payload)
    listings_store.mark_published(db_path, listing.id, vinted_item_id=str(result["id"]))


async def _process_one_offer(
    db_path: str, account: VintedAccount, session_client: VintedSessionClient, ai_provider: AIProvider
) -> str | None:
    conversations = await session_client.list_conversations()

    for pending in parse_pending_offers(conversations):
        if offers_store.get_offer_by_external_id(db_path, str(pending["offer_id"])):
            continue  # ya se procesó en un ciclo anterior

        vinted_item_id = pending.get("vinted_item_id")
        listing = (
            listings_store.get_listing_by_vinted_item_id(db_path, str(vinted_item_id))
            if vinted_item_id
            else None
        )
        if listing is None or listing.min_price is None:
            # Sin anuncio interno reconocible, o sin precio mínimo configurado:
            # no hay forma segura de decidir, así que se deja para revisión manual.
            continue

        offer = offers_store.create_offer(
            db_path,
            Offer(
                listing_id=listing.id,
                account_id=account.id,
                buyer_name=pending.get("buyer_name"),
                offer_amount=float(pending["amount"]),
                external_conversation_id=str(pending["conversation_id"]),
                external_offer_id=str(pending["offer_id"]),
            ),
        )

        decision = decide(
            offer.offer_amount, listing.min_price, listing_price=listing.price, policy=DEFAULT_POLICY
        )
        reply_text = draft_reply(ai_provider, decision)
        offers_store.set_offer_decision(db_path, offer.id, decision.action, decision.counter_amount, reply_text)

        if account.auto_reply_offers:
            await _send_offer_decision(
                session_client,
                str(pending["conversation_id"]),
                str(pending["offer_id"]),
                decision.action,
                decision.counter_amount,
                reply_text,
            )
            offers_store.mark_sent(db_path, offer.id)
            # Solo lo que de verdad toca Vinted (mandar la respuesta) cuenta
            # para el límite diario — leer conversaciones y redactar no.
            actions_store.record_action(db_path, account.id, "process_offer")

        return f"oferta {offer.id} ({decision.action})"

    return None


async def _send_offer_decision(
    session_client: VintedSessionClient,
    conversation_id: str,
    offer_id: str,
    action: str,
    counter_amount: float | None,
    reply_text: str,
) -> None:
    if action == "accept":
        await session_client.accept_offer(conversation_id, offer_id)
    elif action == "reject":
        await session_client.reject_offer(conversation_id, offer_id)
    else:
        assert counter_amount is not None  # decide() lo garantiza para "counter"
        await session_client.counter_offer(conversation_id, offer_id, amount=counter_amount)
    await session_client.send_message(conversation_id, reply_text)


async def run_forever(
    db_path: str,
    settings: Settings,
    ai_provider: AIProvider,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Bucle real: I/O de verdad (HTTP, disco, reloj) — no se prueba unitariamente."""
    stop_event = stop_event or asyncio.Event()
    while not stop_event.is_set():
        for account in accounts_store.list_accounts(db_path):
            if account.connection_mode != "session" or account.status != "connected":
                continue
            if not (account.auto_publish or account.auto_reply_offers):
                continue
            cookie = accounts_store.get_account_session_cookie(db_path, account.id)
            if not cookie:
                continue

            client = VintedSessionClient(domain=settings.vinted_domain, session_cookie=cookie)
            try:
                result = await run_account_cycle(db_path, account, client, ai_provider, settings)
                if result.action != "idle":
                    logger.info(f"[{account.label}] {result.action}: {result.detail}")
            except Exception as error:  # noqa: BLE001
                logger.warning(f"[{account.label}] fallo en el ciclo del trabajador: {error}")
            finally:
                await client.aclose()

        delay = pick_next_delay_seconds(settings.rate_limit)
        # Se cumple la espera sin que nos pidieran parar -> siguiente vuelta.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
