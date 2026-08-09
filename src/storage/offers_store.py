"""Persistencia de ofertas de compradores."""

import sqlite3
from datetime import datetime

from src.storage.db import connect
from src.vinted.models import Offer


def _row_to_offer(row: sqlite3.Row) -> Offer:
    return Offer(
        id=row["id"],
        listing_id=row["listing_id"],
        account_id=row["account_id"],
        buyer_name=row["buyer_name"],
        offer_amount=row["offer_amount"],
        decision=row["decision"],
        counter_amount=row["counter_amount"],
        reply_text=row["reply_text"],
        status=row["status"],
        received_at=datetime.fromisoformat(row["received_at"]),
        answered_at=datetime.fromisoformat(row["answered_at"]) if row["answered_at"] else None,
    )


def create_offer(db_path: str, offer: Offer) -> Offer:
    with connect(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO offers (listing_id, account_id, buyer_name, offer_amount, status)
               VALUES (?, ?, ?, ?, ?)""",
            (offer.listing_id, offer.account_id, offer.buyer_name, offer.offer_amount, offer.status),
        )
        offer_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM offers WHERE id = ?", (offer_id,)).fetchone()
        return _row_to_offer(row)


def get_offer(db_path: str, offer_id: int) -> Offer | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM offers WHERE id = ?", (offer_id,)).fetchone()
        return _row_to_offer(row) if row else None


def list_offers(
    db_path: str, account_id: int | None = None, status: str | None = None
) -> list[Offer]:
    query = "SELECT * FROM offers WHERE 1=1"
    params: list[object] = []
    if account_id is not None:
        query += " AND account_id = ?"
        params.append(account_id)
    if status is not None:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY received_at DESC"

    with connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
        return [_row_to_offer(row) for row in rows]


def set_offer_decision(
    db_path: str, offer_id: int, decision: str, counter_amount: float | None, reply_text: str
) -> None:
    """Guarda la decisión del motor de reglas + el texto redactado por la IA.

    Deja el estado en 'pending' (a la espera de aprobación humana en el
    panel) salvo que la cuenta tenga `auto_reply_offers` activo, en cuyo caso
    quien orquesta (`src/worker/scheduler.py`) llama después a `mark_sent`.
    """
    with connect(db_path) as conn:
        conn.execute(
            """UPDATE offers
               SET decision = ?, counter_amount = ?, reply_text = ?
               WHERE id = ?""",
            (decision, counter_amount, reply_text, offer_id),
        )


def mark_sent(db_path: str, offer_id: int) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE offers SET status = 'sent', answered_at = datetime('now') WHERE id = ?",
            (offer_id,),
        )


def discard_offer(db_path: str, offer_id: int) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE offers SET status = 'discarded', answered_at = datetime('now') WHERE id = ?",
            (offer_id,),
        )
