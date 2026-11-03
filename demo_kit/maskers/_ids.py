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


# Culturally-coherent name pools — the bucket is chosen first, then
# first+last inside it, so results never mix ethnicities (no "Ahmed Wilson").
# Mix mirrors the UAE player demographic.
_NAME_POOLS = (
    (  # Arab / Emirati
        ("Ahmed", "Fatima", "Khalid", "Mariam", "Omar", "Aisha", "Rashid",
         "Noor", "Saeed", "Hessa", "Sultan", "Latifa", "Hamdan", "Shamsa"),
        ("Al Mansouri", "Al Zaabi", "Al Falasi", "Al Nuaimi", "Al Shamsi",
         "Al Qassimi", "Al Suwaidi", "Al Mazrouei", "Al Ketbi", "Al Hammadi"),
    ),
    (  # South Asian
        ("Arjun", "Priya", "Ravi", "Sneha", "Vikram", "Ananya", "Rahul",
         "Divya", "Kiran", "Meera", "Aditya", "Pooja", "Sanjay", "Lakshmi"),
        ("Nair", "Sharma", "Patel", "Kumar", "Menon", "Reddy", "Iyer",
         "Naidu", "Pillai", "Verma", "Gupta", "Desai"),
    ),
    (  # Filipino
        ("Jose", "Maria", "Angel", "Paolo", "Grace", "Miguel", "Rosa",
         "Carlo", "Liza", "Marco", "Jenny", "Ramon"),
        ("Santos", "Reyes", "Cruz", "Garcia", "Mendoza", "Torres", "Ramos",
         "Aquino", "Navarro", "Salazar", "Mercado", "Aguilar"),
    ),
    (  # Western expat
        ("James", "Sarah", "Emma", "Daniel", "Olivia", "Tom", "Laura",
         "Mark", "Sophie", "Jack", "Chloe", "Ryan"),
        ("Smith", "Brown", "Wilson", "Taylor", "Miller", "Davies", "Evans",
         "Thomas", "Johnson", "Walker", "Wright", "Clarke"),
    ),
)


def masked_name(oid, prefix="Player"):
    # `prefix` retained for call-site compatibility; all pools now produce
    # real-looking person names (staff names look better that way too).
    firsts, lasts = _NAME_POOLS[seq(f"{oid}:pool", len(_NAME_POOLS))]
    return (
        f"{firsts[seq(f'{oid}:fn', len(firsts))]} "
        f"{lasts[seq(f'{oid}:ln', len(lasts))]}"
    )


def is_whitelisted(doc):
    mobile = (doc.get("mobile") or doc.get("phone") or "").strip()
    email = (doc.get("email") or "").strip().lower()
    return bool(
        (mobile and mobile in config.DEMO_WHITELIST_MOBILES)
        or (email and email in config.DEMO_WHITELIST_EMAILS)
    )
