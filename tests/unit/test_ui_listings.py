import io

from fastapi.testclient import TestClient
from PIL import Image

from src.core.security import hash_password
from src.core.settings import Settings
from src.storage import accounts_store, listings_store
from src.ui.app import create_app
from src.vinted.models import Listing, VintedAccount

TEST_PASSWORD = "una-contraseña-de-prueba"


class _FakeSessionClient:
    def __init__(self, publish_result=None):
        self.publish_result = publish_result or {"id": "item-777"}
        self.published_payloads = []
        self.closed = False

    async def upload_photo(self, photo_bytes: bytes, filename: str = "foto.jpg") -> str:
        return "photo-1"

    async def publish_listing(self, payload: dict) -> dict:
        self.published_payloads.append(payload)
        return self.publish_result

    async def aclose(self) -> None:
        self.closed = True


class _FakeApiClient:
    def __init__(self, create_item_result=None):
        self.create_item_result = create_item_result or {"id": "official-1"}
        self.created_payloads = []
        self.closed = False

    async def create_item(self, payload: dict) -> dict:
        self.created_payloads.append(payload)
        return self.create_item_result

    async def aclose(self) -> None:
        self.closed = True


def _fake_jpeg_bytes() -> bytes:
    image = Image.new("RGB", (200, 200), (10, 20, 30))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _make_client(tmp_path, fake_session_client=None) -> TestClient:
    settings = Settings(
        database_path=tmp_path / "test.db",
        env_path=tmp_path / ".env",
        dashboard_password_hash=hash_password(TEST_PASSWORD),
    )
    app = create_app(
        settings,
        start_worker=False,
        session_client_factory=(lambda domain, cookie: fake_session_client) if fake_session_client else None,
    )
    client = TestClient(app)
    client.post("/login", data={"password": TEST_PASSWORD})
    return client, settings


def test_generar_anuncio_con_ia_crea_un_borrador(tmp_path) -> None:
    client, settings = _make_client(tmp_path)
    account = accounts_store.create_account(str(settings.database_path), VintedAccount(label="Mi tienda"))

    response = client.post(
        "/listings/generate",
        data={"account_id": account.id, "price": "20", "min_price": "12", "extra_context": "casi nuevo"},
        files={"photos": ("foto.jpg", _fake_jpeg_bytes(), "image/jpeg")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "/edit" in response.headers["location"]
    listings = listings_store.list_listings(str(settings.database_path), account_id=account.id)
    assert len(listings) == 1
    assert listings[0].ai_generated is True
    assert listings[0].status == "draft"
    assert listings[0].min_price == 12.0


def test_generar_anuncio_sin_fotos_da_error(tmp_path) -> None:
    client, settings = _make_client(tmp_path)
    account = accounts_store.create_account(str(settings.database_path), VintedAccount(label="X"))

    response = client.post(
        "/listings/generate",
        data={"account_id": account.id, "price": "20", "min_price": "12"},
        files={"photos": ("vacio.jpg", b"", "image/jpeg")},
        follow_redirects=False,
    )

    assert "error=" in response.headers["location"]


def test_generar_anuncio_cuenta_inexistente_da_error(tmp_path) -> None:
    client, _settings = _make_client(tmp_path)

    response = client.post(
        "/listings/generate",
        data={"account_id": 999, "price": "20", "min_price": "12"},
        files={"photos": ("foto.jpg", _fake_jpeg_bytes(), "image/jpeg")},
        follow_redirects=False,
    )

    assert "error=" in response.headers["location"]


def test_editar_anuncio_guarda_cambios(tmp_path) -> None:
    client, settings = _make_client(tmp_path)
    account = accounts_store.create_account(str(settings.database_path), VintedAccount(label="X"))
    listing = listings_store.create_listing(
        str(settings.database_path), Listing(account_id=account.id, title="Antes", price=10.0)
    )

    response = client.post(
        f"/listings/{listing.id}",
        data={
            "title": "Después",
            "description": "nueva",
            "category": "",
            "brand": "",
            "size": "",
            "item_condition": "",
            "price": "15",
            "min_price": "10",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    updated = listings_store.get_listing(str(settings.database_path), listing.id)
    assert updated.title == "Después"
    assert updated.min_price == 10.0


def test_pagina_de_edicion_muestra_las_fotos(tmp_path) -> None:
    client, settings = _make_client(tmp_path)
    account = accounts_store.create_account(str(settings.database_path), VintedAccount(label="X"))
    photo = tmp_path / "foto.jpg"
    photo.write_bytes(b"\xff\xd8\xff-jpeg-falso")
    listing = listings_store.create_listing(
        str(settings.database_path),
        Listing(account_id=account.id, title="Con fotos", photo_paths=[str(photo)]),
    )

    response = client.get(f"/listings/{listing.id}/edit")

    assert response.status_code == 200
    assert "Con fotos" in response.text
    assert f"/listings/{listing.id}/photos/0" in response.text


def test_foto_del_anuncio_exige_sesion(tmp_path) -> None:
    """La foto vive detrás de login, a diferencia de un StaticFiles suelto."""
    client, settings = _make_client(tmp_path)
    account = accounts_store.create_account(str(settings.database_path), VintedAccount(label="X"))
    photo = tmp_path / "foto.jpg"
    photo.write_bytes(b"\xff\xd8\xff-jpeg-falso")
    listing = listings_store.create_listing(
        str(settings.database_path),
        Listing(account_id=account.id, photo_paths=[str(photo)]),
    )

    client.post("/logout")
    response = client.get(f"/listings/{listing.id}/photos/0", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_foto_del_anuncio_autenticada_se_sirve(tmp_path) -> None:
    client, settings = _make_client(tmp_path)
    account = accounts_store.create_account(str(settings.database_path), VintedAccount(label="X"))
    photo = tmp_path / "foto.jpg"
    photo.write_bytes(b"\xff\xd8\xff-contenido-jpeg-falso")
    listing = listings_store.create_listing(
        str(settings.database_path),
        Listing(account_id=account.id, photo_paths=[str(photo)]),
    )

    response = client.get(f"/listings/{listing.id}/photos/0")

    assert response.status_code == 200
    assert response.content == b"\xff\xd8\xff-contenido-jpeg-falso"


def test_foto_indice_fuera_de_rango_da_404(tmp_path) -> None:
    client, settings = _make_client(tmp_path)
    account = accounts_store.create_account(str(settings.database_path), VintedAccount(label="X"))
    listing = listings_store.create_listing(
        str(settings.database_path), Listing(account_id=account.id, photo_paths=[])
    )

    response = client.get(f"/listings/{listing.id}/photos/0")

    assert response.status_code == 404


def test_foto_de_anuncio_inexistente_da_404(tmp_path) -> None:
    client, _settings = _make_client(tmp_path)
    response = client.get("/listings/999/photos/0")
    assert response.status_code == 404


def test_publicar_sin_min_price_da_error(tmp_path) -> None:
    client, settings = _make_client(tmp_path, fake_session_client=_FakeSessionClient())
    account = accounts_store.create_account(
        str(settings.database_path), VintedAccount(label="X"), session_cookie="access_token_web=abc"
    )
    accounts_store.update_account_status(str(settings.database_path), account.id, "connected")
    listing = listings_store.create_listing(
        str(settings.database_path),
        Listing(account_id=account.id, title="Sin mínimo", photo_paths=["a.jpg"]),  # sin min_price
    )

    response = client.post(f"/listings/{listing.id}/publish", follow_redirects=False)

    assert "error=" in response.headers["location"]


def test_publicar_con_todo_listo_publica_de_verdad(tmp_path) -> None:
    fake_client = _FakeSessionClient(publish_result={"id": "item-777"})
    client, settings = _make_client(tmp_path, fake_session_client=fake_client)
    account = accounts_store.create_account(
        str(settings.database_path), VintedAccount(label="X"), session_cookie="access_token_web=abc"
    )
    photo = tmp_path / "foto.jpg"
    photo.write_bytes(b"\xff\xd8\xff-jpeg-falso")
    listing = listings_store.create_listing(
        str(settings.database_path),
        Listing(account_id=account.id, title="Listo", price=20.0, min_price=15.0, photo_paths=[str(photo)]),
    )

    response = client.post(f"/listings/{listing.id}/publish", follow_redirects=False)

    assert "ok=" in response.headers["location"]
    assert fake_client.closed is True
    updated = listings_store.get_listing(str(settings.database_path), listing.id)
    assert updated.status == "published"
    assert updated.vinted_item_id == "item-777"


def test_publicar_cuenta_api_sin_credenciales_da_error(tmp_path) -> None:
    client, settings = _make_client(tmp_path)
    account = accounts_store.create_account(
        str(settings.database_path), VintedAccount(label="X", connection_mode="api")
    )
    listing = listings_store.create_listing(
        str(settings.database_path),
        Listing(account_id=account.id, title="X", price=20.0, min_price=15.0, photo_paths=["a.jpg"]),
    )

    response = client.post(f"/listings/{listing.id}/publish", follow_redirects=False)

    assert "error=" in response.headers["location"]


def test_publicar_cuenta_api_con_credenciales_publica_de_verdad(tmp_path) -> None:
    fake_api_client = _FakeApiClient(create_item_result={"id": "official-42"})
    settings = Settings(
        database_path=tmp_path / "test.db",
        env_path=tmp_path / ".env",
        dashboard_password_hash=hash_password(TEST_PASSWORD),
        vinted_api_client_id="cid",
        vinted_api_client_secret="secret",
    )
    app = create_app(settings, start_worker=False, api_client_factory=lambda s: fake_api_client)
    client = TestClient(app)
    client.post("/login", data={"password": TEST_PASSWORD})

    account = accounts_store.create_account(
        str(settings.database_path), VintedAccount(label="X", connection_mode="api")
    )
    photo = tmp_path / "foto.jpg"
    photo.write_bytes(b"\xff\xd8\xff-jpeg-falso")
    listing = listings_store.create_listing(
        str(settings.database_path),
        Listing(account_id=account.id, title="Bolso", price=20.0, min_price=15.0, photo_paths=[str(photo)]),
    )

    response = client.post(f"/listings/{listing.id}/publish", follow_redirects=False)

    assert "ok=" in response.headers["location"]
    assert fake_api_client.closed is True
    assert len(fake_api_client.created_payloads) == 1
    updated = listings_store.get_listing(str(settings.database_path), listing.id)
    assert updated.status == "published"
    assert updated.vinted_item_id == "official-42"


def test_borrar_anuncio(tmp_path) -> None:
    client, settings = _make_client(tmp_path)
    account = accounts_store.create_account(str(settings.database_path), VintedAccount(label="X"))
    listing = listings_store.create_listing(str(settings.database_path), Listing(account_id=account.id))

    client.post(f"/listings/{listing.id}/delete")

    assert listings_store.get_listing(str(settings.database_path), listing.id) is None
