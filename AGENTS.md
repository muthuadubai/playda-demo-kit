# playda-demo-kit — Project Notes

Builds masked demo databases on the CRM Atlas cluster from production data.
Full design + step list lives in `playda-be/AGENTS.md` → "Demo platform —
implementation plan".

## Layout

- `demo_kit/config.py` — env-driven config (see `.env.example`)
- `demo_kit/safety.py` — hard aborts before any write (`guard()`)
- `demo_kit/copier.py` — collection specs + scope resolution + copy engine
  - `OPS_SPECS`: prod `playda` → `playda_demo`
  - `CRM_SPECS`: prod `playda_crm` → `playda_crm_demo`
  - venue scope = two-pass: bookings/check-ins → B/P/U sets → per-spec filter
- `demo_kit/maskers/` — stateless deterministic masking `f(_id, DEMO_SALT)`,
  whitelist-aware. Registry in `maskers/__init__.py`; unlisted collections
  copy unmasked (aggregate/reference data only).
- `demo_kit/post_fixups.py` — demo accounts + venue_access, notification
  kill-flags, `_demo_meta` audit doc
- `demo_kit/pipeline.py` — `refresh_ops` / `refresh_crm` / `status`
- `demo_kit/cli.py` — `python -m demo_kit refresh|refresh-crm|status`
- `app/` + `run.py` — thin Flask API (`POST /api/demo/refresh`,
  `/refresh-crm`, `GET /api/demo/status`)

## Invariants

- **Never write to prod**: read-only source creds; `safety.guard()` runs
  before every copy (demo-name match, CONFIRM_TARGET, host check).
- **Masking is stateless**: masked values depend only on `_id` + `DEMO_SALT`.
  Both profiles must share the same salt or cross-DB identities diverge.
- **Allowlist, not denylist**: collections not in SPECS are skipped —
  new PII-carrying collections fail closed, not open.
- **Skipped by design**: ops `notifications` (free text may embed names),
  CRM `users`/`venue_access`/`platform_settings_history`/`_crm_sync_state`.
- **Refresh = full rebuild**: every specced collection is wiped and recopied
  — point-in-time, no change-stream tailing.
- **Notification posture**: demo backend runs prod Twilio/email creds on
  purpose — masked contacts are the safety boundary (`+1555…` unroutable,
  `.invalid` undeliverable); only whitelisted attendees are reachable.
  Copied `venue_notification_settings` are forced off by post-fixups so
  demos default to silent; presenters re-enable toggles in the demo portal
  to show live notifications to whitelisted numbers.

## Verification

`python -m demo_kit status` after a refresh; PII leak audit = regex scan of
`playda_demo` for real mobile/email patterns (see plan in playda-be/AGENTS.md).
