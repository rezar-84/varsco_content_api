# Clean Code Standards

Code is read far more than written — and here it's also read by the *next agent*, who has none of your context. Optimize for the reader. These standards are enforced partly by tooling (lint/format/types) and partly by review.

## 1. Universal principles

- **Clarity over cleverness.** The obvious solution a tired reviewer understands beats the elegant one they have to decode.
- **Names carry the weight.** A well-named function needs few comments. Names say *what* and *why*; they don't abbreviate to save keystrokes. `retiredProductRedirect` > `rpr`.
- **Small units, one responsibility.** A function does one thing at one level of abstraction. If you narrate it and hit "and also," split it. Rough ceilings: functions ~30 lines, files ~300 — soft signals, not laws.
- **Comment the *why*, not the *what*.** The code shows what. Comments explain intent, trade-offs, non-obvious constraints, links to the reason. Delete commented-out code — that's what version control is for.
- **DRY, but not prematurely.** Extract a shared abstraction after the second or third real repetition, not on the first coincidental one. The wrong abstraction is costlier than duplication.
- **Fail loudly, handle deliberately.** No silent `catch`/`except: pass`. Validate at boundaries (API input, form input); trust internal callers. Errors carry enough context to debug.
- **Pure core, thin edges.** Push logic into pure, testable functions; keep I/O (HTTP, ORM, filesystem) in thin adapters. This is what makes the pyramid in `tdd.md` mostly unit tests.
- **No magic values.** Numbers and strings with meaning become named constants or config. Especially: no hardcoded URLs, locales, or varsco-specific values — those are config/data (see `CLAUDE.md` §1).
- **Consistency beats personal preference.** Match the surrounding code and the tooling config even if you'd do it differently.

## 2. Python / Odoo (`odoo/addons/*`)

- **PEP 8 + Ruff + Black**; type hints on public functions. Follow Odoo's own idioms — models, fields, `api.model`/`api.depends`, environment access — don't invent parallel patterns.
- Controllers stay thin: parse/validate input, call a service/model method, shape the response. Business logic lives in models or dedicated service methods, not in the `@http.route` handler — so it's unit-testable without HTTP.
- **Field allow-lists, always.** Public endpoints select explicit fields; never return whole records or expose forbidden fields (`architecture.md` §5). This is both a clean-code and a security rule.
- Respect ORM safety: no raw SQL for reads unless there's a measured reason; parameterize if you must. Never build queries by string concatenation from request input.
- Records and recordsets named for what they hold (`published_items`, not `recs`). Use `sudo()` sparingly and only with a comment explaining why it's safe.
- Migrations are explicit and reversible where possible; document data changes.
- Keep `varsco_content_api` generic and config-driven so it's reusable across client Odoo instances (agency-template goal).

## 3. API & interface design

- Design the contract from the *consumer's* need (the frontend calling `/api/v1`), not the database shape. The caller shouldn't have to know Odoo internals.
- Consistent envelope, consistent errors, explicit versioning (`architecture.md` §5). Additive changes only within a version.
- Validate all input at the boundary; return clear, structured errors — never leak stack traces or internal field names to the caller.

## 4. Security & privacy hygiene (non-negotiable)

- Secrets only in env/secret stores. Nothing sensitive in the repo, logs, or a public response.
- Treat all request input as hostile: validate, sanitize; the S2S write endpoints (`leads.py`, `checkout.py`) are the highest-risk surface — see `security.md`.
- Never log PII or full request bodies; log identifiers and outcomes.

## 5. What review will send back

- A function that does three things.
- A name that lies or abbreviates.
- A hardcoded string/URL/locale/price.
- A swallowed error or an empty catch.
- Logic in a controller that belongs in a testable model method.
- A public API field that shouldn't be public.
- New behavior with no test, or a test with no real assertion.
- A commented-out block "just in case."

Clean code isn't polish applied at the end — it's the state each green refactor step leaves the code in.
