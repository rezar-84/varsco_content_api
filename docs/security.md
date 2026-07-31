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

**Dormant** credential surface: Iyzico payment integration. Kept in Odoo's
secret storage as-is per prior VARS confirmation for a future commerce
phase — include it in any credential-rotation routine so it's healthy when
needed, but don't surface it anywhere new until that phase is scoped.

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
  (`REQUIRED_FIELDS` in `leads.py`).
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
  should reject cross-origin browser calls to `/api/v1/*` that don't come
  through that server-side proxy.

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
