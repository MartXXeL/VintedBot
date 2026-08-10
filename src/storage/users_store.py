"""Persistencia de usuarios del panel (quién entra, con qué rol, con qué suscripción)."""

import sqlite3
from datetime import datetime

from src.core.users import User
from src.storage.db import connect


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        email=row["email"],
        role=row["role"],
        is_active=bool(row["is_active"]),
        plan_id=row["plan_id"],
        subscription_status=row["subscription_status"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def create_user(db_path: str, email: str, password_hash: str, role: str = "member") -> User:
    with connect(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, role) VALUES (?, ?, ?)",
            (email.strip().lower(), password_hash, role),
        )
        user_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_user(row)


def get_user(db_path: str, user_id: int) -> User | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_user(row) if row else None


def get_user_by_email(db_path: str, email: str) -> User | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
        return _row_to_user(row) if row else None


def get_password_hash(db_path: str, user_id: int) -> str | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
        return row["password_hash"] if row else None


def list_users(db_path: str) -> list[User]:
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()
        return [_row_to_user(row) for row in rows]


def count_users(db_path: str) -> int:
    with connect(db_path) as conn:
        return int(conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"])


def set_role(db_path: str, user_id: int, role: str) -> None:
    with connect(db_path) as conn:
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))


def set_active(db_path: str, user_id: int, is_active: bool) -> None:
    with connect(db_path) as conn:
        conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (int(is_active), user_id))


def set_password_hash(db_path: str, user_id: int, password_hash: str) -> None:
    with connect(db_path) as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))


def set_subscription(db_path: str, user_id: int, plan_id: str | None, subscription_status: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE users SET plan_id = ?, subscription_status = ? WHERE id = ?",
            (plan_id, subscription_status, user_id),
        )
