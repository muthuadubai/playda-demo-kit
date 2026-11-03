"""players + users masking. Whitelisted docs keep real contact data (so demo
attendees can log in) but still lose device/session artefacts so nothing can
reach their real device."""

from demo_kit.maskers import _ids

# Anything that could route a push/OTP/session to a real device or leak a
# real photo. Cleared on whitelisted docs too.
_DEVICE_FIELDS = (
    "mpin",
    "device_id",
    "last_login_device",
    "fcm_token",
    "expo_push_token",
    "push_token",
    "device_token",
    "avatar",
    "profile_picture",
    "photo_url",
)


def _strip_device_fields(doc):
    for field in _DEVICE_FIELDS:
        if field in doc:
            doc[field] = None


def mask_player(doc):
    if _ids.is_whitelisted(doc):
        _strip_device_fields(doc)
        return doc
    oid = doc["_id"]
    doc["name"] = _ids.masked_name(oid)
    doc["profile_name"] = _ids.masked_name(oid)
    doc["mobile"] = _ids.masked_mobile(oid)
    if "phone" in doc and doc.get("phone"):
        doc["phone"] = _ids.masked_mobile(oid)
    if "email" in doc and doc.get("email"):
        doc["email"] = _ids.masked_email(oid)
    _strip_device_fields(doc)
    return doc


def mask_user(doc):
    if _ids.is_whitelisted(doc):
        _strip_device_fields(doc)
        return doc
    oid = doc["_id"]
    doc["name"] = _ids.masked_name(oid, "Staff")
    doc["email"] = _ids.masked_email(oid, "staff")
    if "mobile" in doc and doc.get("mobile"):
        doc["mobile"] = _ids.masked_mobile(oid)
    if "address" in doc:
        doc["address"] = None
    _strip_device_fields(doc)
    return doc
