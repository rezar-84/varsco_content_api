from odoo.http import request

API_PREFIX = "/api/v1"


def require_trusted_origin():
    """Reject session-cookie-authenticated writes whose Origin header
    doesn't match the configured frontend (security.md §3: Odoo itself must
    reject cross-origin browser calls to /api/v1/* that don't come through
    the frontend's own server-side proxy).

    A missing Origin header is allowed through — the frontend's BFF talks to
    this module server-to-server and never sends one, and browsers omit it
    on plain top-level navigation. A cross-site form/fetch POST or PUT,
    however, always carries an Origin the browser sets and page script can't
    override, so checking it (when present) against an allow-list blocks
    that CSRF vector without breaking the sanctioned call path.

    Returns a 403 JSON response if the request should be rejected, None
    otherwise.
    """
    origin = request.httprequest.headers.get("Origin")
    if not origin:
        return None
    raw_allowed = (
        request.env["ir.config_parameter"]
        .sudo()
        .get_param("varsco_content_api.allowed_frontend_origin", "https://varsco.com")
    )
    allowed = {o.strip() for o in raw_allowed.split(",") if o.strip()}
    if origin not in allowed:
        return request.make_json_response({"error": "origin_not_allowed"}, status=403)
    return None
