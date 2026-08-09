from src.storage import accounts_store
from src.storage.db import init_db
from src.vinted.models import VintedAccount


def _db(tmp_path):
    path = tmp_path / "test.db"
    init_db(path)
    return path


def test_create_and_get_account(tmp_path) -> None:
    db_path = _db(tmp_path)
    created = accounts_store.create_account(db_path, VintedAccount(label="Mi tienda"))

    assert created.id is not None
    fetched = accounts_store.get_account(db_path, created.id)
    assert fetched.label == "Mi tienda"
    assert fetched.status == "disconnected"


def test_get_account_inexistente_devuelve_none(tmp_path) -> None:
    db_path = _db(tmp_path)
    assert accounts_store.get_account(db_path, 999) is None


def test_list_accounts_orden_de_creacion(tmp_path) -> None:
    db_path = _db(tmp_path)
    accounts_store.create_account(db_path, VintedAccount(label="Primera"))
    accounts_store.create_account(db_path, VintedAccount(label="Segunda"))

    labels = [a.label for a in accounts_store.list_accounts(db_path)]
    assert labels == ["Primera", "Segunda"]


def test_update_account_status(tmp_path) -> None:
    db_path = _db(tmp_path)
    account = accounts_store.create_account(db_path, VintedAccount(label="X"))

    accounts_store.update_account_status(db_path, account.id, "connected")

    assert accounts_store.get_account(db_path, account.id).status == "connected"


def test_session_cookie_se_guarda_cifrada_y_se_recupera_igual(tmp_path) -> None:
    db_path = _db(tmp_path)
    account = accounts_store.create_account(db_path, VintedAccount(label="X"), session_cookie="access_token_web=abc123")

    assert accounts_store.get_account_session_cookie(db_path, account.id) == "access_token_web=abc123"

    import sqlite3

    conn = sqlite3.connect(db_path)
    raw = conn.execute(
        "SELECT session_cookie_encrypted FROM accounts WHERE id = ?", (account.id,)
    ).fetchone()[0]
    conn.close()
    assert raw != "access_token_web=abc123"  # nunca en claro en disco


def test_set_account_session_cookie_actualiza(tmp_path) -> None:
    db_path = _db(tmp_path)
    account = accounts_store.create_account(db_path, VintedAccount(label="X"))

    accounts_store.set_account_session_cookie(db_path, account.id, "nueva-cookie")

    assert accounts_store.get_account_session_cookie(db_path, account.id) == "nueva-cookie"


def test_set_automation_flags(tmp_path) -> None:
    db_path = _db(tmp_path)
    account = accounts_store.create_account(db_path, VintedAccount(label="X"))

    accounts_store.set_automation_flags(db_path, account.id, auto_publish=True, auto_reply_offers=True)

    fetched = accounts_store.get_account(db_path, account.id)
    assert fetched.auto_publish is True
    assert fetched.auto_reply_offers is True

    accounts_store.set_automation_flags(db_path, account.id, auto_publish=False, auto_reply_offers=False)
    assert accounts_store.get_account(db_path, account.id).auto_publish is False


def test_delete_account(tmp_path) -> None:
    db_path = _db(tmp_path)
    account = accounts_store.create_account(db_path, VintedAccount(label="X"))

    accounts_store.delete_account(db_path, account.id)

    assert accounts_store.get_account(db_path, account.id) is None
