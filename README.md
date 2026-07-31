# varsco_content_api

Secure Odoo 19 API/middleware addon for **varsco.com** (VARS Aquaculture — artemia import & distribution). **Odoo 19 is the backend/source of truth**; this addon is the only sanctioned way an external frontend talks to it.

This repository **is** the Odoo addon — the repo root is the module's technical name, so it can be cloned directly into an Odoo `addons_path` directory and installed/updated via the web interface (Apps → Update Apps List → Install), no extra nesting or build step required.

This module is a **reference implementation** for a reusable Midvex agency template: a new client site is "point a frontend at a new Odoo instance running this addon," not a rewrite.

Public presentation lives in a **separate repository** (currently `aqua-bloom-portal`) that isn't maintained from here — see `CLAUDE.md` §1 and `docs/decisions.md` ADR-007 for how this module's scope narrowed to the API layer.

---

## What this is

| Layer | Tech | Responsibility |
|-------|------|----------------|
| API | This addon (`varsco_content_api`) | Public catalog reads, S2S CRM lead intake, session-authenticated portal auth/orders/profile, checkout |
| Backend | **Odoo 19** | CRM, product & pricing data, catalog content |
| Frontend | *(separate repo)* | Public site — not part of this repository |

Full picture: [`docs/architecture.md`](docs/architecture.md).

## Repository layout

```
varsco_content_api/
├── CLAUDE.md                 # Agent operating manual — READ FIRST (auto-loaded by Claude Code)
├── AGENTS.md                 # Same instructions for non-Claude agents
├── README.md                 # This file
├── __manifest__.py           # Odoo module manifest
├── controllers/               # @http.route endpoints (base, products, leads, portal, checkout)
├── models/                    # varsco.content.locale, varsco.catalog.* + validators
├── security/                  # ir.model.access.csv
├── data/                      # seed data (locales)
├── tests/                     # Odoo TransactionCase/HttpCase tests
└── docs/
    ├── architecture.md       # System design & the /api/v1 contract
    ├── sdlc.md               # Lifecycle, git flow, environments, Definition of Done
    ├── tdd.md                # Test-driven workflow, test pyramid, per-layer testing
    ├── clean-code.md         # Coding standards (Python/Odoo)
    ├── quality-assurance.md  # QA gates, CI, review & sign-off checklists
    ├── agent-playbooks.md    # Step-by-step recipes agents follow for common tasks
    ├── decisions.md          # ADR log
    ├── handoff-log.md        # Running session-by-session handoff log
    ├── data-model.md         # Active content-type field model (locale, catalog)
    ├── security.md           # Credential surfaces, session posture, record rules
    └── infrastructure.md     # DevOps topology, local test environment, backup/rollback
```

Pre-pivot history (the discontinued Astro frontend and its CMS content layer) lives in the separate `varsco_front` repo, not here — see that repo's `archive/README.md` if you need it.

## How the docs fit together

- **[CLAUDE.md](CLAUDE.md)** — the contract every agent follows. Golden rules, guardrails, the TDD loop, when to stop and ask. Start here.
- **[docs/sdlc.md](docs/sdlc.md)** — *how work moves* from idea to production.
- **[docs/tdd.md](docs/tdd.md)** — *how we prove code works* before it's "done."
- **[docs/clean-code.md](docs/clean-code.md)** — *how code should look.*
- **[docs/quality-assurance.md](docs/quality-assurance.md)** — *the gates that block bad work from merging/shipping.*
- **[docs/agent-playbooks.md](docs/agent-playbooks.md)** — *recipes* for recurring tasks.
- **[docs/decisions.md](docs/decisions.md)** — *why* things are the way they are (ADR log). Read ADR-007 first if you're new to this repo.
- **[docs/handoff-log.md](docs/handoff-log.md)** — *what happened last*, session by session.

## Quickstart (humans) — deploying to a production Odoo host

```bash
# From the Odoo host's custom addons directory (the folder name must match
# the module's technical name for Odoo to find it):
git clone git@github.com:rezar-84/varsco_content_api.git varsco_content_api

# Then in the Odoo web interface: Apps → Update Apps List → search
# "Varsco Content API" → Install (or Upgrade, on subsequent deploys).
```

To pick up new commits on an already-installed instance: `git pull` inside that addons-path checkout, then Apps → Upgrade.

```bash
# Running the test suite locally (against a real Odoo instance — see
# docs/infrastructure.md §2-3 for known local-env pitfalls)
odoo -d odoo19_test_varsco -u varsco_content_api --test-enable --stop-after-init
```

## Quickstart (agents)

1. Read `CLAUDE.md` in full.
2. Read the doc(s) relevant to your task.
3. Find or write the matching playbook in `docs/agent-playbooks.md`.
4. Work the TDD loop. Do not mark a task done until every gate in `docs/quality-assurance.md` passes.

## Environments

| Env | Odoo | Purpose |
|-----|------|---------|
| local | `~/Development/odoo19-dev` | build & test |
| staging | staging Odoo | review & QA |
| production | Odoo behind `erp.varsco.com` | live |

## Owner

Midvex — [midvex.com](https://midvex.com). Backend/infra on Hetzner + Plesk; Odoo CRM lead capture via `crm@` / `leads@`.
