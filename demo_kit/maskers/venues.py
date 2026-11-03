"""Venue masking — replace identity + contact details, keep everything
functional: address.location (geo index/maps), address.country (timezone
fallback), timezone, operating_hours, courts references all survive."""

from demo_kit.maskers import _ids

_CONTACT_FIELDS = ("contact_person", "website", "instagram", "whatsapp")


def mask_venue(doc):
    oid = doc["_id"]
    doc["name"] = f"Demo Arena {_ids.seq(oid, 1000)}"
    if doc.get("phone"):
        doc["phone"] = _ids.masked_mobile(oid)
    if doc.get("email"):
        doc["email"] = _ids.masked_email(oid, "venue")
    address = doc.get("address")
    if isinstance(address, dict) and address.get("street"):
        address["street"] = f"Demo Street {_ids.seq(oid, 100)}"
    for field in _CONTACT_FIELDS:
        if field in doc:
            doc[field] = None
    return doc
