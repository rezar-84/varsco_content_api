# Quality Assurance & Control

QA here is a set of **gates**, not a vibe. A change reaches production only by passing every automated gate in CI and every manual checklist that applies. Agents run these against their own work *before* asking for review; CI enforces them; a human signs off on release.

## 1. The gate model

```
Local (agent self-check) → CI (automated, blocking) → Staging QA (manual checklists) → Release sign-off
```

Any red gate blocks the merge or the release. Gates are not advisory.

## 2. CI pipeline (blocking — every PR)

Runs on every pull request; must be green to merge.

1. **Lint** — Ruff. Zero errors.
2. **Format** — Black. No diffs.
3. **Tests** — Odoo test framework (`odoo -d <db> -i varsco_content_api --test-enable --stop-after-init`, see `infrastructure.md` §3 for known local-env pitfalls). All pass.
4. **API contract tests** — responses match `architecture.md` §5; **field-discipline tests pass** (no forbidden fields leak — cost, margin, internal notes, partner PII).
5. **Build/install** — Odoo module installs and upgrades cleanly with `--test-enable`.
6. **Coverage** — meets thresholds in `tdd.md` §4 (≥80% logic; 100% on the lead-creation and checkout-validation paths, and on field-discipline serializers).
7. **Security scan** — dependency audit, secret scan on the diff. No high-severity issues, no committed secrets.

## 3. Manual QA checklists (staging, before promotion)

**Lead flow (mandatory whenever `leads.py` or its callers are touched — a dropped lead is a lost sale):**
- [ ] Submitting a lead payload creates exactly one `crm.lead` with correct fields, source, and any cart summary.
- [ ] The `crm@`/`leads@` notification fires and is delivered (deliverability intact: SPF/DKIM/DMARC aligned).
- [ ] Validation rejects bad input cleanly; no partial/duplicate leads on error or double-submit.
- [ ] The bearer-token check actually rejects a missing/wrong token (401), not just a happy-path pass.

**Checkout flow (mandatory whenever `checkout.py` is touched):**
- [ ] Only `item_type == "purchasable_now"` items can be checked out; every other type is rejected server-side even if a client sends it anyway.
- [ ] Stock is re-checked server-side; an out-of-stock line is rejected, not silently clamped.
- [ ] Price/currency on the resulting `sale.order` matches the catalog item's current `list_price`.

**Portal flow (mandatory whenever `portal.py` is touched):**
- [ ] `portal_orders`/`portal_profile_update` only ever return/modify the authenticated session's own `partner_id` — try a second account and confirm no cross-partner leakage.
- [ ] Login rejects bad credentials with 401, not a stack trace or a 500.

**Catalog reads (whenever `products.py`/`catalog.py` is touched):**
- [ ] `_public_commerce_fields()` never returns `standard_price`/margin — only `amount`/`currency`/`available`/`qty_available`, and only for `purchasable_now` items.
- [ ] Unpublished/unreviewed items and categories are absent from both list and detail responses.

## 4. Code review checklist (self-review first, then reviewer)

- [ ] Does it do what the acceptance criteria say, and no more?
- [ ] Tests exist at the right level and actually assert behavior (red-before-green shown).
- [ ] API contract stable (or version-bumped + signed off, `architecture.md` §5).
- [ ] No hardcoded client-specific values; no secrets; no debug noise (`print`); no dead code.
- [ ] Errors handled deliberately; input validated at the endpoint boundary.
- [ ] Logic testable (not buried in an `@http.route` handler).
- [ ] PR explains what/why/how-tested; docs/playbooks updated if process changed.

## 5. Release sign-off (production promotion)

A human confirms before promoting:
- [ ] All CI gates green on `main`.
- [ ] Staging manual QA checklists passed for the touched areas (§3).
- [ ] Rollback step documented (module downgrade/reinstall).
- [ ] Any data-model migration validated on a production-like data copy.
- [ ] Guardrail changes (`CLAUDE.md` §6) explicitly approved.

## 6. Post-release verification

Within a short window after promotion:
- [ ] Smoke-test live against the frontend: submit a real test lead (then clean it up), confirm a real catalog read, confirm portal login works.
- [ ] Confirm no spike in Odoo error logs or 401/500s on `/api/v1/*`.

## 7. When a gate fails

Fixing a red gate is the priority over new work. Never disable, skip, or weaken a gate to get a merge through — if a gate is wrong, fix the gate in its own PR with sign-off, and add a regression test so the real defect can't slip past next time.
