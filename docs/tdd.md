# Test-Driven Development (TDD)

Tests are how we let AI agents move fast without breaking things. A test written *before* the code turns a vague requirement into an executable spec, and the green bar is objective evidence the agent actually delivered it. **No production code is written without a failing test that motivates it.**

## 1. The loop (red → green → refactor)

1. **Red** — write the smallest test that expresses the next slice of the requirement. Run it. Watch it fail *for the right reason* (a failing assertion, not an import error). A test that passes before you wrote the code tests nothing.
2. **Green** — write the least code that makes it pass. Resist gold-plating; the next test drives the next feature.
3. **Refactor** — with the safety net green, clean the code and the test per `clean-code.md`. Re-run. Still green.
4. Repeat. Commit at green.

If you can't figure out how to test a requirement, you don't yet understand the requirement — that's a signal to clarify, not to skip the test.

## 2. The test pyramid (where each kind of test lives)

```
        ▲  few, slow, high-confidence
 Integ. │  API contract tests — real Odoo instance (infrastructure.md §3)
        │
  Unit  │  many, fast — Odoo model methods, controller helpers, pure functions
        ▼
```

**Default to the lowest level that can catch the bug.** Push logic down into pure, unit-testable model/service methods so most coverage is fast unit tests; reserve full-instance integration tests for the handful of end-to-end flows that must never break (lead creation, checkout, portal auth).

## 3. Testing `varsco_content_api` (contract + integration)

- **Contract tests**: every endpoint's response matches the documented schema in `architecture.md` §5 (shape, required fields, envelope). The contract can't silently drift.
- **Field-discipline tests**: assert forbidden fields (cost, margin, internal notes, PII) are **never** present in any public response. This is a security test — it must exist for each endpoint, especially `products.py`'s `_public_commerce_fields()`.
- **Auth tests**: public read endpoints reject writes; `leads.py` rejects unauthenticated and malformed requests; `checkout.py`/`portal.py` reject unauthenticated sessions and cross-partner access.
- **Integration**: run inside Odoo's test framework (`TransactionCase`) against seeded records; verify locale handling and 404 behavior.
- **Lead creation**: `POST /api/v1/leads` creates exactly one `crm.lead` with correct fields, source, and locale where applicable; duplicate/spam handling behaves; the notification pipeline is triggered. Test the failure paths too (bad payload → no partial lead).
- **Checkout**: every line item is re-validated against `item_type == "purchasable_now"` and live stock — test that a client sending a non-purchasable or out-of-stock line is rejected, not silently adjusted.

## 4. Coverage & quality of tests

- Target **≥ 80%** line coverage on `varsco_content_api`; **100%** on the lead-creation path, the checkout-validation path, and the API field-discipline checks — those are money and privacy.
- Coverage is a floor, not a goal. A test must *assert behavior*; a test that executes code without meaningful assertions is worse than none (false confidence).
- Test behavior, not implementation. Don't assert private internals; assert observable outputs. Refactors shouldn't require rewriting good tests.
- One reason to fail per test where practical. Clear names: `test_checkout_rejects_informational_item`, not `test_checkout`.
- Deterministic. No reliance on real network or wall-clock in unit/contract tests.

## 5. Regression discipline

Every bug fixed gets a test that fails before the fix and passes after. Every production incident with a code cause gets a regression test. The suite only grows; we don't delete tests to make CI pass — we fix the code or, with sign-off, the outdated spec.

## 6. Agent-specific TDD notes

- Show your red before your green: in the PR/handoff, note that the test failed first and why. This proves the test has teeth.
- Don't write the test and the implementation in one undifferentiated blob — the discipline is the point.
- If a human asks for "just a quick change," the quick change still gets a test. Speed comes from small scope, not from skipping the net.

## 7. AI assistant evals (currently out of scope)

`CLAUDE.md` §8 describes eval requirements for an on-site AI assistant. No
such service currently exists in this repo or `aqua-bloom-portal` — this
section is a placeholder for if/when one is built, not an active gate.
