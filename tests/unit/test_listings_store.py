from datetime import datetime, timedelta

from src.storage import accounts_store, listings_store
from src.storage.db import init_db
from src.vinted.models import Listing, VintedAccount


def _account(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    account = accounts_store.create_account(db_path, VintedAccount(label="X"))
    return db_path, account.id


def test_create_and_get_listing(tmp_path) -> None:
    db_path, account_id = _account(tmp_path)
    listing = listings_store.create_listing(
        db_path, Listing(account_id=account_id, title="Camiseta", price=15.0, min_price=10.0)
    )

    fetched = listings_store.get_listing(db_path, listing.id)
    assert fetched.title == "Camiseta"
    assert fetched.min_price == 10.0


def test_min_price_se_cifra_en_disco(tmp_path) -> None:
    db_path, account_id = _account(tmp_path)
    listing = listings_store.create_listing(
        db_path, Listing(account_id=account_id, price=15.0, min_price=10.0)
    )

    import sqlite3

    conn = sqlite3.connect(db_path)
    raw = conn.execute(
        "SELECT min_price_encrypted FROM listings WHERE id = ?", (listing.id,)
    ).fetchone()[0]
    conn.close()
    assert raw != "10.0"


def test_listing_sin_min_price(tmp_path) -> None:
    db_path, account_id = _account(tmp_path)
    listing = listings_store.create_listing(db_path, Listing(account_id=account_id, price=15.0))
    fetched = listings_store.get_listing(db_path, listing.id)
    assert fetched.min_price is None


def test_photo_paths_roundtrip(tmp_path) -> None:
    db_path, account_id = _account(tmp_path)
    listing = listings_store.create_listing(
        db_path, Listing(account_id=account_id, photo_paths=["a.jpg", "b.jpg"])
    )
    fetched = listings_store.get_listing(db_path, listing.id)
    assert fetched.photo_paths == ["a.jpg", "b.jpg"]


def test_list_listings_filtra_por_cuenta_y_estado(tmp_path) -> None:
    db_path, account_id = _account(tmp_path)
    other_account = accounts_store.create_account(db_path, VintedAccount(label="Y")).id

    listings_store.create_listing(db_path, Listing(account_id=account_id, status="draft"))
    listings_store.create_listing(db_path, Listing(account_id=account_id, status="published"))
    listings_store.create_listing(db_path, Listing(account_id=other_account, status="draft"))

    drafts_of_account = listings_store.list_listings(db_path, account_id=account_id, status="draft")
    assert len(drafts_of_account) == 1

    all_of_account = listings_store.list_listings(db_path, account_id=account_id)
    assert len(all_of_account) == 2


def test_mark_published(tmp_path) -> None:
    db_path, account_id = _account(tmp_path)
    listing = listings_store.create_listing(db_path, Listing(account_id=account_id, status="draft"))

    listings_store.mark_published(db_path, listing.id, vinted_item_id="item-42")

    fetched = listings_store.get_listing(db_path, listing.id)
    assert fetched.status == "published"
    assert fetched.vinted_item_id == "item-42"
    assert fetched.published_at is not None


def test_mark_sold(tmp_path) -> None:
    db_path, account_id = _account(tmp_path)
    listing = listings_store.create_listing(db_path, Listing(account_id=account_id))

    listings_store.mark_sold(db_path, listing.id)

    assert listings_store.get_listing(db_path, listing.id).status == "sold"


def test_count_listings_since(tmp_path) -> None:
    db_path, account_id = _account(tmp_path)
    listings_store.create_listing(db_path, Listing(account_id=account_id))
    listings_store.create_listing(db_path, Listing(account_id=account_id))

    count = listings_store.count_listings_since(db_path, account_id, datetime.now() - timedelta(days=1))
    assert count == 2

    count_future = listings_store.count_listings_since(
        db_path, account_id, datetime.now() + timedelta(days=1)
    )
    assert count_future == 0
