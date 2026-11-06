import os

from dotenv import load_dotenv

load_dotenv()

# --- Sources (READ ONLY credentials) ---
# Operational cluster (prod `playda` DB) — source of the ops copy.
SOURCE_MONGO_URI = os.environ.get("SOURCE_MONGO_URI", "")
SOURCE_DB_NAME = os.environ.get("SOURCE_DB_NAME", "playda")

# Prod CRM DB — source of the crm_copy profile. Lives on the CRM cluster,
# so it defaults to the source URI only if you point that at the CRM cluster;
# normally set explicitly with a read-only credential.
SOURCE_CRM_MONGO_URI = os.environ.get("SOURCE_CRM_MONGO_URI", "")
SOURCE_CRM_DB_NAME = os.environ.get("SOURCE_CRM_DB_NAME", "playda_crm")

# --- Target (WRITE credential on the CRM Atlas cluster) ---
DEMO_MONGO_URI = os.environ.get("DEMO_MONGO_URI", "")
DEMO_OPS_DB_NAME = os.environ.get("DEMO_OPS_DB_NAME", "playda_demo")
DEMO_CRM_DB_NAME = os.environ.get("DEMO_CRM_DB_NAME", "playda_crm_demo")

# Safety latch — must equal the target db name being written, per run.
CONFIRM_TARGET = os.environ.get("CONFIRM_TARGET", "")

# Deterministic masking salt. All masked identities are f(_id, DEMO_SALT) —
# the same salt must be used for the ops copy and the crm copy so identities
# agree across playda_demo and playda_crm_demo. Rotate to re-randomize.
DEMO_SALT = os.environ.get("DEMO_SALT", "playda-demo")

# GCS image copy — docs store full public URLs into the prod bucket; the
# refresh server-side-copies referenced blobs into the demo bucket and
# rewrites the stored URLs so demo uploads/deletes can never reach prod.
# Empty GCS_DEMO_BUCKET disables rewriting (URLs pass through untouched).
GCS_SOURCE_BUCKET = os.environ.get("GCS_SOURCE_BUCKET", "playda-images-prod")
GCS_DEMO_BUCKET = os.environ.get("GCS_DEMO_BUCKET", "")


def _csv(name):
    return {v.strip() for v in os.environ.get(name, "").split(",") if v.strip()}


def _csv_list(name):
    return [v.strip() for v in os.environ.get(name, "").split(",") if v.strip()]


# Whitelist — players/users whose real contact data is preserved so demo
# attendees can log in (email OTP / mobile OTP reach real inboxes/devices).
# Prefer E.164 for mobiles.
DEMO_WHITELIST_MOBILES = _csv("DEMO_WHITELIST_MOBILES")
DEMO_WHITELIST_EMAILS = {e.lower() for e in _csv("DEMO_WHITELIST_EMAILS")}

# Demo accounts inserted by post_fixups (emails should be whitelisted too).
# Emails AND names accept comma-separated lists — one account per email;
# names pair by position and extras fall back to the email local part.
DEMO_ADMIN_EMAILS = [e.lower() for e in _csv_list("DEMO_ADMIN_EMAIL")]
DEMO_ADMIN_NAMES = _csv_list("DEMO_ADMIN_NAME") or ["Demo Admin"]
DEMO_OWNER_EMAILS = [e.lower() for e in _csv_list("DEMO_OWNER_EMAIL")]
DEMO_OWNER_NAMES = _csv_list("DEMO_OWNER_NAME") or ["Demo Owner"]
DEMO_MANAGER_EMAILS = [e.lower() for e in _csv_list("DEMO_MANAGER_EMAIL")]
DEMO_MANAGER_NAMES = _csv_list("DEMO_MANAGER_NAME") or ["Demo Manager"]

# API auth — /api/demo/* accepts either the job token or an admin-role JWT
# issued by playda-be (same shared secret as crm-be).
DEMO_JOB_TOKEN = os.environ.get("DEMO_JOB_TOKEN", "")
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "")

# Comma-separated browser origins allowed to call the API (admin portals).
# Default "*" keeps local/dev frictionless — set explicit origins in deploys.
ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()
]

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
