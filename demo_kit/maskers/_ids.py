"""Deterministic masking primitives.

Every masked value is a pure function of (entity _id, DEMO_SALT) — no state,
no maps. The ops copy and the crm copy mask the same player identically
even when run independently, which is what keeps identities consistent
across playda_demo and playda_crm_demo.
"""

import hashlib

from demo_kit import config


def seq(oid, mod):
    """Stable pseudo-random index for an entity id under the current salt."""
    digest = hashlib.sha256(f"{config.DEMO_SALT}:{oid}".encode()).hexdigest()
    return int(digest[:12], 16) % mod


def masked_mobile(oid):
    """+1 555-XXX-XXXX — NANP area code 555 is unassigned → unroutable
    even if a send path were accidentally enabled."""
    return f"+1555{seq(oid, 10_000_000):07d}"


def masked_email(oid, prefix="player"):
    # RFC 2606 `.invalid` TLD — undeliverable by construction.
    return f"{prefix}{seq(oid, 1_000_000)}@playda-demo.invalid"


def masked_name(oid, prefix="Player"):
    return f"{prefix} {seq(oid, 100_000)}"


def is_whitelisted(doc):
    mobile = (doc.get("mobile") or doc.get("phone") or "").strip()
    email = (doc.get("email") or "").strip().lower()
    return bool(
        (mobile and mobile in config.DEMO_WHITELIST_MOBILES)
        or (email and email in config.DEMO_WHITELIST_EMAILS)
    )
