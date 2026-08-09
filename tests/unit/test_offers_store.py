from src.storage import accounts_store, listings_store, offers_store
from src.storage.db import init_db
from src.vinted.models import Listing, Offer, VintedAccount


def _listing(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    account_id = accounts_store.create_account(db_path, VintedAccount(label="X")).id
    listing_id = listings_store.create_listing(db_path, Listing(account_id=account_id)).id
    return db_path, account_id, listing_id


def test_create_offer_queda_pendiente(tmp_path) -> None:
    db_path, account_id, listing_id = _listing(tmp_path)
    offer = offers_store.create_offer(
        db_path, Offer(listing_id=listing_id, account_id=account_id, offer_amount=12.0)
    )
    assert offer.status == "pending"
    assert offers_store.get_offer(db_path, offer.id).offer_amount == 12.0


def test_set_offer_decision_guarda_todo(tmp_path) -> None:
    db_path, account_id, listing_id = _listing(tmp_path)
    offer = offers_store.create_offer(
        db_path, Offer(listing_id=listing_id, account_id=account_id, offer_amount=12.0)
    )

    offers_store.set_offer_decision(db_path, offer.id, "counter", 15.0, "¿Qué tal 15€?")

    fetched = offers_store.get_offer(db_path, offer.id)
    assert fetched.decision == "counter"
    assert fetched.counter_amount == 15.0
    assert fetched.reply_text == "¿Qué tal 15€?"
    assert fetched.status == "pending"  # sigue pendiente de aprobación humana


def test_mark_sent(tmp_path) -> None:
    db_path, account_id, listing_id = _listing(tmp_path)
    offer = offers_store.create_offer(
        db_path, Offer(listing_id=listing_id, account_id=account_id, offer_amount=12.0)
    )

    offers_store.mark_sent(db_path, offer.id)

    fetched = offers_store.get_offer(db_path, offer.id)
    assert fetched.status == "sent"
    assert fetched.answered_at is not None


def test_discard_offer(tmp_path) -> None:
    db_path, account_id, listing_id = _listing(tmp_path)
    offer = offers_store.create_offer(
        db_path, Offer(listing_id=listing_id, account_id=account_id, offer_amount=12.0)
    )

    offers_store.discard_offer(db_path, offer.id)

    assert offers_store.get_offer(db_path, offer.id).status == "discarded"


def test_external_offer_id_evita_duplicados(tmp_path) -> None:
    db_path, account_id, listing_id = _listing(tmp_path)
    offers_store.create_offer(
        db_path,
        Offer(
            listing_id=listing_id,
            account_id=account_id,
            offer_amount=12.0,
            external_conversation_id="conv-1",
            external_offer_id="ext-offer-1",
        ),
    )

    found = offers_store.get_offer_by_external_id(db_path, "ext-offer-1")
    assert found is not None
    assert found.offer_amount == 12.0
    assert offers_store.get_offer_by_external_id(db_path, "no-existe") is None


def test_list_offers_filtra_por_estado(tmp_path) -> None:
    db_path, account_id, listing_id = _listing(tmp_path)
    a = offers_store.create_offer(
        db_path, Offer(listing_id=listing_id, account_id=account_id, offer_amount=10.0)
    )
    offers_store.create_offer(
        db_path, Offer(listing_id=listing_id, account_id=account_id, offer_amount=20.0)
    )
    offers_store.discard_offer(db_path, a.id)

    pending = offers_store.list_offers(db_path, account_id=account_id, status="pending")
    assert len(pending) == 1
    assert pending[0].offer_amount == 20.0
