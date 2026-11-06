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
- `demo_kit/images.py` — GCS blob copy + URL rewrite (`GCS_SOURCE_BUCKET`
  → `GCS_DEMO_BUCKET`) run per doc inside `copier.copy_db`
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
- **Skipped by design**: ops `notifications`, `ai_insights_*` (free text may
  embed names), CRM `users`/`venue_access`/`platform_settings_history`/
  `_crm_sync_state`.
- **Ops collection names are singular**: `court`, `court_blocks`,
  `pricing_template`, `discount_template`, `promotion` (camelCase
  `venueId`, `isGlobal` flag), `country`, `platform_refund_policy`,
  `terms_acceptances`, `player_due_balances`, `late_cancellation_events`,
  `cancel_booking_tokens`. Verified against live prod — don't rename back
  to plural guesses.
- **Free-text residual**: `bookings.notes` gets digits/emails scrubbed but
  first names in prose survive (unreliable to detect). Consider clearing
  notes entirely if stricter masking is required.
- **Nested person fields**: `matches.slots.teamN[]`, `player_blocks`,
  `venue_notification_settings.channels.*.recipients[]` all carry
  player/staff PII — masked via recursive person-tree walk + recipients
  walk. When adding collections, audit nested structures, not just top
  level.
- **CRM additions**: `country`, `insights_rulesets` (global),
  `inbound_autoreplies`, `player_blocks`, `tenant_settings` (forced
  `live_sends_enabled=false` via spec `post`). `inbound_unknowns` skipped —
  real WA messages with no tenant linkage. `campaign_sends.to_address`
  masked per player; `provider_message_id` rewritten to fake `SM…` SIDs
  (real ones resolve prod messages in the Twilio console — demo runs prod
  creds). `crm payments` is empty in prod — 0 docs is expected, not a bug.
- **Refresh = full rebuild**: every specced collection is wiped and recopied
  — point-in-time, no change-stream tailing.
- **Images live outside Mongo**: docs store full public GCS URLs. Copied
  `venue.pictures` / `promotion.posterImage|thumbnailImage` blobs are
  server-side copied `GCS_SOURCE_BUCKET` → `GCS_DEMO_BUCKET` and URLs
  rewritten — demo-be uploads/deletes can never reach prod objects.
  `players.profile_image` is PII: cleared by `_DEVICE_FIELDS`, never copied.
  playda-be-demo runs `GCS_BUCKET_NAME=playda-images-demo`; its blob-name
  extraction also fails closed on any residual prod URL.
- **Realistic name masking**: `maskers._ids.masked_name` picks a
  culturally-coherent first+last from per-ethnicity pools (bucket chosen
  deterministically per _id) — no cross-ethnicity mixes, same name for the
  same player in both DBs.
- **Venue names are acronym-masked**: `Le Padel Club` → `LPC Club`
  (initials + fixed " Club" suffix). Collisions get ` Club 2`/` 3` by
  `_id`-ordered copy — deterministic across refreshes and identical in the
  ops/crm pairs. Single-token/non-alpha names fall back to `Demo Arena
  {n}`. Names aren't denormalized into other collections (`venue_id`
  only), so `venue.name` is the only field needing this.
- **Notification posture**: demo backend runs prod Twilio/email creds on
  purpose — masked contacts are the safety boundary (`+1555…` unroutable,
  `.invalid` undeliverable); only whitelisted attendees are reachable.
  Copied `venue_notification_settings` are forced off by post-fixups so
  demos default to silent; presenters re-enable toggles in the demo portal
  to show live notifications to whitelisted numbers.

## Verification

`python -m demo_kit status` after a refresh; PII leak audit = regex scan of
`playda_demo` for real mobile/email patterns (see plan in playda-be/AGENTS.md).
