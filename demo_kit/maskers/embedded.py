"""Embedded-PII masking — bookings/check_ins denormalize player contact
details, payments carry gateway references. Embedded identities are masked
from the PLAYER's _id (not the row's) so they stay consistent with the
masked players collection."""

import re

from demo_kit.maskers import _ids

_NAME_FIELDS = (
    "player_name",
    "guest_name",
    "customer_name",
    "payer_name",
)
_MOBILE_FIELDS = (
    "player_mobile",
    "guest_mobile",
    "customer_mobile",
    "payer_mobile",
    "player_phone",
)
_EMAIL_FIELDS = ("player_email", "guest_email", "customer_email", "payer_email")


def _mask_person_fields(doc):
    """Re-mask any embedded contact field from the owning player_id."""
    pid = doc.get("player_id") or doc.get("payer_ref")
    if not pid:
        return doc
    for field in _NAME_FIELDS:
        if field in doc and doc.get(field):
            doc[field] = _ids.masked_name(pid)
    for field in _MOBILE_FIELDS:
        if field in doc and doc.get(field):
            doc[field] = _ids.masked_mobile(pid)
    for field in _EMAIL_FIELDS:
        if field in doc and doc.get(field):
            doc[field] = _ids.masked_email(pid)
    return doc


def mask_booking(doc):
    return _mask_person_fields(doc)


def mask_check_in(doc):
    return _mask_person_fields(doc)


# Gateway/bank artefacts — keys are matched loosely so new gateway fields
# fail masked rather than fail open.
_SCRUB_KEY = re.compile(
    r"transaction|reference|gateway|stripe|customer|receipt|card|iban|"
    r"account|auth_code|charge|payment_intent|fingerprint",
    re.IGNORECASE,
)


def _scrub(value):
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    return "[masked]"


def mask_payment(doc):
    for key in list(doc.keys()):
        if key == "_id":
            continue
        if _SCRUB_KEY.search(key):
            doc[key] = _scrub(doc[key])
    # Amounts, currency, status, method, dates all survive — revenue
    # numbers must look real in the demo.
    return _mask_person_fields(doc)
