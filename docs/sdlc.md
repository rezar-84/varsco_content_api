# Software Development Lifecycle (SDLC)

How work moves from idea to production. This process is designed for **AI agents doing the bulk of the work under human review**, so its emphasis is on small units, explicit acceptance criteria, and hard gates that catch mistakes before they ship.

## 1. Lifecycle overview

```
Discovery → Design → Plan → Build (TDD) → Review → QA → Release → Operate
     └──────────────────── feedback loops ────────────────────┘
```

Each phase has an entry condition and an exit artifact. No phase is skipped, but small tasks move through quickly.

### Discovery
Turn a request into a clear problem statement. Output: a short **task brief** — the user/business need, scope, and *acceptance criteria written as testable statements*. Agents draft this; a human confirms it before Build. Ambiguity is resolved here, not in code.

### Design
For anything crossing a layer boundary or touching the `/api/v1` contract, write a brief design note (a few paragraphs): approach, alternatives considered, impact on the API contract / data model, and any §6 guardrail it touches (`CLAUDE.md`). Small in-layer changes skip the note but still restate their approach in the PR.

### Plan
Break the task into small, independently testable units (≤ ~400 changed lines each). Identify or write the matching entry in `agent-playbooks.md`. Sequence so each unit leaves the build green.

### Build (TDD)
Run the loop in `CLAUDE.md` §4 / `tdd.md`. Every unit: red → green → refactor. Commit per logical step.

### Review
Open a PR using the template (§4). Self-review against the QA checklist first, then a human (or a second agent acting as reviewer) reviews. Reviews focus on correctness, contract stability, tests, and clean code — not style nits a linter already caught.

### QA
Automated gates run in CI (`quality-assurance.md`). The lead/checkout/portal flows are **always** manually verified end-to-end when touched — a dropped lead is a lost sale, and a checkout bug is a wrong order.

### Release
Merge to `main` triggers deploy to staging; promotion to production is a deliberate step (see §5). Tag releases; keep a changelog.

### Operate
Monitor Odoo error logs and `/api/v1/*` error rates, and lead-notification deliverability. Incidents get a short write-up and, where useful, a regression test so the same break can't recur.

## 2. Definition of Ready (a task may enter Build only if…)
- [ ] Problem statement and scope are clear.
- [ ] Acceptance criteria are written as testable statements.
- [ ] Design note exists (if it crosses a boundary or a guardrail).
- [ ] Dependencies and affected layers identified.
- [ ] Any needed business facts (prices, lead-routing rules, legal text) are supplied — not to be invented.

## 3. Definition of Done
The full checklist lives in `CLAUDE.md` §5. In short: acceptance criteria demonstrated by tests; all gates green; no API-contract regressions; no hardcoded client-specific values; no secrets or debug noise; PR explains what/why/how-tested; docs updated if process changed.

## 4. Git & PR workflow

**Branches**
- `main` — always deployable. Protected: no direct pushes; PR + green CI + review required.
- `feat/<short-slug>`, `fix/<short-slug>`, `chore/<short-slug>`, `docs/<short-slug>` — one concern each.

**Commits** — Conventional Commits: `type(scope): summary`.
Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`.
Example: `feat(api): validate checkout stock server-side`.
One logical change per commit. Tests belong in the same commit/PR as the code they cover.

**Pull request template**
```
## What
<one-paragraph summary of the change>

## Why
<the need / acceptance criteria it satisfies>

## How tested
<tests added; levels of the pyramid touched; manual QA if any>

## Impact
- API contract: <none | additive | breaking (needs sign-off)>
- Data/migration: <none | describe>
- Guardrails touched (CLAUDE.md §6): <none | describe + approval>

## Checklist
- [ ] Test-first; all gates pass locally
- [ ] No hardcoded client-specific values, no secrets
- [ ] Playbook/docs updated if process changed
```

**PR size** — small. A reviewer should hold the whole change in their head. Oversized PRs get split, not rubber-stamped.

## 5. Environments & releases

| Env | Trigger | Odoo |
|-----|---------|------|
| local | dev | `~/Development/odoo19-dev` (`infrastructure.md` §2–3) |
| staging | merge to `main` | staging Odoo |
| production | manual promotion + tag | production Odoo (`erp.varsco.com`) |

- **Migrations** (Odoo model changes) run on staging first with a production-like data copy; never auto-applied to production.
- **Rollback** — revert the release tag and reinstall the prior module version (`infrastructure.md` §6). Every release notes its rollback step.

## 6. Working agreements for agents

- Keep the build green. If you break it, fixing it is the top priority.
- Leave a trail: PRs and commits explain intent, not just mechanics.
- Prefer deleting to commenting-out. Version control is the history.
- If you discover the task is bigger or riskier than the brief assumed, stop and re-scope with a human rather than pushing on.
- Update the relevant doc/playbook in the same PR when your change alters how future work should be done.
