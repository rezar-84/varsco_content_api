# Decisions — varsco.com Replatform

Running architecture decision record (ADR) log for the replatform from Odoo-rendered `varsco.com` to the headless Astro + Odoo architecture in `architecture.md`. Format follows `midvex_marketplace_foundry`'s convention: Status, Decision, Reason.

## ADR-001: Headless replatform, Odoo stays system of record

### Status
Accepted — 2026-07-16

### Decision
Odoo 19 stops rendering public pages and becomes a pure backend + content source, reachable only via `varsco_content_api`. An Astro frontend owns all public presentation. This was already the direction in `CLAUDE.md`/`architecture.md`; this ADR records it as the formal starting point for the migration work now that a real current-state inventory exists (`migration/url-inventory.md`).

### Reason
Better SEO tooling and control (Astro SSG/SSR vs. Odoo's website renderer), a reusable agency template (`architecture.md` §7), and — per user direction — better translation/localization tooling than Odoo's native offering allows (see ADR-004).

## ADR-002: Drop the transactional shop; catalog-only with quote CTA

### Status
Accepted — 2026-07-16. **Amended 2026-07-17:** the shop is *deferred*, not permanently removed. VARS plans to sell online again in a later phase, together with user accounts/dashboards and custom operations-module panels (see `product/roadmap.md` Phase 8). Consequences of the amendment:
- The replatform/cutover scope is unchanged — the new site launches catalog+quote only, and the `/shop/*` 301s ship as planned. When commerce returns, the new shop either claims fresh URLs or re-claims `/shop/*` (reversing a 301 later is routine; the redirects are correct for the no-checkout period).
- `distance-sales-agreement` is **kept live verbatim** — it will be required again when selling resumes, so the legal question is moot. Sprint 0 blocker 2 resolved.
- Iyzico credentials are **kept**, not deactivated at cutover — they'll be reused. The `security.md` cutover-deactivation item is withdrawn; the keys just need to stay properly stored.
- The future commerce phase will need an authenticated API surface (cart, checkout, user accounts) — that's a versioned extension of the content API contract or a separate authenticated API, designed when that phase starts, not now. The current read-only contract stays as-is until then.

### Decision
The live site's `/shop/*` e-commerce (cart, checkout, Iyzico payment) is **not** rebuilt. The `/products/*` informational catalog — which already exists as a separate section on the live site — becomes the sole product surface, backed by a "request a quote" CTA into the existing CRM lead flow (`architecture.md` §3, `agent-playbooks.md` P4). Every `/shop/*` URL still gets a 301 to its nearest `/products/*` equivalent (`migration/url-inventory.md` §3) — descoping the feature does not mean 404ing its URLs.

### Reason
User decision, given the significantly larger and higher-risk scope of rebuilding real payment/checkout (PCI posture, `midvex_o` payment integration, guardrail territory per `CLAUDE.md` §6) versus the site's actual business model, which is lead-driven B2B (confirmed by the existing CRM lead architecture already documented before this ADR).

### Consequences
- `distance-sales-agreement` (Turkish distance-selling legal page, tied to online purchase) may no longer be legally required — **flagged for VARS/legal confirmation**, not decided here (`CLAUDE.md` §7: never fabricate or unilaterally retire legal text).
- 8 of 21 shop URLs have no clean 1:1 target in the current `/products/*` taxonomy (`migration/url-inventory.md` §3b/3d) — this is a product-catalog gap, not a redirect-logic gap, and needs a human with product/SKU knowledge before the redirect map is finalized.
- The content API contract (`architecture.md` §5) stays read-only-plus-one-lead-endpoint; no cart/checkout/payment endpoints are added.

## ADR-003: Locale scope and URL scheme — match the live site exactly

### Status
Accepted — 2026-07-16

### Decision
Support all 7 locales currently live (confirmed via `hreflang` on `varsco.com`): `en` (default, **unprefixed**, `x-default`), `ar`, `de`, `ja`, `ko`, `ru`, `tr` (**prefixed** `/tr/...`). The new site replicates this exact scheme — not the "default `tr`, plus `en`" assumption previously written into `architecture.md` §2/§4, and not a reduced locale set.

### Reason
The current scheme is already the state search engines have indexed and ranked. Changing the default locale, the prefix pattern, or dropping locales would force a second, unrelated wave of redirects/hreflang churn on top of the shop descope — unnecessary SEO risk for no user-facing benefit. Matching it exactly means zero hreflang disruption for 5 of the 7 locale variants and the default.

### Consequences
- `architecture.md` needs correcting (currently says "Default `tr`, plus `en`").
- The i18n solution chosen in ADR-004 must support this asymmetric scheme (one unprefixed default locale, six prefixed locales, one of which uses a full locale code `ko_KR` rather than a bare language code) — not just a simple two-locale case.

## ADR-004: Translation/i18n tooling — Tolgee, self-hosted, Odoo stays the served source of truth

### Status
**Superseded by ADR-005** — 2026-07-17. Tolgee self-hosted is free but still means operating another service; the user prefers no extra tools. Kept below for the research record.

### Original status
Accepted — 2026-07-16

### Decision
Use **Tolgee** (open-source, self-hostable) as the translation *workflow* tool for all non-default-locale content. Odoo's native `ir.translation` / website-builder per-field translation UI is not used at all. Integration pattern:

```
Odoo (canonical default-locale content: en, per ADR-003)
   │  on publish/update — webhook or scheduled job
   ▼
Tolgee (translation workspace: in-context editing, glossary, BYOK MT first drafts,
         human/reviewer workflow for the 6 non-default locales)
   │  CLI/REST pull — CI job or scheduled sync
   ▼
Odoo per-locale custom fields (plain fields per active language, NOT ir.translation)
   │
   ▼
varsco_content_api  →  Astro frontend  (unchanged contract, architecture.md §5)
```

Translated strings land back in Odoo as ordinary custom fields (one per active locale) rather than through `ir.translation`. Odoo therefore remains the **only** data source the frontend talks to — the content API contract in `architecture.md` §5 does not change shape, and `CLAUDE.md` §2.4 ("Odoo owns the data") holds for translated content too, not just default-locale content. Tolgee is a workflow tool sitting *before* Odoo in the pipeline, not a second runtime data source.

For UI chrome strings (buttons, nav labels, form copy — not Odoo-sourced content), Tolgee's CLI export produces the locale JSON files consumed directly by Astro's i18n layer at build time; these never touch Odoo, matching how `architecture.md` §2 already separates "content" (Odoo) from "UI chrome" (frontend locale files).

In-context editing (Tolgee's standout feature for a small in-house/agency team without a dedicated localization department) is enabled only against staging/dev deployments — the Tolgee JS snippet is excluded from the production bundle, keeping the performance budget in `quality-assurance.md` §4 intact.

### Reason
- **Solves the stated pain point** (Odoo's native translation UI) without adding a second served data source — the architecture's single-API-contract principle survives intact.
- **Self-hostable for free**, fitting the existing Hetzner-hosted infra (README "Owner" section) and the agency-template reuse goal (`architecture.md` §7) — no new per-client SaaS translation-tool cost baked into the template.
- **Glossary support** matters here: the content is domain-technical (artemia/hatchery/aquaculture terminology across 7 languages) where consistent, controlled terminology beats raw MT quality.
- **BYOK machine translation** (OpenAI/Azure/Anthropic/Google AI, confirmed current as of the 2026 research pass) gives fast first-draft coverage for new/updated content across all 6 non-default locales, with human review before it's pulled back into Odoo.
- Evaluated and rejected: **Crowdin** (best for community/crowdsourced OSS translation — wrong shape for an internally managed B2B site); **Lokalise** (strong professional-translator/reviewer workflow but SaaS-only, worse fit for the agency-template cost goal); **Weblate** (mature and git-native, a reasonable self-hosted alternative, but its editing UX and Astro/JS ecosystem integration are weaker than Tolgee's for a marketing-content-heavy, non-software-string use case) — kept as the fallback option if Tolgee's self-hosted operational burden proves too high in practice.

### Consequences
- Adds one more self-hosted service to operate (`infrastructure.md`) alongside Odoo — DevOps owns provisioning, backup, and the sync job's reliability.
- The Odoo-side custom per-locale fields need modeling per content type (`data-model.md`) — this is new Odoo model/field work, not just a frontend concern.
- The publish→Tolgee→pull-back sync job is a new integration surface requiring its own tests (`tdd.md` conventions apply: contract test on the sync payload, a11y/build gates unaffected).

### Sources consulted (2026-07-16)
- [i18next: Translation Management Systems overview](https://www.i18next.com/overview/translation-management-systems)
- [IntlPull: Open-Source TMS Comparison 2026 — Weblate vs Tolgee vs Pontoon](https://intlpull.com/blog/open-source-tms-comparison-2026)
- [IntlPull: Top 10 Localization Tools 2026](https://intlpull.com/blog/top-10-localization-tools-tms-comparison-2026)
- [Tolgee: Self-hosted pricing](https://tolgee.io/pricing/self-hosted)
- [Tolgee: In-context translation](https://tolgee.io/features/in-context)
- [Tolgee: REST API](https://tolgee.io/apps-integrations/rest-api)
- [Tolgee GitHub — tolgee-platform](https://github.com/tolgee/tolgee-platform)

## ADR-005: AI-assisted translation pipeline — no external TMS (supersedes ADR-004)

### Status
Accepted — 2026-07-17

### Decision
Translations are produced by an **AI translation job** (Claude API) operating directly on the `varsco.content.*.i18n` records in Odoo — no Tolgee, no external TMS, no new self-hosted service.

Pipeline:

```
Odoo default-locale (en) content  — canonical source
   │  cron / agent-run job detects missing or stale translations
   │  (staleness = hash of the source fields stored on each i18n record)
   ▼
Claude API translation, with a maintained per-locale domain glossary
(artemia/hatchery/aquaculture terminology) embedded in the prompt
   │
   ▼
i18n records written with review_status = "ai_draft"
   │  human reviewer flips to "reviewed" in an Odoo list view (per locale)
   ▼
Servability: only "reviewed" translations are served (extends the existing
servability rule — an ai_draft locale 404s, same as an incomplete one)
```

Hard limits:
- **Legal pages are never AI-translated into a live locale** — human/professional translation only (`CLAUDE.md` §7).
- Review is per-locale so native speakers can approve independently.
- The review gate implements `CLAUDE.md` §6: AI-generated content never goes live unreviewed.

### Reason
- User preference: no extra tools/services. Tolgee self-hosted is license-free but still a service to run, back up, and secure.
- Translation of existing approved content is *grounded* generation — much lower risk than free-form AI content, and the review-status gate covers the rest.
- Volume is small (~70 content items × 6 non-default locales); a TMS's workflow machinery isn't warranted at this scale.
- What's lost vs. Tolgee — in-context editing and translation memory — isn't worth an extra operating surface here. Revisit only if content volume or translator headcount grows substantially.

### Consequences
- `varsco.content.page.i18n` (and future i18n models) gain `review_status` and `source_hash` fields; the servability rule extends to require `reviewed` (backlogged).
- The glossary is maintained as data in the repo (per-locale term tables) — a business asset VARS should review, not invent-and-forget.
- `infrastructure.md`'s Tolgee service, backup, and secret rows are void; the only new secret is the Claude API key for the translation job, held server-side in Odoo/cron env.

## ADR-006: Structured public content; Astro exclusively owns presentation

### Status
Accepted — 2026-07-18

### Decision
The pre-launch `/api/v1` contract is corrected in place. Odoo page-builder/QWeb
HTML is migration input only and is never a public layout contract. Non-legal
pages expose validated, presentation-neutral blocks; Astro alone chooses the
HTML, layout, styling, responsive behavior, and interaction design.

Long-form editorial content may use sanitized semantic HTML limited to prose
elements. Odoo classes, inline styles, snippets, grids, buttons, scripts, forms,
and QWeb attributes are forbidden. Legal bodies remain verbatim and are rendered
inside an isolated typography surface without AI rewriting.

The public catalog is backed by curated `varsco.catalog.item` records. A catalog
item may link to one or more Odoo products for a later commerce release, but the
public catalog does not expose raw `product.template` records. Public pages stay
static and cacheable; publishing reviewed Odoo content triggers a debounced
Cloudflare Pages rebuild. The initial launch includes catalog + quote only.

### Reason
The first migration retained Odoo layout markup in 1,063 of 1,522 exported
sections. Rendering those values with `set:html` reproduced Odoo's visual system
inside Astro and contradicted ADR-001's layer boundary. The production replica
also has 22 informational portfolio pages but only 10 website-published products,
so neither raw page HTML nor raw product records form a complete public catalog.

### Consequences
- Existing pre-launch page-section fixtures, models, importers, and Astro
  components are migrated together; no compatibility version is retained.
- AI-assisted conversion creates drafts only. Every page/locale requires human
  approval before serving, and unresolved product relationships remain explicit.
- Cart, checkout, accounts, dashboards, and customs portal UI remain Phase 8 and
  will use a separately guarded authenticated API/BFF rather than public v1.

## ADR-007: Astro frontend discontinued; repo scope narrows to the Odoo middleware/API module; CMS content layer archived

### Status
Accepted — 2026-07-30

### Decision
The Astro frontend built in this repo (`apps/web`) is discontinued and
deleted (full history retained in git). Public presentation now lives in a
separately-developed frontend, `aqua-bloom-portal` (TanStack Start),
maintained in its own repository. This repository's scope narrows to:
**a secure Odoo 19 middleware/API module (`varsco_content_api`) that an
external frontend calls for authentication, CRM lead capture, catalog
browsing, and checkout.**

The content-management layer built to feed the Astro frontend —
`varsco.content.page`/`.section`, blog posts/categories, the navigation
menu, and the redirect map (ADR-006), along with the one-time migration
tooling that seeded it from the legacy `varsco.com` site — is **archived,
not deleted**. It now lives in `archive/odoo-addons/varsco_content_cms/`
(a separate Odoo addon, `installable: False`, depending on
`varsco_content_api`) and `archive/tools-migration/` /
`archive/migration-data/`, with full git history preserved. See
`archive/README.md` for what's there and how to reactivate any of it.

This ADR also formally **supersedes ADR-002's closing line** ("no
cart/checkout/payment endpoints are added" to the content API contract).
That constraint was written for the catalog-only, quote-CTA-only Astro
launch scope. It no longer holds: `checkout.py` (`POST /api/v1/store/checkout`)
and the portal auth/orders/profile endpoints (`portal.py`) already exist in
this module, built directly against `aqua-bloom-portal`'s own API
specification (its `doc/odoo_api_spec.md`). The rest of ADR-002 — that the
live `/shop/*` Odoo-rendered shop itself was not rebuilt, and its redirect
disposition — is historical fact about the migration and stands unchanged.

### Reason
Presentation and product/frontend direction moved to a separate team/repo
building `aqua-bloom-portal` independently. That project's own SDLC docs
(`doc/handoff.md`, `doc/odoo_api_spec.md`) explicitly designate this repo's
`varsco_content_api` as the Odoo-side implementation target for new routes
and state new Odoo routes should not be added inside the portal repo. Given
that, maintaining a second, now-unused frontend and its content-management
layer in this repo added no value and diverging documentation (`architecture.md`,
`product/roadmap.md`, etc. described a target that no longer matched
reality) actively misled future work. Archiving rather than deleting the
CMS layer preserves the option to reuse it (e.g. if a future frontend wants
managed marketing pages) without it cluttering the active surface area.

### Consequences
- `docs/architecture.md`, `docs/data-model.md`, `docs/security.md`,
  `docs/infrastructure.md`, `docs/clean-code.md`, `docs/quality-assurance.md`,
  `docs/tdd.md`, `docs/sdlc.md`, `docs/agent-playbooks.md`, `CLAUDE.md`,
  `AGENTS.md`, and `README.md` were rewritten to describe the middleware-only
  scope; SEO/rendering/i18n-routing/frontend-build concerns are no longer
  this repo's responsibility.
- `docs/product/*` and `docs/migration/*` (the Astro replatform's product
  plan and cutover docs) moved to `archive/docs/` alongside the code —
  historical record of *why* earlier decisions were made, not a live plan.
- The `catalog.py` model's content-validation helpers
  (`_validate_plain_text`, `_validate_semantic_html`, `_validate_media`)
  were extracted from `content_page_section.py` into a new
  `models/content_validators.py` in the active module, since the catalog
  model needs them independently of the now-archived CMS models. The
  archived module imports them back from the active one.
- No behavior change to any live endpoint from this ADR alone — this is a
  repository re-scope and documentation pass, not a functional change.
