# Agent Playbooks

Repeatable recipes for the tasks that recur on this project. Each follows the loop in `CLAUDE.md` §4 (understand → red → green → refactor → verify → self-review → handoff). When you do a task with no playbook here and it's likely to recur, **add one** in the same PR.

Every playbook assumes the golden rules in `CLAUDE.md` §2 and ends at the Definition of Done in §5.

---

## P1 — Add a new public read endpoint

**Goal:** e.g. exposing a new catalog field or a new list filter.

1. Confirm the data is **safe to expose** (`architecture.md` §5 field discipline — not cost/margin/PII/internal). If unsure, ask.
2. Write the **contract test** and the **field-discipline test** first (red) — assert the response envelope and that forbidden fields never appear.
3. Add the endpoint/field via an explicit allow-list (never `read()` the whole record).
4. Additive change → same API version (`/api/v1`). Note it in the PR `Impact` section. A breaking change is a `CLAUDE.md` §6 guardrail — get sign-off first.

---

## P2 — Add a new authenticated write endpoint

**Goal:** e.g. a new portal action, or extending `checkout.py`/`leads.py`.

1. This is a `CLAUDE.md` §6 guardrail (touches CRM/data/auth) — confirm the exact write behavior with a human before coding.
2. Decide the auth model deliberately and write it down: `auth="public"` + bearer token (server-to-server, like `leads.py`) or `auth="user"` session-cookie (like `checkout.py`/`portal.py`) — never a new pattern without discussing it.
3. Write tests first (red): happy path, missing/invalid auth (401), malformed payload (400), and — for anything writing an Odoo record — that exactly one record is created/modified, with no partial writes on error.
4. Server-side re-validate everything the client claims (item type, ownership, stock) — never trust a client-supplied id or amount as authoritative. See `checkout.py` for the pattern.
5. 100% test coverage on the new write path (`tdd.md` §4).

---

## P3 — Touch the lead-capture flow (HIGH CARE)

This is money. `crm.lead` creation is a §6 guardrail — a human is in the loop.

1. Restate exactly what changes and confirm with a human before coding.
2. Write tests first, at multiple levels (red): `POST /api/v1/leads` creates **exactly one** `crm.lead`, correct fields/source; bad payload → **no** partial lead; the bearer-token check actually rejects a missing/wrong token.
3. Implement. Never write to Odoo directly from a browser — only the frontend's server holds the write token.
4. **Manual E2E on staging is mandatory:** submit a real test lead, confirm it lands in CRM, confirm the `crm@`/`leads@` notification is delivered, then clean up the test lead.
5. Confirm deliverability posture unchanged (SPF/DKIM/DMARC still aligned).
6. 100% test coverage on the lead path (`tdd.md` §4).

---

## P4 — Touch the checkout flow (HIGH CARE)

Creates real `sale.order`s. Also a §6 guardrail.

1. Restate exactly what changes and confirm with a human before coding.
2. Write tests first (red): only `item_type == "purchasable_now"` items pass; out-of-stock lines are rejected; price/currency on the resulting order matches the catalog item's current price; a bad payload creates no order at all.
3. Implement in `checkout.py`, re-validating every line server-side regardless of what the client sent.
4. **Manual E2E on staging is mandatory:** run a real checkout, confirm the resulting `sale.order`'s lines/pricing, then clean up the test order.
5. 100% test coverage on the checkout-validation path.

---

## P5 — Add a third-party dependency

1. §6 guardrail. Justify: what it does, why nothing in-repo or the Odoo platform already does it.
2. Check license (permissive), maintenance health, and security history.
3. Get sign-off before adding. Pin the version.

---

## P6 — Fix a bug

1. Reproduce it with a **failing test** that captures the defect (red). This is non-negotiable — the test proves the bug exists and that you fixed it.
2. Fix the code (green).
3. Refactor if the bug revealed a design weakness.
4. The regression test stays in the suite forever (`tdd.md` §5).

---

## P7 — Onboard a new client site (agency-template path)

varsco.com is the reference. A new client should be configuration, not a fork.

1. Stand up the client's Odoo instance + `varsco_content_api` (generic addon, config-driven).
2. Provide the client's locale list and catalog data as config/data — no addon code forks.
3. Point the client's own frontend (any stack, same pattern as `aqua-bloom-portal`) at the new instance's `/api/v1` base URL.
4. If anything **forces** an addon code change specific to one client, that's a design smell — stop and generalize it into config instead, then update this playbook.

---

## P8 — Prepare a release

1. Confirm all CI gates green on `main`.
2. Run the applicable staging manual checklists (`quality-assurance.md` §3).
3. Write the changelog entry and the **rollback step** for this release.
4. Validate any migration on a production-like copy.
5. Get human release sign-off (`quality-assurance.md` §5), promote, then run post-release verification (§6).

---

### Meta-playbook: when no playbook fits

1. Restate the task and its acceptance criteria; write a short design note if it crosses a boundary (`sdlc.md` §Design).
2. Identify which guardrails (`CLAUDE.md` §6) apply; get sign-off where needed.
3. Run the standard loop with test-first discipline.
4. Add a new playbook here so the next agent doesn't start from scratch.
