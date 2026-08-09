"""Tests de integración del panel: FastAPI TestClient, sin red real.

Cada test crea su propia app con base de datos y `.env` en `tmp_path`, IA
simulada (por defecto, sin `ANTHROPIC_API_KEY`) y una contraseña conocida
para poder probar el login de verdad.
"""

from fastapi.testclient import TestClient

from src.core.security import hash_password
from src.core.settings import Settings
from src.storage import accounts_store
from src.storage.db import init_db
from src.ui.app import create_app
from src.vinted.models import VintedAccount

TEST_PASSWORD = "una-contraseña-de-prueba"


def _make_client(tmp_path, **settings_kwargs) -> TestClient:
    settings = Settings(
        database_path=tmp_path / "test.db",
        env_path=tmp_path / ".env",
        dashboard_password_hash=hash_password(TEST_PASSWORD),
        **settings_kwargs,
    )
    app = create_app(settings, start_worker=False)
    return TestClient(app)


def test_pagina_protegida_sin_sesion_redirige_a_login(tmp_path) -> None:
    client = _make_client(tmp_path)
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_con_contrasena_correcta(tmp_path) -> None:
    client = _make_client(tmp_path)
    response = client.post("/login", data={"password": TEST_PASSWORD}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert "vintedbot_session" in response.cookies


def test_login_con_contrasena_incorrecta(tmp_path) -> None:
    client = _make_client(tmp_path)
    response = client.post("/login", data={"password": "incorrecta"}, follow_redirects=False)
    assert response.status_code == 303
    assert "error" in response.headers["location"]
    assert "vintedbot_session" not in response.cookies


def test_bloqueo_tras_varios_intentos_fallidos(tmp_path) -> None:
    client = _make_client(tmp_path)
    for _ in range(5):
        client.post("/login", data={"password": "incorrecta"})

    response = client.post("/login", data={"password": TEST_PASSWORD}, follow_redirects=False)
    # Bloqueado incluso con la contraseña correcta: es un bloqueo por IP, no por acierto.
    assert "vintedbot_session" not in response.cookies
    assert "Demasiados" in response.headers["location"]


def test_sesion_valida_da_acceso_al_dashboard(tmp_path) -> None:
    client = _make_client(tmp_path)
    client.post("/login", data={"password": TEST_PASSWORD})

    response = client.get("/")

    assert response.status_code == 200
    assert "Cuentas conectadas" in response.text


def test_logout_invalida_la_sesion(tmp_path) -> None:
    client = _make_client(tmp_path)
    client.post("/login", data={"password": TEST_PASSWORD})

    client.post("/logout")
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_dashboard_lista_cuentas_existentes(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "test.db", dashboard_password_hash=hash_password(TEST_PASSWORD))
    init_db(settings.database_path)
    accounts_store.create_account(str(settings.database_path), VintedAccount(label="Mi tienda de ropa"))

    client = TestClient(create_app(settings, start_worker=False))
    client.post("/login", data={"password": TEST_PASSWORD})

    response = client.get("/")

    assert "Mi tienda de ropa" in response.text


def test_crear_cuenta_desde_el_dashboard(tmp_path) -> None:
    client = _make_client(tmp_path)
    client.post("/login", data={"password": TEST_PASSWORD})

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
    client.post("/login", data={"password": TEST_PASSWORD})

    response = client.post(
        "/accounts",
        data={"label": "Sin cookie", "connection_mode": "session", "session_cookie": ""},
        follow_redirects=False,
    )

    assert "error=" in response.headers["location"]


def test_toggle_automation_flags(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "test.db", dashboard_password_hash=hash_password(TEST_PASSWORD))
    init_db(settings.database_path)
    account = accounts_store.create_account(str(settings.database_path), VintedAccount(label="X"))

    client = TestClient(create_app(settings, start_worker=False))
    client.post("/login", data={"password": TEST_PASSWORD})

    client.post(f"/accounts/{account.id}/automation", data={"auto_publish": "on"})

    updated = accounts_store.get_account(str(settings.database_path), account.id)
    assert updated.auto_publish is True
    assert updated.auto_reply_offers is False  # no se mandó -> se desmarca


def test_delete_account_desde_el_panel(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "test.db", dashboard_password_hash=hash_password(TEST_PASSWORD))
    init_db(settings.database_path)
    account = accounts_store.create_account(str(settings.database_path), VintedAccount(label="Borrar"))

    client = TestClient(create_app(settings, start_worker=False))
    client.post("/login", data={"password": TEST_PASSWORD})

    client.post(f"/accounts/{account.id}/delete")

    assert accounts_store.get_account(str(settings.database_path), account.id) is None
