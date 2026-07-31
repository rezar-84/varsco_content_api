# Handoff Log

Running session-by-session record of what happened, in reverse-chronological order (newest first).

## 2026-07-31 — Repo split from `varsco_front`; portal auth bugs fixed pre-split

- **Context:** Per ADR-007, this repo's scope is the Odoo middleware/API module only. It was split out of the `varsco_front` monorepo (`odoo/addons/varsco_content_api/` there) into its own repo at `git@github.com:rezar-84/varsco_content_api.git` so it can be deployed to production independently — cloned directly into an Odoo host's `addons_path` and installed/upgraded via the web interface (Apps → Update Apps List), no build step. `varsco_front` keeps full pre-pivot history and the archived CMS/frontend layer; this repo starts fresh with just the active module + its current docs.
- **Pre-split verification:** ran the full test suite against a freshly initialized local Odoo 19 test DB (not one carrying leftover fixture data from earlier runs) and found the portal auth flow had never actually passed:
  - `portal_login` called `Session.authenticate(db, login, password)` — a pre-19 signature. This Odoo 19 instance expects `authenticate(env, credential_dict)`; every login attempt 500'd.
  - The portal test fixture used the pre-19 `groups_id` field on `res.users`, renamed to `group_ids`; `setUpClass` errored before any portal test could run.
  - `/portal/orders` and `/portal/profile` used `auth="user"`, which redirects anonymous `type="http"` requests to `/web/login` (200 + HTML) instead of the JSON 401 the frontend contract expects. Switched to `auth="public"` + the existing manual partner check (`_portal_partner()`), which had been dead code.
  - `portal_orders` read `picking_ids.carrier_tracking_ref` unconditionally; that field only exists when `stock_delivery` is installed, which this module doesn't depend on. Made the read conditional rather than adding an undeclared module dependency.
  - Fixed in `varsco_front` first (commit `d17095b`), then carried into this repo's initial commit. 23/23 tests green on a clean DB.
- **Not yet done** (carried over from the pre-split assessment, still open here):
  - No CI pipeline configured (`docs/quality-assurance.md` describes gates that nothing currently enforces automatically).
  - `docs/quality-assurance.md` §3 manual QA checklists (lead/checkout/portal/catalog flows) have no recorded sign-off for the current endpoint set.
  - Frontend-side session cookie (`aqua-bloom-portal`) — confirm `Secure`/`SameSite=Strict` are set before portal auth goes live (`docs/security.md` §2).
  - `write_token` rotation for `/api/v1/leads` not yet confirmed set up on production.
- **Next:** stand up CI (Ruff/Black/tests at minimum) for this repo; work the §3/§5 checklists in `docs/quality-assurance.md` before first production install.
