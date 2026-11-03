"""Post-copy fixups on playda_demo:

  1. Demo accounts — admin / owner / manager users + venue_access rows so
     the demo portal is loggable into out of the box.
  2. Notification kill-flags — every venue_notification_settings channels
     `enabled` flag forced false. The demo backend runs with PROD Twilio/
     email credentials (deliberate — the presenter can re-enable channel
     toggles per venue in the demo portal to demo notifications). The
     actual safety boundary is the masked data: masked mobiles are
     unroutable and masked emails undeliverable, so only whitelisted demo
     attendees can ever receive a real message.
  3. _demo_meta — audit record of the refresh (scope, counts, salt hash).
"""

import datetime
import hashlib
import logging

from bson import ObjectId

from demo_kit import config

logger = logging.getLogger("demo_kit.post_fixups")


def _user_doc(email, name, role):
    now = datetime.datetime.now(datetime.timezone.utc)
    return {
        "_id": ObjectId(),
        "name": name,
        "email": email.strip().lower(),
        "role": role,
        "active": True,
        "created_at": now,
        "updated_at": now,
        "demo_account": True,
    }


def _access_doc(user_id, venue_id, access_level):
    now = datetime.datetime.now(datetime.timezone.utc)
    doc = {
        "_id": ObjectId(),
        "user_id": user_id,
        "venue_id": venue_id,
        "access_level": access_level,
        "created_at": now,
        "updated_at": now,
        "demo_account": True,
    }
    # CRM permissions live on the access record for non-owners.
    if access_level == "manager":
        doc["permissions"] = {"crm_view": True, "crm_manage": True}
    return doc


def _insert_demo_accounts(demo_db, scope):
    venue_oids = (
        scope.venue_oids
        if not scope.full
        else [v["_id"] for v in demo_db["venue"].find({}, {"_id": 1})]
    )
    inserted = []
    specs = [
        (config.DEMO_ADMIN_EMAIL, config.DEMO_ADMIN_NAME, "admin", None),
        (config.DEMO_OWNER_EMAIL, config.DEMO_OWNER_NAME, "owner", "owner"),
        (
            config.DEMO_MANAGER_EMAIL,
            config.DEMO_MANAGER_NAME,
            "manager",
            "manager",
        ),
    ]
    for email, name, role, access_level in specs:
        if not email:
            continue
        email = email.strip().lower()
        existing = demo_db["users"].find_one({"email": email})
        user_id = existing["_id"] if existing else None
        if not user_id:
            user_id = demo_db["users"].insert_one(
                _user_doc(email, name, role)
            ).inserted_id
        if access_level:
            for vid in venue_oids:
                demo_db["venue_access"].replace_one(
                    {"user_id": user_id, "venue_id": vid},
                    _access_doc(user_id, vid, access_level),
                    upsert=True,
                )
        inserted.append({"email": email, "role": role, "access": access_level})
    logger.info("Demo accounts ensured: %s", inserted)
    return inserted


def _disable_notifications(demo_db):
    """Force every `enabled` flag under channels.* to false."""
    patched = 0
    coll = demo_db["venue_notification_settings"]
    for doc in coll.find({"channels": {"$type": "object"}}):
        changed = False
        for channel in (doc.get("channels") or {}).values():
            if not isinstance(channel, dict):
                continue
            for feature in channel.values():
                if isinstance(feature, dict) and feature.get("enabled"):
                    feature["enabled"] = False
                    changed = True
        if changed:
            coll.replace_one({"_id": doc["_id"]}, doc)
            patched += 1
    logger.info("Disabled notification channels on %d settings docs", patched)
    return patched


def _write_meta(demo_db, scope, counts):
    meta = {
        "_id": "refresh",
        "seeded_at": datetime.datetime.now(datetime.timezone.utc),
        "scope": (
            "full" if scope.full else [str(v) for v in scope.venue_oids]
        ),
        "counts": counts,
        "salt_hash": hashlib.sha256(
            config.DEMO_SALT.encode()
        ).hexdigest()[:8],
        "whitelisted_mobiles": len(config.DEMO_WHITELIST_MOBILES),
        "whitelisted_emails": len(config.DEMO_WHITELIST_EMAILS),
    }
    demo_db["_demo_meta"].replace_one({"_id": "refresh"}, meta, upsert=True)


def apply(demo_db, scope, counts):
    demo_accounts = _insert_demo_accounts(demo_db, scope)
    disabled = _disable_notifications(demo_db)
    _write_meta(demo_db, scope, counts)
    return {"demo_accounts": demo_accounts, "notification_docs_disabled": disabled}
