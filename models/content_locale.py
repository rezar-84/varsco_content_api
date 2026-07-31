from odoo import fields, models


class VarscoContentLocale(models.Model):
    """Active locale served by the content API.

    Locales are data, not code, so a new client site can change the locale
    list without touching this addon (architecture.md §7 template-reuse rule).
    The seed data for varsco.com carries the 7 live locales per ADR-003.
    """

    _name = "varsco.content.locale"
    _description = "Content API Locale"
    _order = "sequence, id"

    name = fields.Char(required=True)
    code = fields.Char(
        required=True,
        help="Locale code as used in API paths and hreflang, e.g. 'en' or 'ko_KR'.",
    )
    url_prefix = fields.Char(
        default="",
        help="Public URL path prefix, e.g. '/tr'. Empty for the default locale (ADR-003).",
    )
    is_default = fields.Boolean(default=False)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint("UNIQUE (code)", "Locale code must be unique.")
