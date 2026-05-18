from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .models import CalibreBook, Destination


class CalibreAdapter:
    def __init__(self, library_path: str, read_only: bool = True) -> None:
        self.library_path = str(Path(library_path).expanduser().resolve())
        self.read_only = read_only
        self.db = None

    def __enter__(self) -> "CalibreAdapter":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def open(self) -> None:
        try:
            from calibre.db.legacy import LibraryDatabase
        except Exception as exc:  # pragma: no cover - requires non-Calibre Python
            raise RuntimeError("This command must be run with calibre-debug so Calibre's Python API is available") from exc
        self.db = LibraryDatabase(self.library_path, read_only=self.read_only)

    def close(self) -> None:
        if self.db is not None and hasattr(self.db, "close"):
            self.db.close()

    def validate(self) -> None:
        metadata = Path(self.library_path) / "metadata.db"
        if not metadata.exists():
            raise FileNotFoundError(f"Calibre metadata.db not found: {metadata}")

    def backup_metadata_db(self) -> str:
        source = Path(self.library_path) / "metadata.db"
        if not source.exists():
            raise FileNotFoundError(f"Calibre metadata.db not found: {source}")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = source.with_name(f"metadata.db.kindle-clippings-{stamp}.bak")
        shutil.copy2(source, target)
        return str(target)

    def books(self, destination_fields: Iterable[str] = ()) -> list[CalibreBook]:
        assert self.db is not None
        id_field = self.db.FIELD_MAP["id"]
        result: list[CalibreBook] = []
        for record in self.db.data.iterall():
            book_id = int(record[id_field])
            mi = self.db.get_metadata(book_id, index_is_id=True)
            custom: dict[str, str | None] = {}
            for field in destination_fields:
                if field == "Comments":
                    continue
                try:
                    custom[field] = mi.get_user_metadata(field, False).get("#value#")
                except Exception:
                    custom[field] = None
            result.append(
                CalibreBook(
                    book_id=book_id,
                    title=mi.title or "",
                    authors=list(mi.authors or []),
                    comments=getattr(mi, "comments", None),
                    custom=custom,
                )
            )
        return result

    def destinations(self) -> list[Destination]:
        assert self.db is not None
        destinations = [Destination(field="Comments", name="Comments", is_comments=True)]
        for field in sorted(self.db.custom_field_keys()):
            metadata = self.db.metadata_for_field(field)
            if metadata.get("datatype") == "comments":
                destinations.append(Destination(field=field, name=metadata.get("name") or field, is_comments=False))
        return destinations

    def read_destination_html(self, book_id: int, destination: Destination) -> str | None:
        assert self.db is not None
        mi = self.db.get_metadata(book_id, index_is_id=True)
        if destination.is_comments:
            return getattr(mi, "comments", None)
        return mi.get_user_metadata(destination.field, False).get("#value#")

    def write_destination_html_bulk(self, destination: Destination, updates: dict[int, str]) -> None:
        assert self.db is not None
        if not updates:
            return
        if destination.is_comments:
            for book_id, value in updates.items():
                mi = self.db.get_metadata(book_id, index_is_id=True)
                mi.comments = value
                self.db.set_metadata(book_id, mi, set_title=False, set_authors=False, commit=True, force_changes=True, notify=False)
            return
        self.db.new_api.set_field(destination.field.lower(), updates)


def score_destination(destination: Destination, books: list[CalibreBook]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    name = f"{destination.name} {destination.field}".casefold()
    if "annotation" in name or "highlight" in name or "clipping" in name:
        score += 30
        reasons.append("name looks annotation-related")
    if destination.is_comments:
        score += 5
        reasons.append("built-in Comments fallback")
    content_hits = 0
    for book in books[:500]:
        value = book.comments if destination.is_comments else book.custom.get(destination.field)
        if value and "user_annotations" in value:
            content_hits += 1
    if content_hits:
        score += min(40, content_hits * 4)
        reasons.append(f"{content_hits} books already contain annotations")
    return score, reasons


def choose_likely_destination(destinations: list[Destination], books: list[CalibreBook], remembered_field: str | None = None) -> Destination:
    if remembered_field:
        for destination in destinations:
            if destination.field == remembered_field:
                return destination
    scored = [(score_destination(destination, books), destination) for destination in destinations]
    scored.sort(key=lambda item: (-item[0][0], item[1].name.casefold()))
    return scored[0][1]
