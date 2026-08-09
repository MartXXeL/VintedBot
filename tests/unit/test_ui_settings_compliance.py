from datetime import datetime

from fastapi.testclient import TestClient

from src.core.security import hash_password
from src.core.settings import Settings
from src.storage import accounts_store, sales_store
from src.ui.app import create_app
from src.vinted.models import Sale, VintedAccount

TEST_PASSWORD = "una-contraseña-de-prueba"


def _make_client(tmp_path):
    settings = Settings(
        database_path=tmp_path / "test.db",
        env_path=tmp_path / ".env",
        dashboard_password_hash=hash_password(TEST_PASSWORD),
    )
    app = create_app(settings, start_worker=False)
    client = TestClient(app)
    client.post("/login", data={"password": TEST_PASSWORD})
    return client, settings


# --------------------------------------------------------------------------- #
#  Ajustes
# --------------------------------------------------------------------------- #


def test_ver_ajustes_no_expone_claves_ya_guardadas(tmp_path) -> None:
    client, settings = _make_client(tmp_path)
    settings.anthropic_api_key = "sk-ant-secreto-de-verdad"

    response = client.get("/settings")

    assert response.status_code == 200
    assert "sk-ant-secreto-de-verdad" not in response.text
    assert "ya configurada" in response.text


def test_guardar_ajustes_actualiza_el_env_y_el_settings_en_memoria(tmp_path) -> None:
    client, settings = _make_client(tmp_path)

    response = client.post(
        "/settings",
        data={
            "anthropic_model": "claude-otro-modelo",
            "ai_provider": "mock",
            "vinted_domain": "www.vinted.fr",
            "rate_limit_min_seconds": "200",
            "rate_limit_max_seconds": "500",
            "rate_limit_max_actions_per_day": "40",
            "rate_limit_night_start_hour": "22",
            "rate_limit_night_end_hour": "7",
            "dac7_alert_amount_eur": "2500",
            "dac7_alert_transactions": "25",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "ok=" in response.headers["location"]
    assert settings.vinted_domain == "www.vinted.fr"
    assert settings.rate_limit.min_seconds == 200
    assert settings.dac7.alert_transactions == 25
    assert "VINTED_DOMAIN=www.vinted.fr" in settings.env_path.read_text(encoding="utf-8")


def test_guardar_clave_en_blanco_no_borra_la_existente(tmp_path) -> None:
    client, settings = _make_client(tmp_path)
    settings.anthropic_api_key = "sk-ant-original"

    client.post(
        "/settings",
        data={
            "anthropic_model": "claude-sonnet-5",
            "ai_provider": "auto",
            "vinted_domain": "www.vinted.es",
            "anthropic_api_key": "",  # en blanco: no tocar
            "rate_limit_min_seconds": "180",
            "rate_limit_max_seconds": "600",
            "rate_limit_max_actions_per_day": "50",
            "rate_limit_night_start_hour": "23",
            "rate_limit_night_end_hour": "8",
            "dac7_alert_amount_eur": "2000",
            "dac7_alert_transactions": "30",
        },
    )

    assert settings.anthropic_api_key == "sk-ant-original"


def test_guardar_ajustes_de_stripe(tmp_path) -> None:
    client, settings = _make_client(tmp_path)

    client.post(
        "/settings",
        data={
            "anthropic_model": "claude-sonnet-5",
            "ai_provider": "auto",
            "vinted_domain": "www.vinted.es",
            "rate_limit_min_seconds": "180",
            "rate_limit_max_seconds": "600",
            "rate_limit_max_actions_per_day": "50",
            "rate_limit_night_start_hour": "23",
            "rate_limit_night_end_hour": "8",
            "dac7_alert_amount_eur": "2000",
            "dac7_alert_transactions": "30",
            "stripe_secret_key": "sk_test_nueva",
            "stripe_webhook_secret": "whsec_nuevo",
            "stripe_price_starter_id": "price_starter",
            "stripe_price_pro_id": "price_pro",
            "stripe_price_scale_id": "price_scale",
        },
    )

    assert settings.stripe_secret_key == "sk_test_nueva"
    assert settings.stripe_webhook_secret == "whsec_nuevo"
    assert settings.stripe_price_starter_id == "price_starter"
    env_content = settings.env_path.read_text(encoding="utf-8")
    assert "STRIPE_SECRET_KEY=sk_test_nueva" in env_content
    assert "STRIPE_PRICE_PRO_ID=price_pro" in env_content


def test_ajustes_no_muestra_la_clave_de_stripe_ya_guardada(tmp_path) -> None:
    client, settings = _make_client(tmp_path)
    settings.stripe_secret_key = "sk_test_secreta_de_verdad"

    response = client.get("/settings")

    assert "sk_test_secreta_de_verdad" not in response.text
    assert "ya configurada" in response.text


def test_cadencia_minima_mayor_que_maxima_da_error(tmp_path) -> None:
    client, _settings = _make_client(tmp_path)

    response = client.post(
        "/settings",
        data={
            "anthropic_model": "claude-sonnet-5",
            "ai_provider": "auto",
            "vinted_domain": "www.vinted.es",
            "rate_limit_min_seconds": "600",
            "rate_limit_max_seconds": "180",
            "rate_limit_max_actions_per_day": "50",
            "rate_limit_night_start_hour": "23",
            "rate_limit_night_end_hour": "8",
            "dac7_alert_amount_eur": "2000",
            "dac7_alert_transactions": "30",
        },
        follow_redirects=False,
    )

    assert "error=" in response.headers["location"]


# --------------------------------------------------------------------------- #
#  DAC7
# --------------------------------------------------------------------------- #


def test_compliance_sin_cuentas(tmp_path) -> None:
    client, _settings = _make_client(tmp_path)
    response = client.get("/compliance")
    assert response.status_code == 200
    assert "Todavía no hay cuentas" in response.text


def test_compliance_muestra_el_estado_por_cuenta(tmp_path) -> None:
    client, settings = _make_client(tmp_path)
    account = accounts_store.create_account(str(settings.database_path), VintedAccount(label="Mi tienda"))
    sales_store.record_sale(str(settings.database_path), Sale(account_id=account.id, sale_amount=2500.0))

    response = client.get("/compliance")

    assert "Mi tienda" in response.text
    assert "Reporte obligatorio" in response.text


def test_compliance_filtra_por_anio(tmp_path) -> None:
    client, settings = _make_client(tmp_path)
    account = accounts_store.create_account(str(settings.database_path), VintedAccount(label="X"))
    # Una venta del año pasado no debe contar en el resumen de este año.
    import sqlite3

    conn = sqlite3.connect(settings.database_path)
    conn.execute(
        "INSERT INTO sales (account_id, sale_amount, sold_at) VALUES (?, ?, ?)",
        (account.id, 5000.0, f"{datetime.now().year - 1}-01-01 00:00:00"),
    )
    conn.commit()
    conn.close()

    response = client.get("/compliance")

    assert "Al día" in response.text
