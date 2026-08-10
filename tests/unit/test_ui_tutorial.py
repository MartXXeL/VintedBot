from fastapi.testclient import TestClient

from src.core.security import hash_password
from src.core.settings import Settings
from src.ui.app import create_app

TEST_PASSWORD = "una-contraseña-de-prueba"


def _make_client(tmp_path) -> TestClient:
    settings = Settings(
        database_path=tmp_path / "test.db",
        env_path=tmp_path / ".env",
        dashboard_password_hash=hash_password(TEST_PASSWORD),
    )
    app = create_app(settings, start_worker=False)
    client = TestClient(app)
    client.post("/login", data={"password": TEST_PASSWORD})
    return client


def test_tutorial_exige_sesion(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "test.db", dashboard_password_hash=hash_password(TEST_PASSWORD))
    client = TestClient(create_app(settings, start_worker=False))
    response = client.get("/tutorial", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_tutorial_muestra_todas_las_secciones(tmp_path) -> None:
    client = _make_client(tmp_path)
    response = client.get("/tutorial")

    assert response.status_code == 200
    for anchor in ("conectar", "anuncios", "negociacion", "aprobar", "ritmo", "vendido", "ajustes", "suscripcion", "faq"):
        assert f'id="{anchor}"' in response.text
    assert "precio mínimo" in response.text
    assert "/static/img/vinted-icon.png" in response.text


def test_tutorial_enlazado_desde_la_navegacion(tmp_path) -> None:
    client = _make_client(tmp_path)
    response = client.get("/")
    assert 'href="/tutorial"' in response.text
    assert ">Ayuda</a>" in response.text
