import hmac
import json
from html import escape as html_escape

from odoo import http
from odoo.http import request
from odoo.tools.mail import single_email_re

from .base import API_PREFIX, resolve_country


class VarscoContentApiLeads(http.Controller):
    """Secure S2S endpoint: the frontend BFF forwards form submissions here.

    auth="public" because there's no end-user Odoo session at this point —
    this route is called server-to-server, so the write_token bearer check
    below is the actual gate (architecture.md §5, odoo_api_spec.md §2.2).
    """

    REQUIRED_FIELDS = ("name", "email", "message", "source")

    # Human labels for the closed set of form identifiers the frontend sends
    # (src/lib/submission-context.ts SUBMISSION_SOURCES). Used both for the
    # lead subject and for the utm.source record name. An unrecognised value
    # is not an error — it is titlecased and used as-is, so a new form works
    # before this map is updated.
    SOURCE_LABELS = {
        "contact": "Contact",
        "services-solutions": "Advisory",
        "request-quote-page": "Quote",
        "product-quote-drawer": "Quote",
        "cart-quote": "Quote",
        "horeca-middle-east": "HORECA",
        "newsletter": "Newsletter",
    }

    # Metadata rendered into the lead's Notes tab. Kept separate from the
    # contact block so sales reads "who and what" first and provenance second.
    CONTEXT_LABELS = (
        ("topic", "Topic"),
        ("product_title", "Product"),
        ("page_path", "Submitted from"),
        ("page_section", "Section"),
        ("locale", "Language"),
        ("referrer_host", "Referrer"),
        ("utm_campaign", "Campaign"),
        ("portal_user_id", "Portal user"),
    )

    @staticmethod
    def _unauthorized():
        return request.make_json_response({"error": "unauthorized"}, status=401)

    @staticmethod
    def _bad_request(reason):
        return request.make_json_response({"error": reason}, status=400)

    def _write_token_valid(self):
        header = request.httprequest.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return False
        provided = header[len("Bearer "):].strip()
        expected = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("varsco_content_api.write_token", "")
        )
        # hmac.compare_digest: constant-time comparison, avoids a timing
        # side-channel on the token check.
        return bool(expected) and hmac.compare_digest(provided, expected)

    @classmethod
    def _source_label(cls, source):
        """Readable label for a form identifier."""
        source = (source or "").strip()
        if source in cls.SOURCE_LABELS:
            return cls.SOURCE_LABELS[source]
        return source.replace("-", " ").replace("_", " ").strip().title() or "Web"

    @classmethod
    def _build_subject(cls, payload):
        """Lead subject.

        Every lead used to be named "Web inquiry — {contact name}", so the CRM
        list view was a column of near-identical rows and a salesperson had to
        open each one to find out what it was about. The subject now leads with
        what the buyer wants, then what they asked about, then who they are:

            Quote — Olive Flounder — Acme Ltd
            Advisory — Staff it — Acme Ltd
            Contact — Technical support — Acme Ltd

        Falls back through product -> topic -> company -> contact name, so a
        minimal payload still produces something more useful than a constant.
        """
        parts = [cls._source_label(payload.get("source"))]
        subject_of = payload.get("product_title") or payload.get("topic")
        if subject_of:
            parts.append(subject_of.strip())
        who = payload.get("company") or payload.get("name")
        if who:
            parts.append(who.strip())
        # em dash separator matches the previous convention
        return " — ".join(p for p in parts if p)[:200]

    @staticmethod
    def _resolve_lang(locale):
        """Map a frontend locale code onto an installed res.lang.

        The frontend uses short codes (tr, de, zh) while Odoo stores full
        ones (tr_TR, de_DE, zh_CN), and only languages actually activated in
        this database exist as records — hence the prefix match against
        active langs rather than a fixed table.
        """
        code = (locale or "").strip()
        if not code:
            return False
        Lang = request.env["res.lang"].sudo()
        lang = Lang.search([("code", "=", code), ("active", "=", True)], limit=1)
        if not lang:
            lang = Lang.search(
                [("code", "=like", f"{code}\\_%"), ("active", "=", True)], limit=1
            )
        return lang.id if lang else False

    @staticmethod
    def _utm_record(model, name):
        """Find-or-create a utm.source / utm.medium / utm.campaign by name.

        `source` was in REQUIRED_FIELDS but was only ever rendered into the
        description text — it was never written to the lead, so every web lead
        carried the same fixed medium and no source at all, and attribution
        reporting in CRM was impossible. Records are created on demand so
        adding a form on the frontend needs no Odoo data migration.
        """
        name = (name or "").strip()
        if not name:
            return False
        Model = request.env[model].sudo()
        record = Model.search([("name", "=", name)], limit=1)
        if not record:
            record = Model.create({"name": name})
        return record.id

    @staticmethod
    def _format_description(payload):
        """A labeled HTML note for the lead's Notes tab instead of one plain
        paragraph. Every interpolated value is HTML-escaped — this is stored
        verbatim in crm.lead.description (an Html field, rendered as-is to
        internal users in the backend), so raw user input here would be a
        stored-XSS vector against the CRM team, not just an ugly note."""

        def esc(value):
            return html_escape(value or "")

        parts = [f"<p><strong>Contact:</strong> {esc(payload['name'])} ({esc(payload['email'])})</p>"]
        if payload.get("company"):
            parts.append(f"<p><strong>Company:</strong> {esc(payload['company'])}</p>")
        if payload.get("phone"):
            parts.append(f"<p><strong>Phone:</strong> {esc(payload['phone'])}</p>")
        parts.append(f"<p><strong>Source:</strong> {esc(payload['source'])}</p>")
        message_html = esc(payload["message"]).replace("\n", "<br/>")
        parts.append(f"<p><strong>Message:</strong><br/>{message_html}</p>")

        # Buyer-supplied spec answers (size band, fins, incoterm...). These
        # reached the API before but were dropped by the frontend schema; now
        # they arrive as a real mapping instead of being pasted into the
        # message as JSON.
        custom = payload.get("custom_fields")
        if isinstance(custom, dict) and custom:
            rows = "".join(
                f"<li><strong>{esc(str(key))}:</strong> {esc(str(value))}</li>"
                for key, value in custom.items()
            )
            parts.append(f"<p><strong>Requested specifications:</strong></p><ul>{rows}</ul>")

        if payload.get("cart_summary"):
            items_html = "".join(
                f"<li>{esc(line.lstrip('-* ').strip())}</li>"
                for line in payload["cart_summary"].splitlines()
                if line.strip()
            )
            parts.append(f"<p><strong>Requested Items:</strong></p><ul>{items_html}</ul>")

        # Provenance last: useful for attribution and for replying in the right
        # language, but not what a salesperson needs in the first three lines.
        context_rows = [
            f"<li><strong>{label}:</strong> {esc(str(payload[key]))}</li>"
            for key, label in VarscoContentApiLeads.CONTEXT_LABELS
            if payload.get(key)
        ]
        if context_rows:
            parts.append(
                "<p><strong>Submission context:</strong></p>"
                f"<ul>{''.join(context_rows)}</ul>"
            )
        return "".join(parts)

    @http.route(
        f"{API_PREFIX}/leads",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def create_lead(self, **kwargs):
        if not self._write_token_valid():
            return self._unauthorized()
        try:
            # The frontend BFF sends a plain JSON body (fetch + JSON.stringify),
            # not Odoo's JSON-RPC envelope — parse it directly, matching how
            # every POST route in this addon must handle type="http".
            payload = json.loads(request.httprequest.get_data(as_text=True) or "{}")
        except ValueError:
            return self._bad_request("invalid_json")
        missing = [field for field in self.REQUIRED_FIELDS if not payload.get(field)]
        if missing:
            return self._bad_request(f"missing_fields:{','.join(missing)}")
        if not single_email_re.match(payload["email"]):
            return self._bad_request("invalid_email")

        # utm_medium is what the frontend observed (cpc, email, referral...).
        # Absent that, the visit came through the website itself.
        medium_id = self._utm_record("utm.medium", payload.get("utm_medium"))
        if not medium_id:
            medium = request.env.ref("utm.utm_medium_website", raise_if_not_found=False)
            medium_id = medium.id if medium else False

        # Prefer the real campaign source (google, linkedin) when the visit
        # carried one; otherwise attribute to the form that produced the lead,
        # which is still far better than the nothing recorded before.
        source_id = self._utm_record(
            "utm.source", payload.get("utm_source") or self._source_label(payload.get("source"))
        )
        campaign_id = self._utm_record("utm.campaign", payload.get("utm_campaign"))
        country = resolve_country(payload.get("country"))

        values = {
            "name": self._build_subject(payload),
            # Explicit, not left to the ORM default: crm.lead's `type` field
            # defaults to 'lead' only if the acting user has
            # crm.group_use_lead — the public user authenticating this S2S
            # route never does, so without this every web submission silently
            # skipped the qualification step straight into an opportunity.
            "type": "lead",
            "contact_name": payload["name"],
            "email_from": payload["email"],
            "partner_name": payload.get("company") or False,
            "phone": payload.get("phone") or False,
            "description": self._format_description(payload),
            "medium_id": medium_id,
            "source_id": source_id,
            "campaign_id": campaign_id,
            "country_id": country.id if country else False,
        }
        # lang_id lets the salesperson see which language to reply in, and
        # drives Odoo's own outbound templates. Only set when the locale maps
        # to an installed res.lang — an untranslated Odoo would otherwise
        # reject the write.
        lang_id = self._resolve_lang(payload.get("locale"))
        if lang_id:
            values["lang_id"] = lang_id

        lead = request.env["crm.lead"].sudo().create(values)
        return request.make_json_response(
            {"status": "success", "lead_id": lead.id}, status=201
        )
