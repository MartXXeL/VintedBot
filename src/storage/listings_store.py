"""Persistencia de anuncios.

`min_price` se cifra en reposo por la misma razón que la sesión de una
cuenta: es el dato que protege el margen del vendedor y que el motor de
negociación necesita leer, pero que no debe quedar en claro en un volcado de
la base de datos.
"""

import json
import sqlite3
from datetime import datetime

from src.storage.crypto import decrypt_text, encrypt_text
from src.storage.db import connect
from src.vinted.models import Listing


def _row_to_listing(row: sqlite3.Row) -> Listing:
    min_price_raw = decrypt_text(row["min_price_encrypted"])
    return Listing(
        id=row["id"],
        account_id=row["account_id"],
        title=row["title"],
        description=row["description"],
        category=row["category"],
        brand=row["brand"],
        size=row["size"],
        item_condition=row["item_condition"],
        price=row["price"],
        min_price=float(min_price_raw) if min_price_raw is not None else None,
        photo_paths=json.loads(row["photo_paths"]),
        status=row["status"],
        vinted_item_id=row["vinted_item_id"],
        ai_generated=bool(row["ai_generated"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        published_at=datetime.fromisoformat(row["published_at"]) if row["published_at"] else None,
    )


def create_listing(db_path: str, listing: Listing) -> Listing:
    with connect(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO listings
               (account_id, title, description, category, brand, size, item_condition,
                price, min_price_encrypted, photo_paths, status, vinted_item_id, ai_generated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                listing.account_id,
                listing.title,
                listing.description,
                listing.category,
                listing.brand,
                listing.size,
                listing.item_condition,
                listing.price,
                encrypt_text(str(listing.min_price)) if listing.min_price is not None else None,
                json.dumps(listing.photo_paths),
                listing.status,
                listing.vinted_item_id,
                int(listing.ai_generated),
            ),
        )
        listing_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
        return _row_to_listing(row)


def get_listing(db_path: str, listing_id: int) -> Listing | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
        return _row_to_listing(row) if row else None


def get_listing_by_vinted_item_id(db_path: str, vinted_item_id: str) -> Listing | None:
    """Mapea el id de artículo del lado de Vinted (de una conversación) al anuncio interno."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM listings WHERE vinted_item_id = ?", (vinted_item_id,)
        ).fetchone()
        return _row_to_listing(row) if row else None


def list_listings(
    db_path: str, account_id: int | None = None, status: str | None = None
) -> list[Listing]:
    query = "SELECT * FROM listings WHERE 1=1"
    params: list[object] = []
    if account_id is not None:
        query += " AND account_id = ?"
        params.append(account_id)
    if status is not None:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC"

    with connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
        return [_row_to_listing(row) for row in rows]


def update_listing_fields(
    db_path: str,
    listing_id: int,
    *,
    title: str,
    description: str,
    category: str | None,
    brand: str | None,
    size: str | None,
    item_condition: str | None,
    price: float,
    min_price: float | None,
) -> None:
    """Guarda la edición manual de un borrador (revisión antes de publicar)."""
    with connect(db_path) as conn:
        conn.execute(
            """UPDATE listings
               SET title = ?, description = ?, category = ?, brand = ?, size = ?,
                   item_condition = ?, price = ?, min_price_encrypted = ?
               WHERE id = ?""",
            (
                title,
                description,
                category,
                brand,
                size,
                item_condition,
                price,
                encrypt_text(str(min_price)) if min_price is not None else None,
                listing_id,
            ),
        )


def delete_listing(db_path: str, listing_id: int) -> None:
    with connect(db_path) as conn:
        conn.execute("DELETE FROM listings WHERE id = ?", (listing_id,))


def mark_published(db_path: str, listing_id: int, vinted_item_id: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """UPDATE listings
               SET status = 'published', vinted_item_id = ?, published_at = datetime('now')
               WHERE id = ?""",
            (vinted_item_id, listing_id),
        )


def mark_sold(db_path: str, listing_id: int) -> None:
    with connect(db_path) as conn:
        conn.execute("UPDATE listings SET status = 'sold' WHERE id = ?", (listing_id,))


def count_listings_since(db_path: str, account_id: int, since: datetime) -> int:
    """Anuncios generados/publicados desde `since` — usado por los planes de precio."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM listings WHERE account_id = ? AND created_at >= ?",
            (account_id, since.isoformat(sep=" ", timespec="seconds")),
        ).fetchone()
        return int(row["n"])
