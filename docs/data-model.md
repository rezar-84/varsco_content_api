# Data Model — Active Middleware Models

Field-level shape of the Odoo models backing `varsco_content_api`'s active
contract (`architecture.md` §5): the public catalog and the locale registry
it's translated against. Auth/CRM/checkout endpoints (`leads.py`,
`checkout.py`, `portal.py`) read/write standard Odoo models (`crm.lead`,
`sale.order`, `res.partner`, `product.template`/`.product`) directly — those
aren't documented here since their shape is Odoo's own.

> The page/blog/menu/redirect content system that used to live alongside
> this catalog model is archived, not deleted — see
> `archive/docs/data-model-cms.md` and `archive/README.md`.

Translatable content is stored in a **per-locale child record**
(`varsco.catalog.item.i18n`: `item_id`, `locale_id`, ..., unique per
item+locale), not `title_{locale}`-style suffixed columns. Locales
themselves are data (`varsco.content.locale`), so a new client site changes
the locale list without schema changes (the template-reuse rule,
`architecture.md` §7). i18n records carry `review_status`
(`ai_draft`/`reviewed`) and a `source_hash` for staleness detection; only
`reviewed` translations are servable via `_is_servable(locale)`.

## `varsco.content.locale`

The active-locale registry — adding/removing a locale is a data change, not
a code change.

```text
code            # e.g. "en", "ar", "tr" — matches the API's {locale_code} path segment
url_prefix       # "" for the default/unprefixed locale, "/ar" etc. otherwise
is_default
sequence
```

## `varsco.catalog.category`

```text
slug
url_path
parent_id
sequence
published
```

Per-locale (`varsco.catalog.category.i18n`):
```text
name
summary
meta_title
meta_description
review_status     # ai_draft | reviewed
source_hash
```

`_is_servable(locale)`: `published` AND a `reviewed` translation with
non-empty `name`/`meta_title`/`meta_description`.

## `varsco.catalog.item`

The curated public merchandising layer — covers informational portfolio
entries and items linked to a transactional Odoo `product.template` without
exposing raw ERP records.

```text
slug
url_path
category_id
item_type               # informational | purchasable_later | purchasable_now
product_template_ids    # m2m to product.template; never exposed publicly as a relation —
                         # see _public_commerce_fields() below
sequence
published
quote_cta_enabled
```

Per-locale (`varsco.catalog.item.i18n`):
```text
name
eyebrow
summary
description_html    # sanitized semantic prose only (content_validators.py)
media                # JSON list of { url, alt, width?, height? }
specification_groups # JSON: [{ heading?, items: [{ label, value }] }]
meta_title
meta_description
review_status        # ai_draft | reviewed
source_hash
```

`_is_servable(locale)`: `published` AND `category_id._is_servable(locale)`
AND a `reviewed` translation with non-empty `name`/`meta_title`/`meta_description`.

**Commerce field discipline** (`_public_commerce_fields()`): only
`item_type == "purchasable_now"` items ever expose price/stock, and only
through this one allow-listed method — never `standard_price`/margin, never
a raw `read()`. Shape:
```text
{ product_id, amount, currency, available, qty_available }
```
`product_id` here is the one raw ERP id the public API ever returns, and
only for items that can actually be checked out — it's what
`POST /api/v1/store/checkout`'s `items[].product_id` expects back
(`checkout.py`; see `aqua-bloom-portal`'s `doc/odoo_api_spec.md` §2.4 for the
full checkout contract this satisfies).

## Duplicate-prevention / integrity rules

- `varsco.catalog.category.url_path` and `varsco.catalog.item.url_path` unique.
- `varsco.catalog.item.i18n` unique per `(item_id, locale_id)`; same for category i18n.
- Semantic HTML/plain-text/media fields are validated on write
  (`content_validators.py`) — layout markup, inline styles, scripts, and
  unsafe URL schemes are rejected, not just discouraged.
- `checkout.py` re-validates every checkout line against
  `item_type == "purchasable_now"` and live `qty_available` server-side —
  the frontend hiding "Add to Cart" for non-purchasable items is a UI
  convenience, not the security boundary.
