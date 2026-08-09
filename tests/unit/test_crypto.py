from src.storage import crypto

# El aislamiento de la clave (propio .env de prueba en tmp_path) lo da la
# fixture autouse `_clave_de_cifrado_aislada` de tests/unit/conftest.py.


def test_encrypt_decrypt_roundtrip() -> None:
    original = "cookie-de-sesion-secreta=abc123"
    encrypted = crypto.encrypt_text(original)

    assert encrypted != original
    assert crypto.decrypt_text(encrypted) == original


def test_encrypt_none_devuelve_none() -> None:
    assert crypto.encrypt_text(None) is None
    assert crypto.decrypt_text(None) is None


def test_decrypt_texto_no_cifrado_lo_devuelve_igual() -> None:
    """Compatibilidad con filas escritas antes de activar el cifrado."""
    assert crypto.decrypt_text("texto-en-claro") == "texto-en-claro"


def test_la_clave_se_genera_y_persiste_en_env(tmp_path) -> None:
    crypto.encrypt_text("dato")
    env_path = tmp_path / ".env"
    assert env_path.exists()
    assert "DB_ENCRYPTION_KEY=" in env_path.read_text(encoding="utf-8")


def test_la_clave_generada_se_reutiliza_entre_llamadas() -> None:
    encrypted = crypto.encrypt_text("dato")
    crypto.reset_fernet_cache()  # simula un nuevo proceso releyendo el .env
    assert crypto.decrypt_text(encrypted) == "dato"
