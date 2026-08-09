from datetime import timedelta

from src.ui.login_guard import LoginGuard


def test_no_bloqueado_al_principio() -> None:
    guard = LoginGuard()
    assert not guard.is_locked_out("1.2.3.4")


def test_bloquea_tras_el_maximo_de_fallos() -> None:
    guard = LoginGuard(max_attempts=3)
    for _ in range(3):
        guard.register_failure("1.2.3.4")
    assert guard.is_locked_out("1.2.3.4")


def test_no_bloquea_por_debajo_del_maximo() -> None:
    guard = LoginGuard(max_attempts=3)
    guard.register_failure("1.2.3.4")
    guard.register_failure("1.2.3.4")
    assert not guard.is_locked_out("1.2.3.4")


def test_ips_independientes() -> None:
    guard = LoginGuard(max_attempts=1)
    guard.register_failure("1.1.1.1")
    assert guard.is_locked_out("1.1.1.1")
    assert not guard.is_locked_out("2.2.2.2")


def test_exito_limpia_los_fallos() -> None:
    guard = LoginGuard(max_attempts=2)
    guard.register_failure("1.2.3.4")
    guard.register_success("1.2.3.4")
    guard.register_failure("1.2.3.4")
    assert not guard.is_locked_out("1.2.3.4")


def test_los_fallos_viejos_expiran() -> None:
    guard = LoginGuard(max_attempts=1, lockout=timedelta(seconds=-1))  # ya expirado
    guard.register_failure("1.2.3.4")
    assert not guard.is_locked_out("1.2.3.4")
