from datetime import timedelta

from src.ui.sessions import SessionStore


def test_create_y_validar() -> None:
    store = SessionStore()
    token = store.create(user_id=1)
    assert store.is_valid(token)
    assert store.get_user_id(token) == 1


def test_token_invalido_o_vacio() -> None:
    store = SessionStore()
    assert not store.is_valid(None)
    assert not store.is_valid("")
    assert not store.is_valid("no-existe")
    assert store.get_user_id(None) is None
    assert store.get_user_id("no-existe") is None


def test_invalidate() -> None:
    store = SessionStore()
    token = store.create(user_id=1)
    store.invalidate(token)
    assert not store.is_valid(token)


def test_invalidate_token_inexistente_no_falla() -> None:
    store = SessionStore()
    store.invalidate("no-existe")  # no debe lanzar


def test_sesion_expirada() -> None:
    store = SessionStore(ttl=timedelta(seconds=-1))  # ya caducado al crearlo
    token = store.create(user_id=1)
    assert not store.is_valid(token)


def test_cada_token_es_distinto() -> None:
    store = SessionStore()
    assert store.create(user_id=1) != store.create(user_id=1)


def test_cada_sesion_recuerda_su_propio_usuario() -> None:
    store = SessionStore()
    token_a = store.create(user_id=1)
    token_b = store.create(user_id=2)
    assert store.get_user_id(token_a) == 1
    assert store.get_user_id(token_b) == 2
