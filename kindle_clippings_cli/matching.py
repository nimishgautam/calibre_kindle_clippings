from __future__ import annotations

import re

from .models import BookAnnotations, CalibreBook, MatchCandidate
from .text import authors_match, normalize_text, similarity


_EDITION_MARKERS = re.compile(
    r"\b(summary|abridged|unabridged)\b|\b(volume|vol\.?|book|part)\s+(\d+|[ivxlcdm]+)\b",
    re.IGNORECASE,
)


def _title_key(title: str) -> str:
    # Filename-style underscores and trailing articles occur in exported titles.
    title = title.replace("_", ":")
    title = re.sub(r",\s*(The|An|A)$", r"", title, flags=re.IGNORECASE)
    key = normalize_text(title)
    return re.sub(r"^(the|an|a)\s+", "", key)


def _title_variants(title: str) -> set[str]:
    title = re.sub(r"\s*\([^()]*\)\s*$", "", title)
    parts = re.split(r":|_", title)
    return {_title_key(":".join(parts[:end])) for end in range(1, len(parts) + 1)}


def _structured_match(source: BookAnnotations, book: CalibreBook) -> bool:
    title, author = source.title, source.author
    if not author:
        # Interpret an embedded author only when supported by library metadata.
        parts = re.split(r"\s+[-–—]\s+", title)
        if len(parts) > 1 and authors_match(parts[-1], book.authors):
            title, author = " - ".join(parts[:-1]), parts[-1]
    if not author or not authors_match(author, book.authors):
        return False
    # Summaries and numbered volumes can be different works. Require a saved
    # mapping or an interactive decision rather than dropping those labels.
    if _EDITION_MARKERS.search(title + " " + book.title):
        return _title_key(title) == _title_key(book.title)
    if _title_key(title) == _title_key(book.title):
        return True
    left = _title_key(re.sub(r"\s*\([^()]*\)\s*$", "", title))
    right = _title_key(re.sub(r"\s*\([^()]*\)\s*$", "", book.title))
    # A short title plus an author is useful for suggestions, but needs an
    # explicit choice before collapsing a one-word title into a longer edition.
    return (
        len(left.split()) >= 2 and left in _title_variants(book.title)
        or len(right.split()) >= 2 and right in _title_variants(title)
    )


def rank_candidates(source: BookAnnotations, books: list[CalibreBook], limit: int = 8) -> list[MatchCandidate]:
    candidates: list[MatchCandidate] = []
    for book in books:
        score, reasons = score_candidate(source, book)
        if score > 0.35:
            candidates.append(MatchCandidate(book=book, score=score, reasons=reasons))
    candidates.sort(key=lambda item: (-item.score, item.book.title.casefold(), item.book.book_id))
    return candidates[:limit]


def score_candidate(source: BookAnnotations, book: CalibreBook) -> tuple[float, list[str]]:
    title_score = similarity(source.title, book.title)
    score = title_score * 0.75
    reasons = [f"title {title_score:.2f}"]

    if normalize_text(source.title) == normalize_text(book.title):
        score += 0.15
        reasons.append("exact title")

    if source.author:
        if authors_match(source.author, book.authors):
            score += 0.25
            reasons.append("author match")
        else:
            best_author = max((similarity(source.author, author) for author in book.authors), default=0.0)
            score += best_author * 0.15
            reasons.append(f"author {best_author:.2f}")

    if _structured_match(source, book):
        score = max(score, 0.97)
        reasons.append("normalized title and author match")
    elif (
        _EDITION_MARKERS.search(source.title + " " + book.title)
        and _title_key(source.title) != _title_key(book.title)
    ):
        # A high fuzzy score alone must not bypass edition review.
        score = min(score, 0.91)
        reasons.append("edition difference requires review")
    return min(score, 1.0), reasons


def confident_match(candidates: list[MatchCandidate]) -> MatchCandidate | None:
    if not candidates:
        return None
    best = candidates[0]
    next_score = candidates[1].score if len(candidates) > 1 else 0.0
    if best.score >= 0.92 and best.score - next_score >= 0.08:
        return best
    return None
