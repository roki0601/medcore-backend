from __future__ import annotations

import re

from django.core.exceptions import ValidationError

FENCED_CODE_RE = re.compile(r"(```.*?```|~~~.*?~~~)", re.DOTALL)

# A real HTML tag needs a name and a closing angle bracket, so medical prose such
# as "<5 мм" or "a < b" is not a false positive.
HTML_TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>")

# Markdown link/image destinations must not carry executable schemes.
UNSAFE_URL_RE = re.compile(
    r"\]\(\s*(?:javascript|data|vbscript)\s*:",
    re.IGNORECASE,
)


def _without_fenced_code(value: str) -> str:
    return FENCED_CODE_RE.sub(" ", value)


def validate_markdown_body(value: str) -> None:
    """Reject raw HTML and unsafe link schemes in stored markdown.

    The backend never renders Markdown, so executable content is stopped at the
    write boundary instead of being sanitized with a renderer dependency.
    Fenced code samples are ignored because they are not interpreted as markup.
    """

    if not value:
        return
    checked = _without_fenced_code(value)
    if HTML_TAG_RE.search(checked):
        raise ValidationError(
            "Raw HTML is not allowed in markdown body.",
            code="raw_html_not_allowed",
        )
    if UNSAFE_URL_RE.search(checked):
        raise ValidationError(
            "Unsafe URL scheme is not allowed in markdown links.",
            code="unsafe_url_not_allowed",
        )
