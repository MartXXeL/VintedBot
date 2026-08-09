from src.storage.db import connect, init_db


def test_init_db_crea_las_tablas(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    init_db(db_path)

    with connect(db_path) as conn:
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }

    assert {"accounts", "listings", "offers", "sales", "actions_log"} <= tables


def test_init_db_es_idempotente(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    init_db(db_path)
    init_db(db_path)  # no debe fallar al volver a crear las tablas


def test_foreign_keys_activas(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    init_db(db_path)

    with connect(db_path) as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
