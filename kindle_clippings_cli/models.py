from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ParsedClipping:
    order: int
    bookline: str
    title: str
    author: Optional[str]
    statusline: str
    language: Optional[str]
    kind: str
    text: str
    created_at: Optional[datetime]
    begin: Optional[int]
    end: Optional[int]
    page: Optional[int]


@dataclass
class ParseIssue:
    severity: str
    message: str
    record: Optional[str] = None


@dataclass
class BookAnnotations:
    key: str
    title: str
    author: Optional[str]
    clippings: list[ParsedClipping] = field(default_factory=list)


@dataclass
class CalibreBook:
    book_id: int
    title: str
    authors: list[str]
    comments: Optional[str] = None
    custom: dict[str, Optional[str]] = field(default_factory=dict)


@dataclass
class MatchCandidate:
    book: CalibreBook
    score: float
    reasons: list[str]


@dataclass
class Destination:
    field: str
    name: str
    is_comments: bool


@dataclass
class RenderedAnnotation:
    clipping: ParsedClipping
    annotation_hash: str
    html: str
    location_sort: str


@dataclass
class Conflict:
    book_id: int
    title: str
    location_sort: str
    incoming_hash: str
    existing_hash: Optional[str]
    incoming_text: str
    existing_text: str
    resolution: str = "keep"


@dataclass
class BookPlan:
    source_key: str
    source_title: str
    source_author: Optional[str]
    book: Optional[CalibreBook]
    candidates: list[MatchCandidate]
    annotations: list[RenderedAnnotation]
    new_count: int = 0
    duplicate_count: int = 0
    skipped_count: int = 0
    conflicts: list[Conflict] = field(default_factory=list)
    skipped_reason: Optional[str] = None
    final_html: Optional[str] = None


@dataclass
class ImportPlan:
    clippings_path: str
    library_path: str
    destination: Destination
    books: list[BookPlan]
    parse_issues: list[ParseIssue]
    skipped_bookmarks: int
    backup_path: Optional[str] = None

    @property
    def matched_books(self) -> list[BookPlan]:
        return [book for book in self.books if book.book is not None]

    @property
    def skipped_books(self) -> list[BookPlan]:
        return [book for book in self.books if book.book is None]
