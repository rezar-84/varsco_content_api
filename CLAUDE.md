# CLAUDE.md — Agent Operating Manual

**You are an AI engineer on the `varsco_content_api` project.** This file is your contract. Read it fully before touching code. When this file and any other doc conflict, this file wins; when it and a human instruction conflict, the human wins — but tell them what rule you're breaking and why.

> Non-Claude agents (Lovable, etc.): `AGENTS.md` points here. Same rules apply.

---

## 1. Mission & context

This repository is a **secure Odoo 19 API/middleware module** (`varsco_content_api`) for VARS Aquaculture, an artemia importer/distributor. **Odoo 19 is the backend and single source of truth.** Public presentation lives in a separate, independently-maintained frontend repository (currently `aqua-bloom-portal`) — this repo does not render pages, own SEO, or ship UI. Its job is to give that frontend (or any future one) secure, allow-listed access to Odoo for **authentication, CRM lead capture, catalog browsing, and checkout**. Leads flow into **Odoo CRM**.

Two things are always true and shape every decision:

1. **This is the security boundary.** Every endpoint here decides what an external, less-trusted frontend is allowed to read or write in Odoo. When unsure whether a field/action is safe to expose, assume it isn't and check `docs/security.md`.
2. **This is a template, not a one-off.** Prefer config- and data-driven solutions over hardcoding. Anything varsco-specific that a future client would change (locale list, catalog structure) belongs in config or Odoo data — never inline in a controller.

Read `docs/architecture.md` before writing any code that crosses the `/api/v1` contract boundary.

> This module was originally developed inside a monorepo (`varsco_front`) that also built an Astro frontend and a content-management layer (pages/blog/menu/redirects) for it. Both are gone from active development — the frontend was deleted, the CMS layer archived in `varsco_front`'s `archive/` (see `docs/decisions.md` ADR-007). This repo carries forward only the active middleware module; the archived material and full pre-pivot history live in `varsco_front`, not here. Don't resurrect either without a human decision.

## 2. Golden rules (non-negotiable)

1. **Test first.** No production code without a failing test that motivates it. See `docs/tdd.md`. If a change is genuinely untestable, say so and get human sign-off before proceeding.
2. **Small, reversible steps.** One logical change per commit, one concern per PR. If a task needs more than ~400 changed lines, stop and propose a split.
3. **Never break the `/api/v1` contract.** It's a shared interface with an external frontend repo — additive changes are fine, breaking changes need a version bump and human sign-off (`docs/architecture.md` §5).
4. **Odoo owns the data. The frontend owns presentation.** Never duplicate business logic (pricing, lead rules) in this module beyond what a write endpoint must validate server-side. Fetch/validate, don't reimplement.
5. **Field and action discipline.** Public read endpoints expose only explicit allow-listed fields — never cost/margin/internal data. Write endpoints exist only for the deliberate, tested set this module already implements (leads, checkout, portal auth/orders/profile) — never add a new write path without going through §6.
6. **Secrets never touch the repo.** API keys, Odoo credentials, the S2S write token live in environment/secret stores only. If you find one committed, stop and flag it.
7. **Respect the existing modules.** `midvex_schema_manager` already emits JSON-LD (used only if/when this repo serves content again). Extend it; don't fork or reinvent it.
8. **When blocked or ambiguous, ask — don't guess.** A wrong assumption that reaches production costs more than a question. See §7.

## 3. Tech stack & conventions (quick reference)

| Concern | Decision |
|---------|----------|
| Backend | Odoo 19, Python 3.12, standard Odoo ORM & controllers |
| API module | `varsco_content_api` — `@http.route` controllers, `type="http"`, mixed `auth="public"`/token/`auth="user"` per endpoint (`docs/architecture.md` §2) |
| Tests | Odoo test framework (`TransactionCase`), run against a real Odoo instance (`docs/infrastructure.md` §2–3) |
| Lint/format | Ruff + Black (Python) |
| Deploy | Odoo module install/upgrade behind a subdomain; no separate build/deploy pipeline in this repo |

The external frontend's own stack (TanStack Start, its BFF layer, its own lint/test/deploy pipeline) is out of scope for this repo — see its own docs if you need that context.

## 4. The loop you run for every task

```
1. UNDERSTAND  → restate the task, find/write the playbook, list acceptance criteria
2. RED         → write the smallest failing test that expresses the requirement
3. GREEN       → write the least code that makes it pass
4. REFACTOR    → clean per docs/clean-code.md; tests stay green
5. VERIFY      → run the full local gate (lint, tests, module install)
6. SELF-REVIEW → run the PR checklist in docs/quality-assurance.md against your own diff
7. HANDOFF     → open PR with the template; summarize what/why/how-tested
```

Never skip 2 to "save time." Never mark done before 5 and 6 both pass. Details in `docs/tdd.md` and `docs/sdlc.md`.

## 5. Definition of Done (a task is NOT done until all are true)

- [ ] Acceptance criteria met and demonstrated by tests.
- [ ] All new behavior covered by tests at the right level of the pyramid.
- [ ] `lint` and `test` pass locally; the module installs/upgrades cleanly.
- [ ] No `/api/v1` contract regression for touched endpoints.
- [ ] No hardcoded strings, locales, or varsco-specific values that should be config/data.
- [ ] No secrets, no `print` debug noise, no commented-out code left behind.
- [ ] PR description explains **what changed, why, and how it was tested**.
- [ ] Docs/playbooks updated if the change alters how future work is done.

## 6. Guardrails (things that require a human in the loop)

Stop and get explicit approval before:

- Changing the **`/api/v1` contract** (`docs/architecture.md` §5) — it's a shared interface with a separate frontend repo.
- Touching **CRM lead creation**, email routing (`crm@`/`leads@`), or anything that could drop/duplicate a real sales lead.
- Touching **checkout** (`checkout.py`) — creates real `sale.order`s.
- Modifying **Odoo data models** with existing records (migration risk).
- Anything affecting **secrets, auth, deliverability (SPF/DKIM/DMARC), or TLS**.
- Adding a **new third-party dependency** (supply-chain + license review).
- Reactivating the archived CMS layer or migration tooling — that material lives in the `varsco_front` repo's `archive/`, not here; confirm the need first and see that repo's `archive/README.md`.

## 7. When to ask vs. proceed

**Proceed** when: the task is well-specified, a playbook exists, and the change is inside one layer with tests.

**Ask first** when: the requirement is ambiguous, two reasonable designs exist with different trade-offs, the change crosses a guardrail in §6, or you'd have to invent business rules (pricing logic, lead-routing, legal/shipping copy). State the options and your recommendation; don't silently pick.

**Never** fabricate: product specs, prices, artemia hatching/dosing figures, shipping/customs terms, or legal text. These are business facts owned by VARS. If you need one and don't have it, ask.

## 8. AI assistant feature (currently out of scope)

No AI assistant service exists in this repo or the current frontend today. If one is ever built, it must follow these rules: answer only from grounded context fetched via this module's read endpoints (retrieval-augmented, not free-form); refuse or defer on anything it can't ground (exact pricing, binding shipping/customs commitments) and offer a sales handoff; create a `crm.lead` on genuine intent only via this module's authenticated endpoint, never write to Odoo directly from a browser; ship with an eval set and block release on grounding/refusal regressions.

## 9. Pointers

- System design & API contract → `docs/architecture.md`
- Process, git, environments, releases → `docs/sdlc.md`
- Testing → `docs/tdd.md`
- Code style → `docs/clean-code.md`
- Gates, CI, checklists → `docs/quality-assurance.md`
- Task recipes → `docs/agent-playbooks.md`
- Architecture decisions (ADR log) → `docs/decisions.md`
- Session-by-session handoff → `docs/handoff-log.md` (start one here — this repo's history begins at the migration from `varsco_front`)
- Active data model → `docs/data-model.md`
- Security → `docs/security.md`
- DevOps topology & local test environment → `docs/infrastructure.md`
- Pre-pivot history and the archived CMS/frontend layer → the `varsco_front` repo (its `archive/README.md`)
- The external frontend's own contract expectations → its `doc/` suite in its own repo (currently `aqua-bloom-portal`), read-only reference — this repo doesn't maintain it

**If you read nothing else: test first, keep steps small, never break the `/api/v1` contract, don't invent business facts, and ask when unsure.**
