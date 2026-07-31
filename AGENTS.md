# AGENTS.md

This project's agent instructions live in **[`CLAUDE.md`](CLAUDE.md)** — read it in full before doing any work. It applies to every AI agent regardless of vendor (Claude Code, Lovable, or otherwise).

Then read the doc relevant to your task:

- `docs/architecture.md` — system design & the `/api/v1` contract
- `docs/sdlc.md` — lifecycle, git flow, Definition of Done
- `docs/tdd.md` — test-driven workflow
- `docs/clean-code.md` — coding standards
- `docs/quality-assurance.md` — the gates you must pass
- `docs/agent-playbooks.md` — step-by-step recipes
- `docs/decisions.md` — the ADR log; read ADR-007 before assuming this repo still builds a frontend
- `docs/handoff-log.md` — what happened last session; read before resuming work (this repo's log starts at its split from `varsco_front`)
- `docs/data-model.md` — the active models (`varsco.content.locale`, `varsco.catalog.*`)

This repo's root **is** the addon (technical name `varsco_content_api`) — clone it directly into an Odoo `addons_path` directory and install via the web interface. Pre-pivot history and the archived CMS/frontend layer live in the separate `varsco_front` repo, not here.

This repo is a **secure Odoo 19 API/middleware module**, not a frontend project. Public presentation lives in a separate, independently-maintained repository (currently `aqua-bloom-portal`) that calls this module's `/api/v1` endpoints for auth, CRM leads, catalog, and checkout — don't add frontend code or Odoo-rendered pages here.

The five things you can never do: skip writing a test first, break the `/api/v1` contract without a version bump + sign-off, invent business facts (prices, specs, shipping terms), commit a secret, or cross a §6 guardrail without a human. See `CLAUDE.md` for the rest.
