# Infrastructure — DevOps View

Topology and operational detail supporting `sdlc.md` §5 (environments/releases).
This repo now covers only the Odoo backend + `varsco_content_api` middleware —
the frontend (`aqua-bloom-portal`) has its own deploy topology in its own repo
and isn't documented here.

## 1. Hosting topology

```
External frontend (separate repo/deploy — not this repo's concern)
        │  HTTPS calls to /api/v1/*
        ▼
erp.varsco.com — Odoo 19 (Hetzner + Plesk)
   varsco_content_api (this module)
```

Odoo hosting (Hetzner + Plesk) is the existing setup per the README "Owner"
section — this document doesn't change it.

## 2. Environments (extends `sdlc.md` §5)

| Env | Odoo | Notes |
|---|---|---|
| local | `~/Development/odoo19-dev` (see its own `AGENTS.md`) | Database `odoo19_test_varsco` is the lightweight test target — see §3 below for a known registry-load gotcha |
| staging | staging Odoo | Same module install/test process as local |
| production | Odoo behind `erp.varsco.com` | |

## 3. Testing `varsco_content_api` locally — known pitfalls

Documented in `~/Development/odoo19-dev/AGENTS.md`, repeated here since it's
easy to hit and not obvious from the error:

- A fresh registry build can spuriously report this module's dependencies
  (`sale`/`stock`/`crm`/`portal`) as "not loaded" even though they're
  genuinely installed, silently skipping the whole module and 404ing every
  `/api/v1/*` route. Fix: a one-time `-u varsco_content_api --stop-after-init`
  pass per test database.
- Use `odoo19_test_varsco` (lightweight) as the test target, not `varsco_com`
  (the full production-scale dataset used for real content work) — don't
  write throwaway test data into the latter.
- `dbfilter` in that environment's `config/odoo.conf` must stay pinned to a
  single database — broadening it can cause Odoo to dispatch requests to the
  wrong matching database (looks like a 404, isn't).

## 4. Secrets & environment management

Per `CLAUDE.md` §6/`security.md` §1: all credentials live in Odoo's/Plesk's
own secret storage (`ir.config_parameter`) — never in the repo, never in a
client bundle. The frontend only ever holds these server-side, in its own
env/secret store:
- `varsco_content_api.write_token` — the S2S bearer token for `POST /api/v1/leads`.
- Odoo session cookie is native session infrastructure, not a separate secret to provision.

## 5. CI/CD

The gate pipeline is defined in `quality-assurance.md` §2 — this module's
tests run against a real Odoo instance (§3 above), not a mocked one; there
is no build/deploy step owned by this repo beyond the addon itself being
installed/upgraded on the Odoo host.

## 6. Backup & rollback

- **Odoo**: existing backup practice on the Hetzner/Plesk box, unchanged.
  Catalog/locale data (`data-model.md`) is part of the same Odoo database
  and covered by the same backup, no new backup surface.
- **Module rollback**: standard Odoo module upgrade/downgrade via
  `-u varsco_content_api`; no separate deploy artifact.
