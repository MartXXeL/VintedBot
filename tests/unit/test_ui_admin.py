"""Tests de la pantalla de administración: gestionar perfiles, roles y suscripciones."""

from fastapi.testclient import TestClient

from src.core.security import hash_password, verify_password
from src.core.settings import Settings
from src.storage import users_store
from src.storage.db import init_db
from src.ui.app import create_app

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "una-contraseña-de-prueba"
MEMBER_EMAIL = "miembro@example.com"
MEMBER_PASSWORD = "otra-contraseña"


def _make_app(tmp_path):
    settings = Settings(database_path=tmp_path / "test.db", env_path=tmp_path / ".env")
    init_db(settings.database_path)
    db_path = str(settings.database_path)
    users_store.create_user(db_path, ADMIN_EMAIL, hash_password(ADMIN_PASSWORD), role="admin")
    users_store.create_user(db_path, MEMBER_EMAIL, hash_password(MEMBER_PASSWORD), role="member")
    return create_app(settings, start_worker=False), settings


def _login(client: TestClient, email: str, password: str):
    return client.post("/login", data={"email": email, "password": password})


def test_admin_exige_sesion(tmp_path) -> None:
    app, _settings = _make_app(tmp_path)
    client = TestClient(app)
    response = client.get("/admin", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_member_no_puede_entrar_a_admin(tmp_path) -> None:
    app, _settings = _make_app(tmp_path)
    client = TestClient(app)
    _login(client, MEMBER_EMAIL, MEMBER_PASSWORD)

    response = client.get("/admin", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/?error=")


def test_member_no_puede_entrar_a_ajustes(tmp_path) -> None:
    app, _settings = _make_app(tmp_path)
    client = TestClient(app)
    _login(client, MEMBER_EMAIL, MEMBER_PASSWORD)

    response = client.get("/settings", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/?error=")


def test_admin_ve_la_lista_de_perfiles(tmp_path) -> None:
    app, _settings = _make_app(tmp_path)
    client = TestClient(app)
    _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)

    response = client.get("/admin")

    assert response.status_code == 200
    assert ADMIN_EMAIL in response.text
    assert MEMBER_EMAIL in response.text


def test_admin_crea_un_perfil_nuevo(tmp_path) -> None:
    app, settings = _make_app(tmp_path)
    client = TestClient(app)
    _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)

    response = client.post(
        "/admin/users", data={"email": "nueva@example.com", "role": "member"}, follow_redirects=False
    )

    assert "ok=" in response.headers["location"]
    created = users_store.get_user_by_email(str(settings.database_path), "nueva@example.com")
    assert created is not None
    assert created.role == "member"
    assert created.is_active is True


def test_admin_crea_perfil_con_email_duplicado_da_error(tmp_path) -> None:
    app, _settings = _make_app(tmp_path)
    client = TestClient(app)
    _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)

    response = client.post(
        "/admin/users", data={"email": ADMIN_EMAIL, "role": "member"}, follow_redirects=False
    )

    assert "error=" in response.headers["location"]


def test_admin_cambia_el_rol_de_un_miembro(tmp_path) -> None:
    app, settings = _make_app(tmp_path)
    client = TestClient(app)
    _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    member = users_store.get_user_by_email(str(settings.database_path), MEMBER_EMAIL)

    response = client.post(f"/admin/users/{member.id}/role", data={"role": "admin"}, follow_redirects=False)

    assert "ok=" in response.headers["location"]
    assert users_store.get_user(str(settings.database_path), member.id).role == "admin"


def test_admin_no_puede_quitarse_su_propio_rol(tmp_path) -> None:
    app, settings = _make_app(tmp_path)
    client = TestClient(app)
    _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    admin = users_store.get_user_by_email(str(settings.database_path), ADMIN_EMAIL)

    response = client.post(f"/admin/users/{admin.id}/role", data={"role": "member"}, follow_redirects=False)

    assert "error=" in response.headers["location"]
    assert users_store.get_user(str(settings.database_path), admin.id).role == "admin"


def test_admin_desactiva_y_reactiva_un_miembro(tmp_path) -> None:
    app, settings = _make_app(tmp_path)
    client = TestClient(app)
    _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    member = users_store.get_user_by_email(str(settings.database_path), MEMBER_EMAIL)

    client.post(f"/admin/users/{member.id}/active", data={})  # sin marcar el checkbox = desactivar
    assert users_store.get_user(str(settings.database_path), member.id).is_active is False

    client.post(f"/admin/users/{member.id}/active", data={"is_active": "on"})
    assert users_store.get_user(str(settings.database_path), member.id).is_active is True


def test_desactivar_un_miembro_le_cierra_el_acceso(tmp_path) -> None:
    app, settings = _make_app(tmp_path)
    admin_client = TestClient(app)
    _login(admin_client, ADMIN_EMAIL, ADMIN_PASSWORD)
    member = users_store.get_user_by_email(str(settings.database_path), MEMBER_EMAIL)
    admin_client.post(f"/admin/users/{member.id}/active", data={})

    member_client = TestClient(app)
    response = member_client.post(
        "/login", data={"email": MEMBER_EMAIL, "password": MEMBER_PASSWORD}, follow_redirects=False
    )

    assert "error=" in response.headers["location"]
    assert "vintedbot_session" not in response.cookies


def test_admin_no_puede_desactivarse_a_si_mismo(tmp_path) -> None:
    app, settings = _make_app(tmp_path)
    client = TestClient(app)
    _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    admin = users_store.get_user_by_email(str(settings.database_path), ADMIN_EMAIL)

    response = client.post(f"/admin/users/{admin.id}/active", data={}, follow_redirects=False)

    assert "error=" in response.headers["location"]
    assert users_store.get_user(str(settings.database_path), admin.id).is_active is True


def test_admin_asigna_una_suscripcion(tmp_path) -> None:
    app, settings = _make_app(tmp_path)
    client = TestClient(app)
    _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    member = users_store.get_user_by_email(str(settings.database_path), MEMBER_EMAIL)

    response = client.post(
        f"/admin/users/{member.id}/subscription",
        data={"plan_id": "pro", "subscription_status": "active"},
        follow_redirects=False,
    )

    assert "ok=" in response.headers["location"]
    updated = users_store.get_user(str(settings.database_path), member.id)
    assert updated.plan_id == "pro"
    assert updated.subscription_status == "active"


def test_admin_restablece_la_contrasena_de_un_miembro(tmp_path) -> None:
    app, settings = _make_app(tmp_path)
    client = TestClient(app)
    _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    member = users_store.get_user_by_email(str(settings.database_path), MEMBER_EMAIL)

    response = client.post(f"/admin/users/{member.id}/reset-password", follow_redirects=False)

    assert "ok=" in response.headers["location"]
    new_hash = users_store.get_password_hash(str(settings.database_path), member.id)
    assert not verify_password(MEMBER_PASSWORD, new_hash)  # la contraseña vieja ya no sirve

    member_client = TestClient(app)
    old_login = _login(member_client, MEMBER_EMAIL, MEMBER_PASSWORD)
    assert "vintedbot_session" not in old_login.cookies
