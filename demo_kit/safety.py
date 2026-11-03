"""Hard aborts before any write. This tool only ever READS from sources.

Every write path must call guard() first — a misconfigured environment
should fail loudly, not write masked data into a prod database.
"""

from urllib.parse import urlparse

from demo_kit import config


class SafetyError(RuntimeError):
    pass


def _host(uri):
    try:
        return urlparse(uri).hostname or ""
    except Exception:
        return ""


def assert_demo_target(db_name):
    if "demo" not in (db_name or "").lower():
        raise SafetyError(
            f"Refusing to write to non-demo database name: {db_name!r}"
        )


def assert_confirm_target(expected_db_name):
    """CONFIRM_TARGET is a comma-separated allowlist of demo db names —
    the service refreshes multiple targets, so each run proves intent by
    being named in the list."""
    allowed = {
        t.strip() for t in config.CONFIRM_TARGET.split(",") if t.strip()
    }
    if expected_db_name not in allowed:
        raise SafetyError(
            f"CONFIRM_TARGET {sorted(allowed)} does not include "
            f"{expected_db_name!r}. Add it to CONFIRM_TARGET to prove the "
            "target is intended."
        )


def assert_target_is_not_source(source_uri, target_uri):
    """ops_copy: writing into the ops cluster would be catastrophic.
    crm_copy intentionally shares the cluster with its source, so callers
    pass the OPS source URI here regardless of which copy runs."""
    src, dst = _host(source_uri), _host(target_uri)
    if src and dst and src == dst:
        raise SafetyError(
            f"Target host {dst!r} equals the ops source host — refusing "
            "to write demo data into the operational cluster."
        )


def guard(target_db_name):
    """Full pre-write check for a target database."""
    assert_demo_target(target_db_name)
    assert_confirm_target(target_db_name)
    assert_target_is_not_source(config.SOURCE_MONGO_URI, config.DEMO_MONGO_URI)
    if not config.DEMO_MONGO_URI:
        raise SafetyError("DEMO_MONGO_URI is not set")
