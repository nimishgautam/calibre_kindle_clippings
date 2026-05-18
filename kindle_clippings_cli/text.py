from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable, Optional


_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")


def normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    value = _PUNCT_RE.sub(" ", value)
    return _SPACE_RE.sub(" ", value).strip()


def author_tokens(value: Optional[str]) -> set[str]:
    normalized = normalize_text(value)
    return {part for part in normalized.split() if len(part) > 1}


def authors_match(source: Optional[str], candidates: Iterable[str]) -> bool:
    source_tokens = author_tokens(source)
    if not source_tokens:
        return False
    for candidate in candidates:
        candidate_tokens = author_tokens(candidate)
        if source_tokens.issubset(candidate_tokens) or candidate_tokens.issubset(source_tokens):
            return True
    return False


def similarity(left: Optional[str], right: Optional[str]) -> float:
    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()
