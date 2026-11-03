"""Masker registry — copier calls apply() per document before insert.
Collections not listed copy through unmasked (aggregate/reference data
contains no PII by construction)."""

from demo_kit.maskers import campaign_sends, embedded, people, venues

_BY_COLLECTION = {
    "players": people.mask_player,
    "users": people.mask_user,
    "venue": venues.mask_venue,
    "bookings": embedded.mask_booking,
    "check_ins": embedded.mask_check_in,
    "payments": embedded.mask_payment,
    "campaign_sends": campaign_sends.mask_send,
}


def apply(collection_name, doc):
    masker = _BY_COLLECTION.get(collection_name)
    return masker(doc) if masker else doc
