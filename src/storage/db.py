"""Conexión y esquema de la base de datos SQLite.

Una sola base de datos con todas las tablas: para el volumen de un revendedor
(cientos de anuncios, no millones) SQLite de sobra, y evita levantar un
servidor de base de datos aparte para un proyecto de este tamaño.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    connection_mode TEXT NOT NULL DEFAULT 'session' CHECK (connection_mode IN ('api', 'session')),
    vinted_user_id TEXT,
    session_cookie_encrypted TEXT,
    api_access_token_encrypted TEXT,
    api_refresh_token_encrypted TEXT,
    status TEXT NOT NULL DEFAULT 'disconnected' CHECK (
        status IN ('disconnected', 'connected', 'error', 'suspended')
    ),
    auto_publish INTEGER NOT NULL DEFAULT 0,
    auto_reply_offers INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    category TEXT,
    brand TEXT,
    size TEXT,
    item_condition TEXT,
    price REAL NOT NULL DEFAULT 0,
    min_price_encrypted TEXT,
    photo_paths TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'draft' CHECK (
        status IN ('draft', 'published', 'sold', 'archived')
    ),
    vinted_item_id TEXT,
    ai_generated INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    published_at TEXT
);

CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    buyer_name TEXT,
    offer_amount REAL NOT NULL,
    decision TEXT CHECK (decision IN ('accept', 'counter', 'reject')),
    counter_amount REAL,
    reply_text TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'approved', 'sent', 'discarded', 'expired')
    ),
    received_at TEXT NOT NULL DEFAULT (datetime('now')),
    answered_at TEXT
);

CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    listing_id INTEGER REFERENCES listings(id) ON DELETE SET NULL,
    sale_amount REAL NOT NULL,
    sold_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS actions_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,
    performed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_listings_account ON listings(account_id);
CREATE INDEX IF NOT EXISTS idx_offers_listing ON offers(listing_id);
CREATE INDEX IF NOT EXISTS idx_offers_account ON offers(account_id);
CREATE INDEX IF NOT EXISTS idx_sales_account ON sales(account_id);
CREATE INDEX IF NOT EXISTS idx_actions_account_time ON actions_log(account_id, performed_at);
"""


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Abre una conexión con claves foráneas activas y filas accesibles por nombre."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path) -> None:
    """Crea las tablas que falten. Segura de llamar en cada arranque."""
    conn = get_connection(db_path)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def connect(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    """Context manager: abre, hace commit si no hay error, y siempre cierra."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
