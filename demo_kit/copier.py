"""Point-in-time demo copier.

Two profiles:
  ops_copy — prod `playda` DB        → `playda_demo`      (admin-fe demo)
  crm_copy — prod `playda_crm` DB    → `playda_crm_demo`  (paired CRM demo)

Copy shape is driven by SPECS — an allowlist, not "everything except _".
Unlisted collections are skipped and logged: unknown collections may carry
unmasked PII, so missing data fails closed.

Scope resolution is two-pass for venue-scoped copies:
  pass 1 — bookings + check-ins at the chosen venues → booking_ids (B),
           player_ids (P), and staff user_ids (U) from venue_access.
  pass 2 — every collection filters on B / P / U / venue ids per its spec.

Masking is applied during copy (stateless f(_id, DEMO_SALT)) so masked
identities agree across both profiles.
"""

import datetime
import logging
from dataclasses import dataclass, field as dc_field
from typing import Callable, Optional

from bson import ObjectId

from demo_kit import images, maskers

logger = logging.getLogger("demo_kit.copier")

BATCH_SIZE = 500


def _oids(values):
    out = []
    for v in values or []:
        if isinstance(v, ObjectId):
            out.append(v)
        elif ObjectId.is_valid(str(v)):
            out.append(ObjectId(str(v)))
        else:
            out.append(v)  # keep raw — $in just won't match _ids
    return out


@dataclass
class Scope:
    """Entity sets resolved in pass 1. `full` means no venue filter — every
    spec's query degenerates to {} (except explicit skips)."""

    full: bool = True
    venue_oids: list = dc_field(default_factory=list)
    venue_strs: list = dc_field(default_factory=list)
    booking_ids: set = dc_field(default_factory=set)
    player_ids: set = dc_field(default_factory=set)
    user_ids: set = dc_field(default_factory=set)
    queries: dict = dc_field(default_factory=dict)  # per-collection raw queries


def _any_venue(scope):
    return list(scope.venue_oids) + list(scope.venue_strs)


def _query(spec, scope):
    if scope.full:
        return {} if spec.kind != "skip" else None
    kind = spec.kind
    if kind == "global":
        return {}
    if kind == "skip":
        return None
    if kind == "venue":
        return {spec.field: {"$in": _any_venue(scope)}}
    if kind == "tenant":  # CRM tenant_id is a string
        return {"tenant_id": {"$in": scope.venue_strs}}
    if kind == "booking":
        return {spec.field: {"$in": list(scope.booking_ids)}}
    if kind == "player":
        return {spec.field: {"$in": list(scope.player_ids)}}
    if kind == "user":
        return {spec.field: {"$in": list(scope.user_ids)}}
    if kind == "venue_or_player":
        return {
            "$or": [
                {"venue_id": {"$in": _any_venue(scope)}},
                {"player_id": {"$in": list(scope.player_ids)}},
            ]
        }
    if kind == "venue_or_global":
        return {
            "$or": [
                {spec.field: {"$in": _any_venue(scope)}},
                {"isGlobal": True},
            ]
        }
    if kind == "raw":
        return scope.queries.get(spec.name)
    raise ValueError(f"Unknown spec kind {kind!r} for {spec.name}")


@dataclass
class Spec:
    name: str
    kind: str = "global"          # global|venue|tenant|booking|player|user|
                                  # venue_or_player|raw|skip
    field: str = "venue_id"
    mask: bool = True
    post: Optional[Callable] = None  # doc, scope -> doc (after masking)


def _rewire_crm_player(doc, scope):
    """Players active at non-demo venues shouldn't list them."""
    kept = [v for v in (doc.get("venue_ids") or []) if v in scope.venue_strs]
    doc["venue_ids"] = kept
    if doc.get("tenant_id") not in scope.venue_strs:
        doc["tenant_id"] = kept[0] if kept else None
    return doc


# ---------------------------------------------------------------------------
# ops profile: prod `playda` → `playda_demo`
# ---------------------------------------------------------------------------
OPS_SPECS = [
    # Global reference data — no PII, needed for the app to function.
    Spec("country"),
    Spec("terms_versions"),
    Spec("insights_rulesets"),
    Spec("platform_refund_policy"),
    # Venue-rooted collections.
    Spec("venue", kind="venue", field="_id"),
    Spec("court", kind="venue"),
    Spec("court_blocks", kind="venue"),
    Spec("pricing_template", kind="venue"),
    Spec("discount_template", kind="venue"),
    Spec("matches", kind="venue_or_player"),
    # promotion.venueId is camelCase; isGlobal promos belong to every venue.
    Spec("promotion", kind="venue_or_global", field="venueId"),
    Spec("promo_codes", kind="venue"),
    Spec("promo_redemptions", kind="venue"),
    Spec("venue_notification_settings", kind="venue"),
    Spec("venue_financial_settings", kind="venue"),
    Spec("venue_peak_hours", kind="venue"),
    Spec("venue_onboarding_requests", kind="venue"),
    # Insights derived collections — aggregates/ObjectIds only, no PII.
    Spec("player_day_facts", kind="venue"),
    Spec("venue_daily_metrics", kind="venue"),
    Spec("player_venue_stats", kind="venue"),
    Spec("customer_rfm_snapshots", kind="venue"),
    # Scoped via pass-1 entity sets.
    Spec("bookings", kind="raw"),
    Spec("check_ins", kind="raw"),
    Spec("payments", kind="booking", field="booking_id"),
    Spec("cancel_booking_tokens", kind="booking", field="booking_id"),
    Spec("players", kind="player", field="_id"),
    Spec("consent_events", kind="player"),
    Spec("terms_acceptances", kind="player", field="player_id"),
    Spec("player_blocks", kind="venue_or_player"),
    Spec("player_due_ledger", kind="venue_or_player"),
    Spec("player_due_balances", kind="venue_or_player"),
    Spec("late_cancellation_events", kind="venue_or_player"),
    Spec("venue_access", kind="venue"),
    Spec("users", kind="user", field="_id"),
    # notifications skipped: free-text bodies can embed real names.
    # ai_insights_* skipped: cache may hold generated text with names.
    Spec("notifications", kind="skip"),
    Spec("ai_insights_cache", kind="skip"),
    Spec("ai_insights_usage", kind="skip"),
]


def resolve_ops_scope(source_db, venue_ids, lookback_days=None):
    if not venue_ids:
        return Scope(full=True)
    venue_oids = _oids(venue_ids)
    scope = Scope(
        full=False,
        venue_oids=venue_oids,
        venue_strs=[str(v) for v in venue_oids],
    )
    any_v = list(venue_oids) + scope.venue_strs

    booking_q = {"venue_id": {"$in": any_v}}
    checkin_q = {"venue_id": {"$in": any_v}}
    if lookback_days:
        cutoff = (
            datetime.datetime.now(datetime.timezone.utc).date()
            - datetime.timedelta(days=int(lookback_days))
        ).isoformat()
        booking_q["booking_date"] = {"$gte": cutoff}
        checkin_q["booking_date"] = {"$gte": cutoff}
    scope.queries["bookings"] = booking_q
    scope.queries["check_ins"] = checkin_q

    for b in source_db["bookings"].find(booking_q, {"player_id": 1}):
        scope.booking_ids.add(b["_id"])
        if b.get("player_id"):
            scope.player_ids.add(b["player_id"])
    for c in source_db["check_ins"].find(checkin_q, {"player_id": 1}):
        if c.get("player_id"):
            scope.player_ids.add(c["player_id"])
    scope.player_ids = set(_oids(scope.player_ids))

    # Staff on the scoped venues → masked user docs (realistic staff list).
    for va in source_db["venue_access"].find(
        {"venue_id": {"$in": any_v}}, {"user_id": 1}
    ):
        if va.get("user_id"):
            scope.user_ids.add(va["user_id"])
    scope.user_ids = set(_oids(scope.user_ids))

    logger.info(
        "Ops scope: %d venues → %d bookings, %d players, %d staff users",
        len(venue_oids),
        len(scope.booking_ids),
        len(scope.player_ids),
        len(scope.user_ids),
    )
    return scope


# ---------------------------------------------------------------------------
# crm profile: prod `playda_crm` → `playda_crm_demo`
# ---------------------------------------------------------------------------
CRM_SPECS = [
    # Global platform config — no PII.
    Spec("whatsapp_templates"),
    Spec("platform_settings"),
    # Raw synced docs — tenant-keyed by the sync transform.
    Spec("venue", kind="venue", field="_id"),
    Spec("bookings", kind="tenant"),
    Spec("check_ins", kind="tenant"),
    Spec("payments", kind="tenant"),
    Spec(
        "players",
        kind="raw",
        post=_rewire_crm_player,
    ),
    Spec("promo_codes", kind="venue"),
    Spec("promo_redemptions", kind="player", field="player_id"),
    Spec("consent_events", kind="player", field="player_id"),
    # Derived / config — tenant-keyed.
    Spec("bookings_summary", kind="tenant"),
    Spec("rfm_scores", kind="tenant"),
    Spec("rfm_configs", kind="tenant"),
    Spec("segments", kind="tenant"),
    Spec("segment_members", kind="tenant"),
    Spec("segment_membership_events", kind="tenant"),
    Spec("campaigns", kind="tenant"),
    Spec("campaign_sends", kind="tenant"),
    Spec("tenant_entitlements", kind="tenant"),
    # Player-scoped projections.
    Spec("player_consent", kind="player", field="player_id"),
    Spec("channel_unreachability", kind="player", field="player_id"),
    Spec("player_blocks", kind="venue_or_player"),
    Spec("inbound_autoreplies", kind="player", field="player_id"),
    # Synced global reference — same names as ops.
    Spec("country"),
    Spec("insights_rulesets"),
    # tenant_settings carries live_sends_enabled — force off in demo.
    Spec(
        "tenant_settings",
        kind="tenant",
        post=lambda doc, scope: {**doc, "live_sends_enabled": False},
    ),
    # Deliberately skipped:
    #   users / venue_access      — real staff identities (demo users only)
    #   platform_settings_history — audit noise, may carry actor emails
    #   _crm_sync_state           — stale resume token breaks demo worker
    #   inbound_unknowns          — real WA messages (phone/name/free-text
    #                               body) with no tenant link to scope by
    Spec("users", kind="skip"),
    Spec("venue_access", kind="skip"),
    Spec("platform_settings_history", kind="skip"),
    Spec("_crm_sync_state", kind="skip"),
    Spec("inbound_unknowns", kind="skip"),
]


def resolve_crm_scope(crm_db, venue_ids):
    if not venue_ids:
        return Scope(full=True)
    venue_strs = [str(v) for v in _oids(venue_ids)]
    scope = Scope(
        full=False,
        venue_oids=_oids(venue_ids),
        venue_strs=venue_strs,
    )
    scope.queries["players"] = {"venue_ids": {"$in": venue_strs}}

    for b in crm_db["bookings"].find(
        {"tenant_id": {"$in": venue_strs}}, {"player_id": 1}
    ):
        if b.get("player_id"):
            scope.player_ids.add(b["player_id"])
    for c in crm_db["check_ins"].find(
        {"tenant_id": {"$in": venue_strs}}, {"player_id": 1}
    ):
        if c.get("player_id"):
            scope.player_ids.add(c["player_id"])
    for p in crm_db["players"].find(
        {"venue_ids": {"$in": venue_strs}}, {"_id": 1}
    ):
        scope.player_ids.add(p["_id"])
    scope.player_ids = set(_oids(scope.player_ids))

    logger.info(
        "CRM scope: %d venues → %d players",
        len(venue_strs),
        len(scope.player_ids),
    )
    return scope


# ---------------------------------------------------------------------------
# Copy engine
# ---------------------------------------------------------------------------

def copy_db(source_db, target_db, specs, scope):
    """Drop-and-copy each specced collection; returns per-collection counts."""
    counts = {}
    known = set(source_db.list_collection_names())
    for spec in specs:
        if spec.name not in known:
            counts[spec.name] = 0
            continue
        query = _query(spec, scope)
        target_coll = target_db[spec.name]
        target_coll.delete_many({})
        if query is None:
            counts[spec.name] = 0
            continue
        batch, inserted = [], 0
        # _id-ordered reads keep the copy deterministic — venue name
        # collision suffixes resolve identically on every refresh.
        taken_names = set() if spec.name == "venue" else None
        for doc in source_db[spec.name].find(query).sort("_id", 1):
            if spec.mask:
                doc = maskers.apply(
                    spec.name, doc, taken_names=taken_names
                )
            if spec.post:
                doc = spec.post(doc, scope)
            doc = images.rewrite_doc_images(spec.name, doc)
            batch.append(doc)
            if len(batch) >= BATCH_SIZE:
                target_coll.insert_many(batch, ordered=False)
                inserted += len(batch)
                batch = []
        if batch:
            target_coll.insert_many(batch, ordered=False)
            inserted += len(batch)
        counts[spec.name] = inserted
        logger.info("Copied %s: %d docs", spec.name, inserted)
    skipped = known - {s.name for s in specs}
    if skipped:
        logger.info("Skipped unspecced source collections: %s", sorted(skipped))
    return counts
