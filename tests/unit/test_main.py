import src.main


def test_main_es_invocable() -> None:
    assert callable(src.main.main)
