"""Configuración centralizada, leída de variables de entorno (`.env`).

Todo tiene un valor por defecto sensato: la app debe poder arrancar en una
máquina recién clonada, sin ninguna credencial, para poder explorarla y
probarla (con la IA en modo simulado y sin cuentas de Vinted conectadas).
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class RateLimitSettings:
    """Cadencia segura de la vía de sesión: protege las cuentas conectadas."""

    min_seconds: int = 180
    max_seconds: int = 600
    max_actions_per_day: int = 50
    night_start_hour: int = 23
    night_end_hour: int = 8


@dataclass
class Dac7Settings:
    """Umbrales de aviso del régimen fiscal europeo DAC7 (Directiva 2021/514)."""

    alert_amount_eur: float = 2000.0
    alert_transactions: int = 30


@dataclass
class Settings:
    env_path: Path = field(default_factory=lambda: PROJECT_ROOT / ".env")
    database_path: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "vintedbot.db")

    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8080
    dashboard_user: str = ""
    dashboard_password_hash: str = ""
    dashboard_force_https: bool = False

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    ai_provider: str = "auto"  # "auto" | "anthropic" | "mock"

    vinted_api_base_url: str = "https://api.vinted.com"
    vinted_api_client_id: str = ""
    vinted_api_client_secret: str = ""
    vinted_domain: str = "www.vinted.es"

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_starter_id: str = ""
    stripe_price_pro_id: str = ""
    stripe_price_scale_id: str = ""

    rate_limit: RateLimitSettings = field(default_factory=RateLimitSettings)
    dac7: Dac7Settings = field(default_factory=Dac7Settings)

    def resolve_ai_provider(self) -> str:
        """"auto" usa Anthropic si hay clave; si no, cae al proveedor simulado."""
        if self.ai_provider != "auto":
            return self.ai_provider
        return "anthropic" if self.anthropic_api_key else "mock"


def load_settings() -> Settings:
    """Construye `Settings` a partir de `os.environ` (llamar tras `load_dotenv()`)."""
    return Settings(
        database_path=Path(os.getenv("DATABASE_PATH", "data/vintedbot.db")),
        dashboard_host=os.getenv("DASHBOARD_HOST", "127.0.0.1"),
        dashboard_port=_env_int("DASHBOARD_PORT", 8080),
        dashboard_user=os.getenv("DASHBOARD_USER", ""),
        dashboard_password_hash=os.getenv("DASHBOARD_PASSWORD_HASH", ""),
        dashboard_force_https=_env_bool("DASHBOARD_FORCE_HTTPS", False),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5"),
        ai_provider=os.getenv("AI_PROVIDER", "auto"),
        vinted_api_base_url=os.getenv("VINTED_API_BASE_URL", "https://api.vinted.com"),
        vinted_api_client_id=os.getenv("VINTED_API_CLIENT_ID", ""),
        vinted_api_client_secret=os.getenv("VINTED_API_CLIENT_SECRET", ""),
        vinted_domain=os.getenv("VINTED_DOMAIN", "www.vinted.es"),
        stripe_secret_key=os.getenv("STRIPE_SECRET_KEY", ""),
        stripe_webhook_secret=os.getenv("STRIPE_WEBHOOK_SECRET", ""),
        stripe_price_starter_id=os.getenv("STRIPE_PRICE_STARTER_ID", ""),
        stripe_price_pro_id=os.getenv("STRIPE_PRICE_PRO_ID", ""),
        stripe_price_scale_id=os.getenv("STRIPE_PRICE_SCALE_ID", ""),
        rate_limit=RateLimitSettings(
            min_seconds=_env_int("RATE_LIMIT_MIN_SECONDS", 180),
            max_seconds=_env_int("RATE_LIMIT_MAX_SECONDS", 600),
            max_actions_per_day=_env_int("RATE_LIMIT_MAX_ACTIONS_PER_DAY", 50),
            night_start_hour=_env_int("RATE_LIMIT_NIGHT_START_HOUR", 23),
            night_end_hour=_env_int("RATE_LIMIT_NIGHT_END_HOUR", 8),
        ),
        dac7=Dac7Settings(
            alert_amount_eur=_env_float("DAC7_ALERT_AMOUNT_EUR", 2000.0),
            alert_transactions=_env_int("DAC7_ALERT_TRANSACTIONS", 30),
        ),
    )


settings = load_settings()
