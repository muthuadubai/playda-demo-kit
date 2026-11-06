"""Thin HTTP wrapper over demo_kit.pipeline — called from the admin portal
or a scheduler. Auth: X-Job-Token, or an admin-role playda-be JWT."""

import jwt
from flask import Blueprint, jsonify, request

from demo_kit import config, pipeline, safety

demo_bp = Blueprint("demo", __name__)


def _is_admin_jwt(token):
    try:
        claims = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=["HS256"])
    except Exception:
        return False
    return claims.get("role") == "admin"


def _authorized():
    if config.DEMO_JOB_TOKEN and request.headers.get("X-Job-Token") == config.DEMO_JOB_TOKEN:
        return True
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and config.JWT_SECRET_KEY:
        return _is_admin_jwt(auth[7:])
    return False


def _venue_ids(data):
    ids = data.get("venue_ids")
    if isinstance(ids, str):
        ids = [ids]
    return [v for v in (ids or []) if v] or None


def _scope_or_400(data):
    """API callers must scope explicitly: venue_ids, or `full: true` for a
    complete copy. An omitted scope is a bug, not a full-refresh request —
    the admin UI now sends explicit ids only."""
    ids = _venue_ids(data)
    if not ids and not data.get("full"):
        return None, (
            jsonify(
                {
                    "success": False,
                    "error": "venue_ids required — pass venue_ids, or "
                    "'full': true for a complete copy",
                }
            ),
            400,
        )
    return ids, None


@demo_bp.before_request
def require_auth():
    if request.method == "OPTIONS":
        return None  # let flask-cors answer the preflight
    if not _authorized():
        return jsonify({"success": False, "error": "unauthorized"}), 401


@demo_bp.route("/api/demo/refresh", methods=["POST"])
def refresh():
    data = request.get_json(force=True, silent=True) or {}
    venue_ids, err = _scope_or_400(data)
    if err:
        return err
    try:
        report = pipeline.refresh_ops(
            venue_ids=venue_ids,
            lookback_days=data.get("lookback_days"),
            pair_crm=bool(data.get("pair_crm")),
        )
    except safety.SafetyError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500
    return jsonify({"success": True, "report": report})


@demo_bp.route("/api/demo/refresh-crm", methods=["POST"])
def refresh_crm():
    data = request.get_json(force=True, silent=True) or {}
    venue_ids, err = _scope_or_400(data)
    if err:
        return err
    try:
        report = pipeline.refresh_crm(venue_ids=venue_ids)
    except safety.SafetyError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500
    return jsonify({"success": True, "report": report})


@demo_bp.route("/api/demo/venues", methods=["GET"])
def venues():
    """Prod venue list for the refresh-scope picker — sourced from the ops
    DB so the picker shows ALL venues regardless of what's already demoed."""
    try:
        out = pipeline.list_source_venues()
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500
    return jsonify({"success": True, "venues": out})


@demo_bp.route("/api/demo/status", methods=["GET"])
def status():
    return jsonify({"success": True, "status": pipeline.status()})
