"""Tests de integración del panel: FastAPI TestClient, sin red real.

Cada test crea su propia app con base de datos y `.env` en `tmp_path`, IA
simulada (por defecto, sin `ANTHROPIC_API_KEY`) y un usuario admin de
contraseña conocida (creado a mano antes de `create_app`, para que el
arranque no genere una aleatoria) para poder probar el login de verdad.
"""

import logging

from fastapi.testclient import TestClient

from src.core.security import hash_password
from src.core.settings import Settings
from src.storage import accounts_store, users_store
from src.storage.db import init_db
from src.ui.app import create_app
from src.vinted.models import VintedAccount

TEST_EMAIL = "admin@example.com"
TEST_PASSWORD = "una-contraseña-de-prueba"


def _make_client(tmp_path, **settings_kwargs) -> TestClient:
    settings = Settings(database_path=tmp_path / "test.db", env_path=tmp_path / ".env", **settings_kwargs)
    init_db(settings.database_path)
    users_store.create_user(str(settings.database_path), TEST_EMAIL, hash_password(TEST_PASSWORD), role="admin")
    app = create_app(settings, start_worker=False)
    return TestClient(app)


def _login(client: TestClient):
    return client.post("/login", data={"email": TEST_EMAIL, "password": TEST_PASSWORD}, follow_redirects=False)


def test_pagina_protegida_sin_sesion_redirige_a_login(tmp_path) -> None:
    client = _make_client(tmp_path)
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_con_contrasena_correcta(tmp_path) -> None:
    client = _make_client(tmp_path)
    response = _login(client)
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert "vintedbot_session" in response.cookies


def test_login_con_contrasena_incorrecta(tmp_path) -> None:
    client = _make_client(tmp_path)
    response = client.post(
        "/login", data={"email": TEST_EMAIL, "password": "incorrecta"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert "error" in response.headers["location"]
    assert "vintedbot_session" not in response.cookies


def test_login_con_email_desconocido_da_error(tmp_path) -> None:
    client = _make_client(tmp_path)
    response = client.post(
        "/login", data={"email": "nadie@example.com", "password": TEST_PASSWORD}, follow_redirects=False
    )
    assert "error" in response.headers["location"]
    assert "vintedbot_session" not in response.cookies


def test_login_de_usuario_desactivado_da_error(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "test.db", env_path=tmp_path / ".env")
    init_db(settings.database_path)
    user = users_store.create_user(str(settings.database_path), TEST_EMAIL, hash_password(TEST_PASSWORD), role="admin")
    users_store.set_active(str(settings.database_path), user.id, False)

    client = TestClient(create_app(settings, start_worker=False))
    response = client.post("/login", data={"email": TEST_EMAIL, "password": TEST_PASSWORD}, follow_redirects=False)

    assert "error" in response.headers["location"]
    assert "vintedbot_session" not in response.cookies


def test_bloqueo_tras_varios_intentos_fallidos(tmp_path) -> None:
    client = _make_client(tmp_path)
    for _ in range(5):
        client.post("/login", data={"email": TEST_EMAIL, "password": "incorrecta"})

    response = client.post(
        "/login", data={"email": TEST_EMAIL, "password": TEST_PASSWORD}, follow_redirects=False
    )
    # Bloqueado incluso con la contraseña correcta: es un bloqueo por IP, no por acierto.
    assert "vintedbot_session" not in response.cookies
    assert "Demasiados" in response.headers["location"]


def test_sesion_valida_da_acceso_al_dashboard(tmp_path) -> None:
    client = _make_client(tmp_path)
    _login(client)

    response = client.get("/")

    assert response.status_code == 200
    assert "Cuentas conectadas" in response.text


def test_logout_invalida_la_sesion(tmp_path) -> None:
    client = _make_client(tmp_path)
    _login(client)

    client.post("/logout")
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_dashboard_lista_cuentas_existentes(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "test.db")
    init_db(settings.database_path)
    admin = users_store.create_user(str(settings.database_path), TEST_EMAIL, hash_password(TEST_PASSWORD), role="admin")
    accounts_store.create_account(
        str(settings.database_path), VintedAccount(label="Mi tienda de ropa"), owner_user_id=admin.id
    )

    client = TestClient(create_app(settings, start_worker=False))
    _login(client)

    response = client.get("/")

    assert "Mi tienda de ropa" in response.text


def test_crear_cuenta_desde_el_dashboard(tmp_path) -> None:
    client = _make_client(tmp_path)
    _login(client)

    response = client.post(
        "/accounts",
        data={"label": "Cuenta nueva", "connection_mode": "session", "session_cookie": "access_token_web=abc"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "ok=" in response.headers["location"]
    dashboard = client.get("/")
    assert "Cuenta nueva" in dashboard.text


def test_crear_cuenta_sesion_sin_cookie_falla(tmp_path) -> None:
    client = _make_client(tmp_path)
    _login(client)

    response = client.post(
        "/accounts",
        data={"label": "Sin cookie", "connection_mode": "session", "session_cookie": ""},
        follow_redirects=False,
    )

    assert "error=" in response.headers["location"]


def test_toggle_automation_flags(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "test.db")
    init_db(settings.database_path)
    admin = users_store.create_user(str(settings.database_path), TEST_EMAIL, hash_password(TEST_PASSWORD), role="admin")
    account = accounts_store.create_account(str(settings.database_path), VintedAccount(label="X"), owner_user_id=admin.id)

    client = TestClient(create_app(settings, start_worker=False))
    _login(client)

    client.post(f"/accounts/{account.id}/automation", data={"auto_publish": "on"})

    updated = accounts_store.get_account(str(settings.database_path), account.id)
    assert updated.auto_publish is True
    assert updated.auto_reply_offers is False  # no se mandó -> se desmarca


def test_reconectar_sesion_renueva_la_cookie_y_el_estado(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "test.db")
    init_db(settings.database_path)
    admin = users_store.create_user(str(settings.database_path), TEST_EMAIL, hash_password(TEST_PASSWORD), role="admin")
    account = accounts_store.create_account(
        str(settings.database_path),
        VintedAccount(label="X"),
        session_cookie="access_token_web=vieja",
        owner_user_id=admin.id,
    )
    accounts_store.update_account_status(str(settings.database_path), account.id, "error")

    client = TestClient(create_app(settings, start_worker=False))
    _login(client)

    response = client.post(
        f"/accounts/{account.id}/reconnect",
        data={"session_cookie": "access_token_web=nueva"},
        follow_redirects=False,
    )

    assert "ok=" in response.headers["location"]
    updated = accounts_store.get_account(str(settings.database_path), account.id)
    assert updated.status == "connected"
    assert accounts_store.get_account_session_cookie(str(settings.database_path), account.id) == "access_token_web=nueva"


def test_reconectar_sesion_en_blanco_da_error(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "test.db")
    init_db(settings.database_path)
    admin = users_store.create_user(str(settings.database_path), TEST_EMAIL, hash_password(TEST_PASSWORD), role="admin")
    account = accounts_store.create_account(str(settings.database_path), VintedAccount(label="X"), owner_user_id=admin.id)

    client = TestClient(create_app(settings, start_worker=False))
    _login(client)

    response = client.post(
        f"/accounts/{account.id}/reconnect", data={"session_cookie": "  "}, follow_redirects=False
    )

    assert "error=" in response.headers["location"]


def test_reconectar_cuenta_inexistente_da_error(tmp_path) -> None:
    client = _make_client(tmp_path)
    _login(client)
    response = client.post(
        "/accounts/999/reconnect", data={"session_cookie": "algo"}, follow_redirects=False
    )
    assert "error=" in response.headers["location"]


def test_delete_account_desde_el_panel(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "test.db")
    init_db(settings.database_path)
    admin = users_store.create_user(str(settings.database_path), TEST_EMAIL, hash_password(TEST_PASSWORD), role="admin")
    account = accounts_store.create_account(str(settings.database_path), VintedAccount(label="Borrar"), owner_user_id=admin.id)

    client = TestClient(create_app(settings, start_worker=False))
    _login(client)

    client.post(f"/accounts/{account.id}/delete")

    assert accounts_store.get_account(str(settings.database_path), account.id) is None


def test_member_no_ve_ni_gestiona_cuentas_de_otro(tmp_path) -> None:
    """El escopado por propietario es la base de todo el resto de rutas: se prueba aquí a fondo."""
    settings = Settings(database_path=tmp_path / "test.db")
    init_db(settings.database_path)
    db_path = str(settings.database_path)
    admin = users_store.create_user(db_path, TEST_EMAIL, hash_password(TEST_PASSWORD), role="admin")
    member = users_store.create_user(db_path, "member@example.com", hash_password("otra-contraseña"), role="member")
    accounts_store.create_account(db_path, VintedAccount(label="De admin"), owner_user_id=admin.id)
    de_member = accounts_store.create_account(db_path, VintedAccount(label="De member"), owner_user_id=member.id)

    client = TestClient(create_app(settings, start_worker=False))
    client.post("/login", data={"email": "member@example.com", "password": "otra-contraseña"})

    dashboard = client.get("/")
    assert "De member" in dashboard.text
    assert "De admin" not in dashboard.text

    # Y no puede tocar una cuenta ajena aunque adivine su id.
    other_account = accounts_store.list_accounts(db_path, owner_user_id=admin.id)[0]
    response = client.post(f"/accounts/{other_account.id}/delete", follow_redirects=False)
    assert "error=" in response.headers["location"]
    assert accounts_store.get_account(db_path, other_account.id) is not None

    # Y su propia cuenta sí la puede borrar.
    response = client.post(f"/accounts/{de_member.id}/delete", follow_redirects=False)
    assert "ok=" in response.headers["location"]


def test_admin_ve_las_cuentas_de_todo_el_mundo(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "test.db")
    init_db(settings.database_path)
    db_path = str(settings.database_path)
    admin = users_store.create_user(db_path, TEST_EMAIL, hash_password(TEST_PASSWORD), role="admin")
    member = users_store.create_user(db_path, "member@example.com", hash_password("otra-contraseña"), role="member")
    accounts_store.create_account(db_path, VintedAccount(label="De admin"), owner_user_id=admin.id)
    accounts_store.create_account(db_path, VintedAccount(label="De member"), owner_user_id=member.id)

    client = TestClient(create_app(settings, start_worker=False))
    _login(client)

    dashboard = client.get("/")
    assert "De admin" in dashboard.text
    assert "De member" in dashboard.text


# --------------------------------------------------------------------------- #
#  Aviso de exposición sin HTTPS (DASHBOARD_HOST no-loopback + sin forzar HTTPS)
# --------------------------------------------------------------------------- #


def test_avisa_si_se_expone_sin_https(tmp_path, caplog) -> None:
    settings = Settings(
        database_path=tmp_path / "test.db",
        dashboard_host="0.0.0.0",
        dashboard_force_https=False,
    )
    with caplog.at_level(logging.WARNING, logger="VintedBot"):
        create_app(settings, start_worker=False)

    assert any("no es loopback" in record.message for record in caplog.records)


def test_no_avisa_en_loopback(tmp_path, caplog) -> None:
    settings = Settings(
        database_path=tmp_path / "test.db",
        dashboard_host="127.0.0.1",
        dashboard_force_https=False,
    )
    with caplog.at_level(logging.WARNING, logger="VintedBot"):
        create_app(settings, start_worker=False)

    assert not any("no es loopback" in record.message for record in caplog.records)


def test_no_avisa_si_ya_se_fuerza_https(tmp_path, caplog) -> None:
    settings = Settings(
        database_path=tmp_path / "test.db",
        dashboard_host="0.0.0.0",
        dashboard_force_https=True,
    )
    with caplog.at_level(logging.WARNING, logger="VintedBot"):
        create_app(settings, start_worker=False)

    assert not any("no es loopback" in record.message for record in caplog.records)
