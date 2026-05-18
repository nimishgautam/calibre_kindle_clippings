from __future__ import annotations

from .models import BookAnnotations, CalibreBook, MatchCandidate
from .text import authors_match, normalize_text, similarity


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

    return min(score, 1.0), reasons


def confident_match(candidates: list[MatchCandidate]) -> MatchCandidate | None:
    if not candidates:
        return None
    best = candidates[0]
    next_score = candidates[1].score if len(candidates) > 1 else 0.0
    if best.score >= 0.92 and best.score - next_score >= 0.08:
        return best
    return None
