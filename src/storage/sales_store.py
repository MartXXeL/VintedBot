"""Persistencia de ventas cerradas — alimenta el seguimiento fiscal DAC7."""

import sqlite3
from datetime import datetime

from src.storage.db import connect
from src.vinted.models import Sale


def _row_to_sale(row: sqlite3.Row) -> Sale:
    return Sale(
        id=row["id"],
        account_id=row["account_id"],
        listing_id=row["listing_id"],
        sale_amount=row["sale_amount"],
        sold_at=datetime.fromisoformat(row["sold_at"]),
    )


def record_sale(db_path: str, sale: Sale) -> Sale:
    with connect(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO sales (account_id, listing_id, sale_amount) VALUES (?, ?, ?)",
            (sale.account_id, sale.listing_id, sale.sale_amount),
        )
        sale_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
        return _row_to_sale(row)


def list_sales(db_path: str, account_id: int | None = None) -> list[Sale]:
    query = "SELECT * FROM sales"
    params: list[object] = []
    if account_id is not None:
        query += " WHERE account_id = ?"
        params.append(account_id)
    query += " ORDER BY sold_at"

    with connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
        return [_row_to_sale(row) for row in rows]
