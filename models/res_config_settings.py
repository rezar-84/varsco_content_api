import secrets

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    varsco_content_api_write_token = fields.Char(
        string="Write Token",
        config_parameter="varsco_content_api.write_token",
        help="Bearer token the frontend's server (never its browser) sends "
        "on POST /api/v1/leads. Held only server-side by the frontend.",
    )
    varsco_content_api_base_url = fields.Char(
        string="Public Base URL",
        config_parameter="varsco_content_api.base_url",
        help="This Odoo instance's own public base URL, used to build "
        "absolute links (e.g. canonical URLs) returned by the API. "
        "Falls back to the standard 'web.base.url' parameter if unset.",
    )
    varsco_content_api_allowed_frontend_origin = fields.Char(
        string="Allowed Frontend Origin(s)",
        config_parameter="varsco_content_api.allowed_frontend_origin",
        help="Comma-separated list of Origins allowed to call the "
        "session-cookie-authenticated write routes "
        "(POST /api/v1/store/checkout, PUT /api/v1/portal/profile) "
        "directly from a browser. Defaults to https://varsco.com.",
    )

    def action_varsco_content_api_generate_write_token(self):
        """Generate and immediately persist a new write token, bypassing the
        settings form's own save step — a stale/leaked token should be
        rotatable in one click, not left pending an unrelated 'Save'."""
        self.env["ir.config_parameter"].sudo().set_param(
            "varsco_content_api.write_token", secrets.token_urlsafe(32)
        )
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }
