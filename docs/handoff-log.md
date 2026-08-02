# Handoff Log

Running session-by-session record of what happened, in reverse-chronological order (newest first).

## 2026-08-02 — Shop product images/specs: close the gallery/attributes gap

- **Context:** VARS reported production shop products still look
  "incomplete" (images/info) after the previous session's Shop correction.
  Investigated whether this was missing Odoo data entry or a real code gap —
  it was mostly a code gap: `controllers/shop.py` only ever read the single
  `product.template.image_1920` field and hardcoded `specification_groups: []`
  unconditionally, even though `website_sale` (already a dependency) exposes
  a proper multi-image gallery (`product_template_image_ids`) and attribute
  data (`attribute_line_ids`) that were simply never read.
- **`controllers/shop.py`**: new `_media_list()` builds a real `media` array
  from the main template image plus every `product_template_image_ids` entry
  that actually has image data; new `_specification_groups()` maps
  `attribute_line_ids` into a `{heading: "Specifications", items: [{label,
  value}]}` group instead of the previous hardcoded `[]`. `_summary()`'s
  `primary_media` now derives from `_media_list()`'s first item rather than
  duplicating the same-image check inline.
- **Tests**: two new cases in `test_shop_api.py` — a product with a real
  multi-image gallery and an attribute line (asserts 3 media items, 1 spec
  group with the right label/value), and a product with an image-less
  `product.image` row (asserts it's correctly excluded, not rendered as a
  broken media entry). Full suite: 55/55 green.
- **Verified for real**: created a `product.template` via plain ORM (no test
  harness) with 2 real images and a real attribute line, confirmed via curl
  that `/api/v1/store/products/en/<slug>` returns both images and the
  correct spec group, then deleted the fixture.
- Manifest version bumped to `19.0.1.4.0`. See `docs/decisions.md` ADR-010's
  2026-08-02 amendment for the full record.
- **Also this session** (frontend-side, tracked in `varsco_com`, not here):
  fixed a cart-hydration race that could wipe a guest's `/shop` cart on
  login, a login/auth race that could intermittently fail to redirect after
  sign-in, checkout surfacing the raw string "unauthorized" instead of a
  human message, session-cookie lifetime mismatch (30-day browser cookie vs
  Odoo's 7-day session), and removed the "Add to Cart"/"Add to Quote Cart"
  buttons from the informational `/products` portfolio (that page's separate
  "quote cart" system was unwired from the live UI entirely, kept in the
  codebase for potential reuse elsewhere). Corrected two stale doc claims in
  this repo's own `docs/architecture.md` along the way: the "Customer-portal
  reads/writes" section said `auth="user"`, but every one of those routes
  (including checkout) actually uses `auth="public"` + a manual
  `_portal_partner()` session check — the code was already right, just the
  docs were wrong.
- **Not fixed by anyone yet**: "no payment method shown" at checkout is a
  real *operational* gap, not code — no `payment.provider` is currently
  `state in (enabled, test)` and `is_published=True` on production. Needs a
  human with Odoo admin access: Settings → Payment Providers → enable +
  publish a provider (e.g. Iyzico).
- **Next**: sync this module's vendored copy in `varsco_odoo_staging`
  (tracked there, not here).

## 2026-08-02 — Correction: Shop reads real Odoo product data, not the curated catalog

- **Context:** VARS corrected the immediately-preceding session's direction: the Products/Categories admin UI added there (curated `varsco.catalog.item` model) was the wrong approach entirely. The actual requirement is porting `erp.varsco.com/shop` (Odoo's native `website_sale` storefront — confirmed live with 7 real published products) into the new frontend with the same content/URL structure, using real Odoo product data, not a parallel system requiring every product re-entered a second time. See `docs/decisions.md` ADR-010 for the full record, including the reasoning for why ADR-006's curated model stays right for the *separate* `/products` portfolio but was wrong here.
- **Removed** last session's `views/catalog_views.xml` (Products/Categories menu) — zero real consumers, wrongly implied it managed Shop content.
- **New `controllers/shop.py`**: `GET /api/v1/store/products/{locale}` and `.../{locale}/{url_path}`, reading `product.template` directly, gated on `is_published` (`website_sale`, newly added to `depends`). Slugs generated via `request.env['ir.http']._slug()`/`_unslug()` — the exact same helper `website_sale` uses internally, so URLs match its own `/shop/<slug>-<id>` convention.
- **`checkout.py`** simplified: sellability check is now a direct `product.product_tmpl_id.is_published`, replacing the `varsco.catalog.item.item_type == "purchasable_now"` lookup.
- **Verified for real, not just "tests pass"**: created a product via plain `product.template.create()` (no catalog-item involved) with `is_published=False`, confirmed absent from `/api/v1/store/products/en`; toggled `is_published=True` the normal way; confirmed it appeared immediately with correct real price/stock/slug; confirmed detail-by-slug lookup works. This is the literal "toggle Published, it shows up" workflow VARS asked for.
- Test suite: 53/53 green (new `test_shop_api.py` + updated `test_checkout_api.py` fixtures). Along the way, found and cleaned up leftover test data in the shared `odoo19_test_varsco` database from earlier manual seeding sessions (4 `local-*` catalog items, a stray `payment.provider`) that was causing 2 unrelated pre-existing tests to fail — not a code regression, just accumulated manual-testing residue.
- Manifest version bumped to `19.0.1.3.0`.
- **Not done, deliberately**: per-locale translation-context switching for the new shop endpoints (documented as a known simplification in `shop.py`'s docstring); mapping product attributes into `specification_groups` (deferred to the tracked "Attributes & variations" backlog item).
- **Next**: on the `varsco_com` frontend side (tracked in that repo) — point `store-data.ts` at the new `/api/v1/store/products/*` endpoints instead of the curated `/api/v1/products/*` ones; update `varsco_odoo_staging`'s vendored copy and its README (currently tells the reader to use the now-removed catalog admin UI).

## 2026-08-02 — Catalog admin UI (Products/Categories backend views)

- **Context:** VARS installed this module + `midvex_sale_payment_link` on production and pushed the frontend, but `/shop` still showed zero products. Root cause: `varsco.catalog.category`/`varsco.catalog.item`/their `.i18n` models had full ACL grants but **zero backend views or menu** — there was no way for a human to create catalog content at all short of raw Developer Mode technical-model editing.
- **New `views/catalog_views.xml`**: a "Varsco Catalog" top-level menu (restricted to `base.group_system`, matching the existing ACL) with Products and Categories list/form views. Category translations are an inline editable list (simple fields only). Product translations use a list+form combo — the list shows locale/name/review status, the form (opened per row) has room for the rich-text `description_html` (html widget) and the `media`/`specification_groups` JSON fields (plain text widgets for now — no custom JSON editor built).
- **Verified** (not just "loads without error"): created a category + product through the ORM using exactly the fields the new form exposes, confirmed both report `_is_servable() == True` — i.e., an admin filling in the form correctly produces content the public API will actually serve. Menu/action wiring also checked directly (`ir.ui.menu`/`ir.actions.act_window` refs resolve, root menu really is `base.group_system`-only).
- Manifest version bumped to `19.0.1.2.0`.

## 2026-08-02 — Iyzico payment via new `midvex_sale_payment_link` module; Settings UI

- **Context:** VARS asked (from the `aqua-bloom-portal`/`varsco_com` frontend session) whether payment should be built as an Odoo module, since `payment_iyzico` is already installed. Traced the real mechanism: `sale.order.get_portal_url()` (core `portal`) already returns a full URL with `access_token` embedded, landing on Odoo's own customer-portal order page, which already renders whatever `payment.provider`s are compatible — `payment_iyzico` fully handles the rest natively. See `docs/decisions.md` ADR-009 for the full record.
- **New module**: `midvex_sale_payment_link` (`custom-addons/midvex_sale_payment_link/`) — one method, `sale.order.get_payment_portal_url()`. Depends only on `sale`/`portal`/`payment`; no VARS-specific code, no config of its own. Own tests (`TestSaleOrderPaymentLinkNoProvider`/`WithProvider`), both green against `odoo19_test_varsco`.
- **`checkout.py`**: now calls `order.get_payment_portal_url()` and includes `payment_url` in the response only when not `None`. No provider-compatibility logic duplicated here.
- **Settings UI**: new `res.config.settings` panel (Settings → Varsco Content API) exposing `write_token` (with a "Generate New Token" button, confirmation-gated), `base_url`, `allowed_frontend_origin` as real form fields — previously only reachable via raw System Parameters/XML.
- **Verified against the real local instance** (`odoo19_test_varsco`, not just unit-level): full module install/upgrade clean (`-u varsco_content_api`, auto-pulled in the new dependency, no errors); new module's own tests green (2/2); this module's full suite green (44/44, no regressions) including two new checkout cases (`payment_url` present with a compatible provider, absent without one — both real `HttpCase`/`url_open` HTTP-level tests, not mocked).
- **Deliberately not done**: the full `varsco_content_api` → generic-name rename (module + every `varsco.*` model), also raised in the same session and explicitly deferred — real migration-risk change, wants its own dedicated session once a second real client exists to prove the template against. Live Iyzico sandbox transaction completion also not exercised — needs VARS's own test/sandbox credentials configured in Odoo, out of this session's reach; verification went exactly up to "the portal page returns a correct, working `payment_url`."
- **Next**: on the `varsco_com` frontend side (tracked in that repo, not here) — wire the new `payment_url` field into the checkout UI, and fix a separately-discovered frontend bug where the catalog `purchase` field's real nested shape (`{product_id, amount, currency, available, qty_available} | null` — confirmed correct here by `TestProductsApi.test_purchasable_now_item_exposes_price_and_stock_only`) didn't match what that repo had built.

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
