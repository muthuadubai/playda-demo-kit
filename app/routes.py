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


@demo_bp.before_request
def require_auth():
    if not _authorized():
        return jsonify({"success": False, "error": "unauthorized"}), 401


@demo_bp.route("/api/demo/refresh", methods=["POST"])
def refresh():
    data = request.get_json(force=True, silent=True) or {}
    try:
        report = pipeline.refresh_ops(
            venue_ids=_venue_ids(data),
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
    try:
        report = pipeline.refresh_crm(venue_ids=_venue_ids(data))
    except safety.SafetyError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500
    return jsonify({"success": True, "report": report})


@demo_bp.route("/api/demo/status", methods=["GET"])
def status():
    return jsonify({"success": True, "status": pipeline.status()})
