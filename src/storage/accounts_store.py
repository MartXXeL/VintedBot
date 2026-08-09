"""Persistencia de cuentas de Vinted conectadas.

La cookie de sesión y los tokens de la API oficial se cifran en reposo
(`src/storage/crypto.py`) antes de tocar disco, y se descifran solo al leerlos
para usarlos en un cliente (`src/vinted/session_client.py` /
`src/vinted/api_client.py`) — nunca se exponen sin cifrar fuera de esa
frontera.
"""

import sqlite3
from datetime import datetime

from src.storage.crypto import decrypt_text, encrypt_text
from src.storage.db import connect
from src.vinted.models import VintedAccount


def _row_to_account(row: sqlite3.Row) -> VintedAccount:
    return VintedAccount(
        id=row["id"],
        label=row["label"],
        connection_mode=row["connection_mode"],
        vinted_user_id=row["vinted_user_id"],
        status=row["status"],
        auto_publish=bool(row["auto_publish"]),
        auto_reply_offers=bool(row["auto_reply_offers"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def create_account(db_path: str, account: VintedAccount, session_cookie: str | None = None) -> VintedAccount:
    with connect(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO accounts
               (label, connection_mode, vinted_user_id, session_cookie_encrypted,
                status, auto_publish, auto_reply_offers)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                account.label,
                account.connection_mode,
                account.vinted_user_id,
                encrypt_text(session_cookie),
                account.status,
                int(account.auto_publish),
                int(account.auto_reply_offers),
            ),
        )
        account_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return _row_to_account(row)


def get_account(db_path: str, account_id: int) -> VintedAccount | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return _row_to_account(row) if row else None


def list_accounts(db_path: str) -> list[VintedAccount]:
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM accounts ORDER BY created_at").fetchall()
        return [_row_to_account(row) for row in rows]


def update_account_status(db_path: str, account_id: int, status: str) -> None:
    with connect(db_path) as conn:
        conn.execute("UPDATE accounts SET status = ? WHERE id = ?", (status, account_id))


def set_automation_flags(
    db_path: str, account_id: int, *, auto_publish: bool, auto_reply_offers: bool
) -> None:
    """Activa/desactiva la publicación y el envío automáticos (ambos empiezan en False)."""
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE accounts SET auto_publish = ?, auto_reply_offers = ? WHERE id = ?",
            (int(auto_publish), int(auto_reply_offers), account_id),
        )


def set_account_session_cookie(db_path: str, account_id: int, session_cookie: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE accounts SET session_cookie_encrypted = ? WHERE id = ?",
            (encrypt_text(session_cookie), account_id),
        )


def get_account_session_cookie(db_path: str, account_id: int) -> str | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT session_cookie_encrypted FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if row is None:
            return None
        return decrypt_text(row["session_cookie_encrypted"])


def delete_account(db_path: str, account_id: int) -> None:
    with connect(db_path) as conn:
        conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
