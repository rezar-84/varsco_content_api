{
    "name": "Varsco Content API",
    "summary": "Secure middleware API between Odoo and an external frontend",
    "description": """
Middleware/API module under /api/v1 giving an external frontend (currently
aqua-bloom-portal) secure access to Odoo: a public curated product catalog,
server-to-server CRM lead intake, session-authenticated customer-portal
auth/orders/profile, and checkout. Generic and config-driven so it is
reusable across client Odoo instances (agency-template goal).

A separate, archived module (varsco_content_cms, installable=False) holds
the page/blog/menu/redirect content system built for a now-discontinued
Astro frontend — not part of this module's active contract.
""",
    "version": "19.0.1.12.0",
    "category": "Website",
    "license": "LGPL-3",
    "author": "Midvex",
    "website": "https://midvex.com",
    "depends": [
        "product",
        "web",
        "sale",
        "stock",
        "crm",
        "portal",
        "website_sale",
        "website_sale_wishlist",
        "website_sale_stock",
        "midvex_sale_payment_link",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/content_locales.xml",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
    "application": False,
}
