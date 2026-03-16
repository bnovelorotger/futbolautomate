from __future__ import annotations

import re
import unicodedata

from bs4 import BeautifulSoup


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_token(value: str) -> str:
    compact = normalize_spaces(strip_accents(value.lower()))
    return re.sub(r"[^a-z0-9]+", " ", compact).strip()


def html_to_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    normalized = re.sub(r"\s+([,.;:!?])", r"\1", normalize_spaces(text))
    return normalized or None
