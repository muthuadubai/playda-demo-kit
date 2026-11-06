"""Venue masking — replace identity + contact details, keep everything
functional: address.location (geo index/maps), address.country (timezone
fallback), timezone, operating_hours, courts references all survive."""

import re

from demo_kit.maskers import _ids

_CONTACT_FIELDS = ("contact_person", "website", "instagram", "whatsapp")


def _acronym(name):
    """'Le Padel Club' → 'LPC'. Whitespace tokens starting with a letter;
    needs ≥2 tokens or the caller falls back to a generic name."""
    tokens = [
        t for t in re.split(r"\s+", (name or "").strip())
        if t and t[0].isalpha()
    ]
    if len(tokens) >= 2:
        return "".join(t[0] for t in tokens).upper()
    return None


def mask_venue(doc, taken_names=None):
    oid = doc["_id"]
    acronym = _acronym(doc.get("name"))
    if acronym:
        # '{initials} Club' — recognisable to the demo team, meaningless to
        # attendees. taken_names tracks names assigned earlier in the same
        # run (venues copy in _id order → suffixes are deterministic across
        # refreshes and identical in the ops/crm pairs).
        name = f"{acronym} Club"
        if taken_names is not None:
            n = 2
            while name in taken_names:
                name = f"{acronym} Club {n}"
                n += 1
            taken_names.add(name)
        doc["name"] = name
    else:
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
