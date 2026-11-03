"""Refresh pipelines — shared by the CLI and the HTTP API."""

import logging

from pymongo import MongoClient

from demo_kit import config, copier, post_fixups, safety

logger = logging.getLogger("demo_kit.pipeline")


def _source_client():
    if not config.SOURCE_MONGO_URI:
        raise safety.SafetyError("SOURCE_MONGO_URI is not set")
    return MongoClient(config.SOURCE_MONGO_URI)


def _demo_client():
    return MongoClient(config.DEMO_MONGO_URI)


def refresh_ops(venue_ids=None, lookback_days=None, pair_crm=False):
    """prod `playda` → `playda_demo` (masked)."""
    safety.guard(config.DEMO_OPS_DB_NAME)
    src_client, demo_client = _source_client(), _demo_client()
    try:
        source_db = src_client[config.SOURCE_DB_NAME]
        demo_db = demo_client[config.DEMO_OPS_DB_NAME]
        scope = copier.resolve_ops_scope(source_db, venue_ids, lookback_days)
        counts = copier.copy_db(source_db, demo_db, copier.OPS_SPECS, scope)
        fixups = post_fixups.apply(demo_db, scope, counts)
        report = {
            "target": config.DEMO_OPS_DB_NAME,
            "scope": "full" if scope.full else [str(v) for v in scope.venue_oids],
            "lookback_days": lookback_days,
            "counts": counts,
            **fixups,
        }
        if pair_crm:
            report["crm"] = refresh_crm(venue_ids=venue_ids)
        return report
    finally:
        src_client.close()
        demo_client.close()


def refresh_crm(venue_ids=None):
    """prod `playda_crm` → `playda_crm_demo` (masked)."""
    safety.guard(config.DEMO_CRM_DB_NAME)
    if not config.SOURCE_CRM_MONGO_URI:
        raise safety.SafetyError("SOURCE_CRM_MONGO_URI is not set")
    src_client, demo_client = MongoClient(config.SOURCE_CRM_MONGO_URI), _demo_client()
    try:
        source_db = src_client[config.SOURCE_CRM_DB_NAME]
        demo_db = demo_client[config.DEMO_CRM_DB_NAME]
        scope = copier.resolve_crm_scope(source_db, venue_ids)
        counts = copier.copy_db(source_db, demo_db, copier.CRM_SPECS, scope)
        post_fixups.write_meta(demo_db, scope, counts)
        return {
            "target": config.DEMO_CRM_DB_NAME,
            "scope": "full" if scope.full else [str(v) for v in scope.venue_oids],
            "counts": counts,
        }
    finally:
        src_client.close()
        demo_client.close()


def status():
    demo_client = _demo_client()
    try:
        out = {}
        for name in (config.DEMO_OPS_DB_NAME, config.DEMO_CRM_DB_NAME):
            db = demo_client[name]
            meta = db["_demo_meta"].find_one({"_id": "refresh"})
            collections = {
                c: db[c].estimated_document_count()
                for c in db.list_collection_names()
                if not c.startswith("_")
            }
            out[name] = {"meta": meta, "collections": collections}
        return out
    finally:
        demo_client.close()
