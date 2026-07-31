import re
from urllib.parse import urlsplit

from lxml import html as lxml_html

from odoo.exceptions import ValidationError

_SEMANTIC_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "em",
    "figcaption",
    "figure",
    "h2",
    "h3",
    "h4",
    "img",
    "li",
    "ol",
    "p",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}
_SEMANTIC_ATTRIBUTES = {
    "a": {"href", "title"},
    "img": {"src", "alt", "width", "height"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
}
_MARKUP = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")


def _validate_plain_text(value, label):
    if isinstance(value, str) and _MARKUP.search(value):
        raise ValidationError(f"{label} must be plain text, not HTML.")


def _validate_semantic_html(value, label):
    try:
        root = lxml_html.fragment_fromstring(value, create_parent="div")
    except (TypeError, ValueError, lxml_html.etree.ParserError) as error:
        raise ValidationError(f"{label} must be valid semantic HTML.") from error
    for element in root.iterdescendants():
        if not isinstance(element.tag, str) or element.tag not in _SEMANTIC_TAGS:
            raise ValidationError(f"{label} contains forbidden HTML elements.")
        allowed_attributes = _SEMANTIC_ATTRIBUTES.get(element.tag, set())
        if set(element.attrib) - allowed_attributes:
            raise ValidationError(f"{label} contains forbidden HTML attributes.")
        href = element.attrib.get("href")
        if href:
            scheme = urlsplit(href).scheme.lower()
            if scheme and scheme not in {"http", "https", "mailto", "tel"}:
                raise ValidationError(f"{label} contains an unsafe link.")
        if element.tag == "img":
            if not element.attrib.get("src") or "alt" not in element.attrib:
                raise ValidationError(f"{label} images require src and alt.")
            scheme = urlsplit(element.attrib["src"]).scheme.lower()
            if scheme and scheme not in {"http", "https"}:
                raise ValidationError(f"{label} contains an unsafe image source.")


def _validate_media(media, label):
    if not isinstance(media, dict) or not media.get("url") or "alt" not in media:
        raise ValidationError(f"{label} requires url and alt.")
    if set(media) - {"url", "alt", "width", "height"}:
        raise ValidationError(f"{label} contains unsupported fields.")
    _validate_plain_text(media.get("alt"), f"{label}.alt")
