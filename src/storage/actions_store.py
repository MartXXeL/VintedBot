"""Registro de acciones por cuenta — el historial que consulta el limitador de ritmo.

Separado de las demás tablas porque se escribe en CADA acción de la vía de
sesión (publicar, mandar mensaje, responder una oferta) y se lee en cada
comprobación de `src/vinted/rate_limiter.py::check_rate_limit`: mantenerlo
como su propia tabla, estrecha y con índice por `(account_id, performed_at)`,
evita que ese vaivén constante toque las tablas de negocio.
"""

from datetime import datetime, timedelta

from src.storage.db import connect


def record_action(db_path: str, account_id: int, action_type: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO actions_log (account_id, action_type) VALUES (?, ?)",
            (account_id, action_type),
        )


def actions_in_last_24h(db_path: str, account_id: int, now: datetime) -> list[datetime]:
    since = now - timedelta(hours=24)
    with connect(db_path) as conn:
        rows = conn.execute(
            """SELECT performed_at FROM actions_log
               WHERE account_id = ? AND performed_at >= ?
               ORDER BY performed_at""",
            (account_id, since.isoformat(sep=" ", timespec="seconds")),
        ).fetchall()
        return [datetime.fromisoformat(row["performed_at"]) for row in rows]
