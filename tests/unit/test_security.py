from src.core.security import generate_random_password, hash_password, verify_password


def test_hash_password_verifica_correctamente() -> None:
    stored = hash_password("una-contraseña-segura")

    assert verify_password("una-contraseña-segura", stored)
    assert not verify_password("otra-cosa", stored)


def test_hash_password_genera_sal_distinta_cada_vez() -> None:
    assert hash_password("misma") != hash_password("misma")


def test_verify_password_con_hash_vacio_o_none() -> None:
    assert not verify_password("cualquiera", None)
    assert not verify_password("cualquiera", "")


def test_verify_password_con_hash_corrupto() -> None:
    assert not verify_password("cualquiera", "esto-no-es-un-hash-valido")


def test_generate_random_password_longitud_y_variedad() -> None:
    p1 = generate_random_password()
    p2 = generate_random_password()
    assert len(p1) == 16
    assert p1 != p2
