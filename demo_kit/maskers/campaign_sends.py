"""campaign_sends masking — `to_address` holds the real recipient email or
mobile, and provider `error` strings can echo it back."""

import hashlib
import re

from demo_kit import config
from demo_kit.maskers import _ids

_DIGIT_RUN = re.compile(r"\+?\d[\d .\-()]{5,}\d")


def mask_send(doc):
    pid = doc.get("player_id")
    to_address = doc.get("to_address")
    if pid and to_address:
        if "@" in str(to_address):
            doc["to_address"] = _ids.masked_email(pid)
        else:
            doc["to_address"] = _ids.masked_mobile(pid)
    if doc.get("error"):
        doc["error"] = _DIGIT_RUN.sub("[masked]", str(doc["error"]))
    # Real provider IDs resolve real messages in the Twilio console — and
    # the demo runs prod credentials. Fake-SID shape keeps realism without
    # a live lookup path back to the real send.
    if doc.get("provider_message_id"):
        doc["provider_message_id"] = (
            "SM" + hashlib.sha256(
                f"{config.DEMO_SALT}:sid:{doc['_id']}".encode()
            ).hexdigest()[:32]
        )
    # Resolved merge-tag values may carry the real name/number.
    variables = doc.get("variables")
    if pid and isinstance(variables, dict):
        for key, value in variables.items():
            if isinstance(value, str) and (
                "name" in key.lower() or "mobile" in key.lower()
                or "phone" in key.lower() or "email" in key.lower()
            ):
                variables[key] = (
                    _ids.masked_name(pid)
                    if "name" in key.lower()
                    else _ids.masked_mobile(pid)
                )
    return doc
