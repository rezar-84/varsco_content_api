# Security — Middleware API

Extends `CLAUDE.md` §6 (guardrails) and `clean-code.md` §4 (security/privacy
hygiene), which remain the primary reference. This document covers what's
specific to `varsco_content_api` as the security boundary between an
external frontend and Odoo.

## 1. Credential surfaces

| Surface | Credential | Handling |
|---|---|---|
| Public catalog reads | None (`auth="public"`) | Allow-listed fields only — `docs/architecture.md` §4 |
| `POST /api/v1/leads` | Server-side bearer token (`varsco_content_api.write_token`) | Held only by the frontend's **server**, never its browser. Set up rotation on production. |
| Portal endpoints | Odoo native session cookie | See §2 — the frontend maps this into its own httpOnly cookie |
| `POST /api/v1/store/checkout` | `auth="user"` session | Same session mechanism as portal |
| `POST /api/v1/portal/auth/register` | None (public) — creates the account itself | Rate-limited at the frontend edge like any other public POST; always creates `base.group_portal` only, never `base.group_user` |

**Active** credential surface: Iyzico payment integration (`payment_iyzico`,
configured directly in Odoo — this module never touches its credentials).
`POST /api/v1/store/checkout` may now return a `payment_url` pointing at the
order's customer portal page, which is where Odoo's own `payment`/
`payment_iyzico` machinery takes over entirely (redirect, webhook,
transaction verification). This module's only involvement is deciding
*whether* to include that URL — via `midvex_sale_payment_link`'s
`sale.order.get_payment_portal_url()`, which itself contains no
Iyzico-specific or otherwise provider-specific logic, only the generic
`payment.provider._get_compatible_providers()` check. The URL is always
Odoo-generated (`sale.order.get_portal_url()`, core `portal` module) and
never derived from client-supplied input, so this introduces no new
injection/open-redirect surface. Include Iyzico's credentials in any
credential-rotation routine as usual.

**Config management:** `write_token`, `base_url`, and
`allowed_frontend_origin` are editable via Settings → Varsco Content API
(a `res.config.settings` panel this module adds) rather than requiring
direct System Parameters/XML access — the write token has a "Generate New
Token" button that rotates it immediately (with a confirmation prompt,
since it invalidates whatever the frontend currently has configured).

## 2. Session/cookie posture

`portal.py`'s `POST /api/v1/portal/auth/login` uses Odoo's native
`request.session.authenticate` — the resulting session id is what the
frontend must map into its own cookie for subsequent `auth="user"` calls.
The frontend-side contract (`aqua-bloom-portal`'s `doc/security_and_compliance.md`)
requires that cookie carry `HttpOnly`, `Secure`, and `SameSite=Strict` — as
of the last cross-repo handoff, the frontend's login route sets `HttpOnly`
but not yet `Secure`/`SameSite=Strict`. That's a frontend-repo fix, not
something this module can enforce, but it's the actual attack surface a
leaked/stolen session id would exploit against these endpoints — worth
confirming closed before portal auth goes live in production.

## 3. API security & field discipline

- Read endpoints: `auth="public"`, explicit field allow-lists, no
  cost/margin/internal fields (`architecture.md` §5, `data-model.md`).
- `POST /api/v1/leads`: bearer-token authenticated, validated
  (`REQUIRED_FIELDS` in `leads.py`, plus `email` format via
  `odoo.tools.mail.single_email_re`).
- `POST /api/v1/store/checkout`: `auth="user"`, and every line item is
  re-validated server-side against `item_type == "purchasable_now"` and
  live `qty_available` — the frontend hiding non-purchasable items from its
  UI is a convenience, not the security boundary.
- **Access Control Lists (ACL)**: portal endpoints scope every query to the
  authenticated session's own `partner_id` (`portal.py`'s `_portal_partner()`)
  — never a client-supplied id. Odoo record-rule pattern to keep enforcing
  as new portal endpoints are added:
  ```python
  [('partner_id', '=', user.partner_id.id)]
  ```
- **PII logging**: never write complete request bodies, passwords, or PII
  to log servers — clean transaction indices and error codes only.
- **CORS**: the frontend's own BFF layer (not this module) is expected to
  enforce an origin allowlist for its own `/api/*` routes; Odoo itself
  rejects cross-origin browser calls to `/api/v1/*` that don't come through
  that server-side proxy — `controllers/base.py`'s `require_trusted_origin()`
  checks the `Origin` header (when present — server-to-server BFF calls send
  none) against `varsco_content_api.allowed_frontend_origin`
  (`ir.config_parameter`, default `https://varsco.com`) on
  `POST /api/v1/store/checkout` and `PUT /api/v1/portal/profile`, the two
  mutating session-cookie-authenticated routes. This closes the form/fetch
  CSRF gap that `csrf=False` (required since this API can't hand out an
  Odoo-rendered CSRF token to a cross-origin caller) otherwise leaves open.

## 4. Rate limiting & anti-spam

Enforced at the frontend's edge/BFF layer (Cloudflare Turnstile/reCAPTCHA
on lead-capture forms, IP rate limits on POST routes) — this module doesn't
implement its own rate limiting today. If `/api/v1/leads` or
`/api/v1/store/checkout` are ever called from somewhere without that
front-line protection, add rate limiting here before enabling it.

## 5. SPF/DKIM/DMARC

Unchanged requirement from `CLAUDE.md` §6 — lead notification email
deliverability (`crm@`/`leads@`) must stay healthy regardless of which
frontend is calling `/api/v1/leads`.

## 6. Access control (internal Odoo users)

Internal-user ACLs (`security/ir.model.access.csv`) are read-only for
`base.group_user` and full-CRUD for `base.group_system` on every model this
module owns — the public API controllers bypass this via `.sudo()`, with
the controllers' own allow-list serialization acting as the actual security
boundary for public/portal data, not the ACL rows themselves.

## 7. GDPR/KVKK

Since VARS trades in Turkey and Europe, both GDPR and KVKK apply to any
personal data this module writes (`crm.lead`, `res.partner`):
- Lead-capture consent (checkbox, validated) is the frontend's
  responsibility to collect and pass through — this module doesn't enforce
  consent itself today.
- Data-erasure requests against `crm.lead`/`res.partner` records are
  handled as standard Odoo data-erasure procedure, not a bespoke endpoint.
