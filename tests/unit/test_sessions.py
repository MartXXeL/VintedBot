from datetime import timedelta

from src.ui.sessions import SessionStore


def test_create_y_validar() -> None:
    store = SessionStore()
    token = store.create()
    assert store.is_valid(token)


def test_token_invalido_o_vacio() -> None:
    store = SessionStore()
    assert not store.is_valid(None)
    assert not store.is_valid("")
    assert not store.is_valid("no-existe")


def test_invalidate() -> None:
    store = SessionStore()
    token = store.create()
    store.invalidate(token)
    assert not store.is_valid(token)


def test_invalidate_token_inexistente_no_falla() -> None:
    store = SessionStore()
    store.invalidate("no-existe")  # no debe lanzar


def test_sesion_expirada() -> None:
    store = SessionStore(ttl=timedelta(seconds=-1))  # ya caducado al crearlo
    token = store.create()
    assert not store.is_valid(token)


def test_cada_token_es_distinto() -> None:
    store = SessionStore()
    assert store.create() != store.create()
