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
    # Whitelisted attendees keep their real embedded identity wherever the
    # doc itself carries it (nested entries without contact fields can't be
    # whitelist-checked and stay masked — cosmetic only).
    if _ids.is_whitelisted(
        {
            "mobile": doc.get("player_mobile"),
            "email": doc.get("player_email"),
        }
    ):
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


_PII_TEXT = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|\+?\d[\d .\-()]{5,}\d"
)


def _scrub_text(value):
    """Strip emails/phone-looking runs from free text, keep the message."""
    return _PII_TEXT.sub("[masked]", str(value))


def mask_booking(doc):
    # notes is free text and does carry real phones/emails in prod —
    # scrub matches rather than clear so booking detail still demos.
    if doc.get("notes"):
        doc["notes"] = _scrub_text(doc["notes"])
    return _mask_person_fields(doc)


def mask_check_in(doc):
    return _mask_person_fields(doc)


def mask_player_block(doc):
    pid = doc.get("player_id")
    if pid:
        if doc.get("player_mobile"):
            doc["player_mobile"] = _ids.masked_mobile(pid)
        if doc.get("player_name"):
            doc["player_name"] = _ids.masked_name(pid)
    return doc


def _mask_person_tree(node):
    """Recursively mask person fields on any dict that carries a player_id —
    covers nested rosters like matches.slots.teamN[]."""
    if isinstance(node, dict):
        pid = node.get("player_id")
        for field in _NAME_FIELDS:
            if field in node and node.get(field):
                node[field] = _ids.masked_name(pid or node.get("_id") or "anon")
        for field in _MOBILE_FIELDS:
            if field in node and node.get(field):
                node[field] = _ids.masked_mobile(pid or node.get("_id") or "anon")
        for field in _EMAIL_FIELDS:
            if field in node and node.get(field):
                node[field] = _ids.masked_email(pid or node.get("_id") or "anon")
        for value in node.values():
            _mask_person_tree(value)
    elif isinstance(node, list):
        for item in node:
            _mask_person_tree(item)


def mask_match(doc):
    _mask_person_tree(doc)
    return doc


def mask_notification_settings(doc):
    """channels.*.recipients[] hold real owner/staff phones+emails — mask
    each recipient deterministically. Post-fixups separately force all
    `enabled` flags off."""
    oid = doc.get("_id", "ns")
    channels = doc.get("channels")
    if not isinstance(channels, dict):
        return doc
    counter = [0]

    def _mask_recipients(recipients):
        if not isinstance(recipients, list):
            return
        for rec in recipients:
            counter[0] += 1
            if not isinstance(rec, dict):
                continue
            key = f"{oid}:r{counter[0]}"
            if rec.get("phone_e164"):
                rec["phone_e164"] = _ids.masked_mobile(key)
            if rec.get("email"):
                rec["email"] = _ids.masked_email(key, "staff")
            if rec.get("name"):
                rec["name"] = _ids.masked_name(key, "Staff")

    def _walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "recipients":
                    _mask_recipients(value)
                else:
                    _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(channels)
    return doc


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


def mask_promotion(doc):
    for field in ("createdBy", "approvedBy", "rejectedBy"):
        if field in doc and doc[field]:
            doc[field] = "demo-admin"
    return doc


def mask_terms_acceptance(doc):
    for field in ("device_id", "ip_address"):
        if field in doc:
            doc[field] = None
    return doc


def mask_payment(doc):
    for key in list(doc.keys()):
        if key == "_id":
            continue
        if _SCRUB_KEY.search(key):
            doc[key] = _scrub(doc[key])
    # Amounts, currency, status, method, dates all survive — revenue
    # numbers must look real in the demo.
    return _mask_person_fields(doc)
