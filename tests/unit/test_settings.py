from src.core.settings import load_settings


def test_load_settings_valores_por_defecto(monkeypatch) -> None:
    for name in (
        "ANTHROPIC_API_KEY",
        "AI_PROVIDER",
        "DASHBOARD_PORT",
        "RATE_LIMIT_MAX_ACTIONS_PER_DAY",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = load_settings()

    assert settings.dashboard_port == 8080
    assert settings.rate_limit.max_actions_per_day == 50
    assert settings.dac7.alert_amount_eur == 2000.0
    assert settings.resolve_ai_provider() == "mock"


def test_resolve_ai_provider_usa_anthropic_si_hay_clave(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("AI_PROVIDER", "auto")

    settings = load_settings()

    assert settings.resolve_ai_provider() == "anthropic"


def test_resolve_ai_provider_respeta_valor_explicito(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("AI_PROVIDER", "mock")

    settings = load_settings()

    assert settings.resolve_ai_provider() == "mock"


def test_env_int_invalido_cae_al_default(monkeypatch) -> None:
    monkeypatch.setenv("DASHBOARD_PORT", "no-es-un-numero")

    settings = load_settings()

    assert settings.dashboard_port == 8080
