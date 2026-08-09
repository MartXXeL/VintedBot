from pathlib import Path

from src.core.env_file import is_secret_key, read_env_pairs, update_env_file


def test_read_env_pairs_ignora_comentarios_y_blancos(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# comentario\nA=1\n\nB=hola\n", encoding="utf-8")

    assert read_env_pairs(env_file) == [("A", "1"), ("B", "hola")]


def test_read_env_pairs_archivo_inexistente(tmp_path: Path) -> None:
    assert read_env_pairs(tmp_path / "no_existe.env") == []


def test_update_env_file_preserva_comentarios_y_orden(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# cabecera\nA=1\nB=2\n", encoding="utf-8")

    update_env_file(env_file, {"B": "20"})

    assert env_file.read_text(encoding="utf-8") == "# cabecera\nA=1\nB=20\n"


def test_update_env_file_anade_claves_nuevas_al_final(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("A=1\n", encoding="utf-8")

    update_env_file(env_file, {"C": "3"})

    assert env_file.read_text(encoding="utf-8") == "A=1\nC=3\n"


def test_is_secret_key() -> None:
    assert is_secret_key("ANTHROPIC_API_KEY")
    assert is_secret_key("DASHBOARD_PASSWORD_HASH")
    assert is_secret_key("STRIPE_WEBHOOK_SECRET")
    assert not is_secret_key("DASHBOARD_PORT")
