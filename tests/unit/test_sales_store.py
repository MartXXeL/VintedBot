from src.storage import accounts_store, sales_store
from src.storage.db import init_db
from src.vinted.models import Sale, VintedAccount


def _account(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    account_id = accounts_store.create_account(db_path, VintedAccount(label="X")).id
    return db_path, account_id


def test_record_and_list_sales(tmp_path) -> None:
    db_path, account_id = _account(tmp_path)
    sales_store.record_sale(db_path, Sale(account_id=account_id, sale_amount=25.0))
    sales_store.record_sale(db_path, Sale(account_id=account_id, sale_amount=10.0))

    sales = sales_store.list_sales(db_path, account_id=account_id)
    assert len(sales) == 2
    assert {s.sale_amount for s in sales} == {25.0, 10.0}


def test_list_sales_filtra_por_cuenta(tmp_path) -> None:
    db_path, account_id = _account(tmp_path)
    other_account = accounts_store.create_account(db_path, VintedAccount(label="Y")).id

    sales_store.record_sale(db_path, Sale(account_id=account_id, sale_amount=25.0))
    sales_store.record_sale(db_path, Sale(account_id=other_account, sale_amount=5.0))

    assert len(sales_store.list_sales(db_path, account_id=account_id)) == 1


def test_list_sales_sin_filtro_devuelve_todas(tmp_path) -> None:
    db_path, account_id = _account(tmp_path)
    other_account = accounts_store.create_account(db_path, VintedAccount(label="Y")).id
    sales_store.record_sale(db_path, Sale(account_id=account_id, sale_amount=25.0))
    sales_store.record_sale(db_path, Sale(account_id=other_account, sale_amount=5.0))

    assert len(sales_store.list_sales(db_path)) == 2
