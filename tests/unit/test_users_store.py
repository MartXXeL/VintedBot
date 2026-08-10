from src.core.security import hash_password
from src.storage import users_store
from src.storage.db import init_db


def _db(tmp_path):
    path = tmp_path / "test.db"
    init_db(path)
    return path


def test_create_and_get_user(tmp_path) -> None:
    db_path = _db(tmp_path)
    created = users_store.create_user(db_path, "Admin@Example.com", hash_password("x"), role="admin")

    assert created.id is not None
    assert created.email == "admin@example.com"  # se normaliza en minúsculas
    assert created.role == "admin"
    assert created.is_active is True
    assert created.subscription_status == "none"

    fetched = users_store.get_user(db_path, created.id)
    assert fetched.email == "admin@example.com"


def test_get_user_by_email_normaliza_mayusculas_y_espacios(tmp_path) -> None:
    db_path = _db(tmp_path)
    users_store.create_user(db_path, "persona@example.com", hash_password("x"))

    assert users_store.get_user_by_email(db_path, "  PERSONA@Example.com  ") is not None


def test_get_user_by_email_inexistente(tmp_path) -> None:
    db_path = _db(tmp_path)
    assert users_store.get_user_by_email(db_path, "nadie@example.com") is None


def test_email_duplicado_falla(tmp_path) -> None:
    import sqlite3

    db_path = _db(tmp_path)
    users_store.create_user(db_path, "persona@example.com", hash_password("x"))
    try:
        users_store.create_user(db_path, "persona@example.com", hash_password("y"))
        raise AssertionError("debería haber fallado por email duplicado")
    except sqlite3.IntegrityError:
        pass


def test_list_users_orden_de_creacion(tmp_path) -> None:
    db_path = _db(tmp_path)
    users_store.create_user(db_path, "primero@example.com", hash_password("x"))
    users_store.create_user(db_path, "segundo@example.com", hash_password("x"))

    emails = [u.email for u in users_store.list_users(db_path)]
    assert emails == ["primero@example.com", "segundo@example.com"]


def test_count_users(tmp_path) -> None:
    db_path = _db(tmp_path)
    assert users_store.count_users(db_path) == 0
    users_store.create_user(db_path, "persona@example.com", hash_password("x"))
    assert users_store.count_users(db_path) == 1


def test_set_role(tmp_path) -> None:
    db_path = _db(tmp_path)
    user = users_store.create_user(db_path, "persona@example.com", hash_password("x"))
    users_store.set_role(db_path, user.id, "admin")
    assert users_store.get_user(db_path, user.id).role == "admin"


def test_set_active(tmp_path) -> None:
    db_path = _db(tmp_path)
    user = users_store.create_user(db_path, "persona@example.com", hash_password("x"))
    users_store.set_active(db_path, user.id, False)
    assert users_store.get_user(db_path, user.id).is_active is False


def test_set_password_hash(tmp_path) -> None:
    db_path = _db(tmp_path)
    user = users_store.create_user(db_path, "persona@example.com", hash_password("vieja"))
    users_store.set_password_hash(db_path, user.id, hash_password("nueva"))

    from src.core.security import verify_password

    stored = users_store.get_password_hash(db_path, user.id)
    assert verify_password("nueva", stored)
    assert not verify_password("vieja", stored)


def test_set_subscription(tmp_path) -> None:
    db_path = _db(tmp_path)
    user = users_store.create_user(db_path, "persona@example.com", hash_password("x"))

    users_store.set_subscription(db_path, user.id, "pro", "active")

    updated = users_store.get_user(db_path, user.id)
    assert updated.plan_id == "pro"
    assert updated.subscription_status == "active"
