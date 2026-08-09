from datetime import datetime, timedelta

from src.storage import accounts_store, actions_store
from src.storage.db import init_db
from src.vinted.models import VintedAccount


def _account(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    account_id = accounts_store.create_account(db_path, VintedAccount(label="X")).id
    return db_path, account_id


def test_record_and_read_actions(tmp_path) -> None:
    db_path, account_id = _account(tmp_path)
    actions_store.record_action(db_path, account_id, "publish_listing")
    actions_store.record_action(db_path, account_id, "send_message")

    actions = actions_store.actions_in_last_24h(db_path, account_id, datetime.now())
    assert len(actions) == 2


def test_actions_fuera_de_la_ventana_de_24h_no_aparecen(tmp_path) -> None:
    db_path, account_id = _account(tmp_path)

    import sqlite3

    conn = sqlite3.connect(db_path)
    old_time = (datetime.now() - timedelta(hours=25)).isoformat(sep=" ", timespec="seconds")
    conn.execute(
        "INSERT INTO actions_log (account_id, action_type, performed_at) VALUES (?, ?, ?)",
        (account_id, "publish_listing", old_time),
    )
    conn.commit()
    conn.close()

    actions = actions_store.actions_in_last_24h(db_path, account_id, datetime.now())
    assert actions == []


def test_actions_de_otra_cuenta_no_se_mezclan(tmp_path) -> None:
    db_path, account_id = _account(tmp_path)
    other_account = accounts_store.create_account(db_path, VintedAccount(label="Y")).id

    actions_store.record_action(db_path, account_id, "publish_listing")
    actions_store.record_action(db_path, other_account, "publish_listing")

    assert len(actions_store.actions_in_last_24h(db_path, account_id, datetime.now())) == 1
