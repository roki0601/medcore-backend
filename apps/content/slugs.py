from __future__ import annotations

import re

from django.utils.text import slugify

MAX_SLUG_LENGTH = 255

# Static frontend routes that must not become a public subject URL.
RESERVED_SUBJECT_SLUGS = frozenset(
    {
        "api",
        "auth",
        "catalog",
        "flashcards",
        "llms",
        "offer",
        "og",
        "payment",
        "payment-and-refund",
        "privacy",
        "profile",
        "progress",
        "quiz-attempts",
        "robots",
        "sitemap",
        "subscription",
    }
)

_CYRILLIC = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "yo",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "kh",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
)


_PLACEHOLDER = re.compile(r"^(subject|section|topic)(-\d+)?$")


def latin_base(title: str, *, fallback: str, max_length: int = MAX_SLUG_LENGTH) -> str:
    """Latin kebab-case base. Cyrillic is transliterated; other scripts are dropped."""

    base = slugify(title.casefold().translate(_CYRILLIC))[:max_length]
    return base or fallback


def is_placeholder_slug(slug: str) -> bool:
    """True for the model-name fallback left by ASCII-only slugify."""

    return _PLACEHOLDER.fullmatch(slug) is not None


def unique_candidate(
    base: str,
    *,
    taken,
    reserved: frozenset[str] = frozenset(),
    max_length: int = MAX_SLUG_LENGTH,
) -> str:
    candidate = base
    suffix = 2
    while candidate in reserved or candidate in taken:
        tail = f"-{suffix}"
        candidate = f"{base[: max_length - len(tail)]}{tail}"
        suffix += 1
    return candidate
