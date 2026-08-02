# Architecture

## 1. Principle

**This repository is a secure Odoo 19 API/middleware module** — nothing
more. It exposes a narrow, versioned HTTP contract that an external
frontend (currently `aqua-bloom-portal`, a separate repository) calls for
authentication, CRM lead capture, product catalog browsing, and checkout.
Odoo remains the single source of truth for all business data; this repo
never renders a public page or owns presentation.

```
External frontend (aqua-bloom-portal, separate repo)
        │  BFF/server-side calls only — see below
        ▼
varsco_content_api (this repo, Odoo addon)
        │
Odoo 19 backend
   ├─ CRM (leads, `crm@`/`leads@` notification pipeline)
   ├─ Sales/stock (checkout, orders, pricing)
   └─ Portal (auth, profile, order history)
```

The frontend owns everything about how it talks to Odoo — its own
BFF/server-route layer, session-cookie handling, CORS, rate limiting, and
Zod input validation on the client side of the contract. This repo's job
stops at the Odoo boundary: validate, authorize, and never leak more than
the allow-listed contract below.

## 2. `varsco_content_api` (the contract)

A thin Odoo module exposing:
- **Public catalog reads** (`auth="public"`): cacheable, allow-listed
  fields only — never cost/margin/internal fields.
- **Secure server-to-server writes** (`auth="public"` + bearer
  `write_token`): used by the frontend's *server*, never its browser.
- **Customer-portal reads/writes** (`auth="public"` + a manual
  session-cookie check against `_portal_partner()`, not Odoo's `auth="user"`
  decorator — that would redirect an anonymous `type="http"` request to
  `/web/login` instead of returning the JSON 401 the frontend contract
  expects): scoped to the authenticated partner via record rules
  (`docs/security.md`).

Versioned under `/api/v1/`. Breaking changes → `/api/v2/` + deprecation
window. The contract in §5 is a shared interface with a separate repo —
changing it is a `CLAUDE.md` §6 guardrail.

> An earlier version of this module also served a full content-management
> layer (pages/sections, blog, nav menu, redirects) for a since-discontinued
> Astro frontend built in this same repo. That layer is archived, not
> deleted — see `archive/README.md` and `archive/docs/data-model-cms.md` —
> and is not part of the active contract below.

## 3. Data flow

**Catalog browsing (informational portfolio):** frontend calls
`GET /api/v1/products/{locale}` and `GET /api/v1/products/{locale}/{url_path}`
→ curated `varsco.catalog.item` data, price/stock only when
`item_type == "purchasable_now"`.

**Shop browsing (transactional storefront):** frontend calls
`GET /api/v1/store/products/{locale}` and
`GET /api/v1/store/products/{locale}/{url_path}` → real `product.template`
data, gated purely on `is_published` (website_sale's native flag), including
a real multi-image gallery (`product_template_image_ids`) and
`specification_groups` mapped from `attribute_line_ids` — the
same data `erp.varsco.com/shop` itself reads. No curated model involved;
toggling "Published" on a normal Odoo product is the entire workflow.

**Reviews & ratings:** `GET /api/v1/store/products/{locale}/{url_path}/reviews`
reads Odoo's native `rating.rating` model (`product.template` already
inherits `rating.mixin` via `website_sale`) — no custom review model.
`rating_avg`/`rating_count` are also included on every shop product
summary/detail (`controllers/shop.py`). `POST .../reviews` requires a
session-authenticated partner with a **verified purchase** — at least one
confirmed (`state == "sale"`) `sale.order.line` for the product, matching
exactly how `controllers/checkout.py` creates orders — and rejects a second
review from the same partner for the same product (enforced at the API
layer; `rating.rating` itself has no uniqueness constraint).

**Wishlist:** `GET`/`POST`/`DELETE /api/v1/store/wishlist` read/write Odoo's
native `product.wishlist` model (`website_sale_wishlist`, `auto_install`
alongside `website_sale`, now an explicit `depends` since this module
directly relies on its model) — no custom wishlist model. Session-
authenticated only; unlike the cart, the wishlist has no guest/local-only
mode. Items are serialized through the exact same `_summary()` shape as
`/api/v1/store/products/*`, so the frontend renders a wishlist item with
the same product card component it already has.

**Lead capture:** visitor submits a form on the frontend → frontend's
*server* validates → `POST /api/v1/leads` (bearer-token authenticated) →
Odoo creates `crm.lead` with `type: "lead"` (explicit — see ADR-008) and a
formatted, HTML-escaped Notes section → existing `crm@`/`leads@` notification pipeline
fires.

**Portal auth:** `POST /api/v1/portal/auth/login` → Odoo's native
`request.session.authenticate` → frontend maps the resulting Odoo session
id into its own httpOnly cookie for subsequent `auth="user"` calls
(`GET /api/v1/portal/orders`, `PUT /api/v1/portal/profile`).

**Self-service registration:** `POST /api/v1/portal/auth/register` creates a
real `res.partner` + `res.users` (`base.group_portal` only, never an
internal user) with the password the visitor chose, then immediately
authenticates that account and returns the same session/user shape as
`portal_login` — registering and being logged in are the same real Odoo
account from the first response, not a frontend-local placeholder.

**Checkout:** `POST /api/v1/store/checkout` (session-authenticated) →
server-side re-validation of every line against `is_published` and live
stock → draft `sale.order`. The
response includes an optional `payment_url` — the order's absolute customer
portal URL — whenever a compatible `payment.provider` exists (e.g. Iyzico).
Generated by `midvex_sale_payment_link` (a separate, generic module this one
depends on: `sale.order.get_payment_portal_url()`), not by this module
directly — no payment-provider-specific code lives here. `payment_url` is
omitted, not null, when no provider is available; callers should treat
absence the same as "no online payment for this order."

## 4. Cross-cutting concerns

- **i18n** — locales are data (`varsco.content.locale`), not code; a client
  deployment's active locale list is a data change (`decisions.md` ADR-003).
  Only `reviewed` translations are ever served.
- **Field discipline** — every endpoint declares an explicit allow-list of
  Odoo fields. Cost, margin, internal notes, partner PII, and any
  write-capable route are forbidden on public endpoints. When adding a
  field, ask: "would VARS be unhappy if a competitor scraped this?" If yes,
  it doesn't go on a public endpoint.
- **Security** — see `docs/security.md`: write-token handling, portal
  session-cookie posture, CORS, and record-rule scoping are the frontend's
  and this module's shared responsibility at the API boundary.
- **SEO/rendering/edge/CDN** — entirely the frontend's concern now; this
  repo has no rendering, caching, or deploy-topology responsibility for
  public pages.

## 5. Content API contract (`/api/v1`)

> This is a **shared interface** with `aqua-bloom-portal` (separate repo,
> see its `doc/odoo_api_spec.md` for the frontend-side view of the same
> contract). Treat it like a public API: additive changes are fine,
> breaking changes need a version bump and human sign-off.

Public read endpoints (`auth="public"`, cacheable):

| Method | Path | Returns |
|--------|------|---------|
| GET | `/api/v1/products/{locale}` | Curated public catalog-item list; never raw Odoo product records |
| GET | `/api/v1/products/{locale}/{url_path}` | One curated catalog item: localized copy, media, specifications, quote CTA, price/stock if `purchasable_now` |
| GET | `/api/v1/store/products/{locale}` | **Real** Odoo storefront products — every `product.template` with `is_published = True` (`website_sale`'s native flag), same list as `erp.varsco.com/shop` shows today. Not the curated model above. |
| GET | `/api/v1/store/products/{locale}/{url_path}` | One real product by its `ir.http._slug()`-generated slug (the exact convention `website_sale` itself uses for `/shop/<slug>-<id>`) — 404 if unpublished or unknown |
| GET | `/api/v1/store/products/{locale}/{url_path}/reviews` | Consumed `rating.rating` records for the product (native `rating` module, no custom model) plus `rating_avg`/`rating_count` in `meta` |

Secure server-to-server write (bearer token):

| Method | Path | Body → effect |
|--------|------|---------------|
| POST | `/api/v1/leads` | `{name, email, company?, message, source, cart_summary?}` → creates `crm.lead` |

Customer-portal endpoints (`auth="public"` + manual `_portal_partner()`
session-cookie check — see `docs/handoff-log.md`'s 2026-07-31 entry for why
this is deliberate, not `auth="user"`):

| Method | Path | Effect |
|--------|------|--------|
| POST | `/api/v1/portal/auth/login` | Authenticates via Odoo session, returns partner summary |
| POST | `/api/v1/portal/auth/register` | `{name, email, phone, company, country, password}` → creates `res.partner` + portal `res.users`, logs in, returns partner summary |
| GET | `/api/v1/portal/orders` | Lists the authenticated partner's `sale.order`s |
| PUT | `/api/v1/portal/profile` | Allow-listed `res.partner` field update |
| POST | `/api/v1/store/checkout` | Validates + creates a draft `sale.order`; response includes `payment_url` when a payment provider is available |
| POST | `/api/v1/store/products/{locale}/{url_path}/reviews` | `{rating, feedback?}` → creates a `rating.rating`; 403 without a verified purchase, 409 on a second review for the same product |
| GET | `/api/v1/store/wishlist` | The authenticated partner's wishlist, each item in the same shape as `/api/v1/store/products/*` |
| POST | `/api/v1/store/wishlist` | `{product_id}` (a `product.product` variant id, same field `purchase.product_id` already exposes) → adds/returns the item, idempotent |
| DELETE | `/api/v1/store/wishlist/{product_id}` | Removes the item if owned by the authenticated partner; no-op otherwise |

**Presentation discipline:** catalog `description_html`/media fields
contain sanitized semantic prose, media references, and identifiers only —
never Odoo/QWeb layout markup, classes, inline styles, scripts, or
snippets. The frontend is the only public presentation implementation.

## 6. Repository layout

This repository *is* the addon — the repo root is the module's technical
name (`varsco_content_api`), so it can be cloned directly into an Odoo
`addons_path` directory and installed via the web interface (Apps →
Update Apps List) without any extra nesting.

```
controllers/   models/   tests/   security/   data/   __manifest__.py
docs/                      # this documentation set
```

Historical note: earlier development happened inside a monorepo
(`varsco_front`, formerly `varsco-web`) that also built a since-discontinued
Astro frontend and CMS content layer; that repo's `archive/` still holds
that material for reference. This repo carries forward only the active
middleware module and its current docs.

## 7. Template reuse (agency goal)

varsco.com is the reference build. To keep it reusable:
- `varsco_content_api` is a generic addon parameterized by Odoo config, not
  a varsco fork.
- A new client = new Odoo instance + new frontend pointed at the same
  `/api/v1` contract. Anything that would block that is a design smell —
  flag it.
