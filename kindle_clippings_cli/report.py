from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import ImportPlan


def default_report_path(clippings_path: str) -> str:
    source = Path(clippings_path)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return str(source.with_name(f"{source.stem}.import-report-{stamp}.json"))


def write_report(plan: ImportPlan, path: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(to_report_dict(plan), handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def to_report_dict(plan: ImportPlan) -> dict[str, Any]:
    return {
        "clippings_path": plan.clippings_path,
        "library_path": plan.library_path,
        "destination": asdict(plan.destination),
        "backup_path": plan.backup_path,
        "parse_issues": [asdict(issue) for issue in plan.parse_issues],
        "skipped_bookmarks": plan.skipped_bookmarks,
        "books": [_book_to_dict(book) for book in plan.books],
        "summary": {
            "matched_books": len(plan.matched_books),
            "skipped_books": len(plan.skipped_books),
            "new_annotations": sum(book.new_count for book in plan.books),
            "duplicates": sum(book.duplicate_count for book in plan.books),
            "conflicts": sum(len(book.conflicts) for book in plan.books),
        },
    }


def _book_to_dict(book_plan) -> dict[str, Any]:
    return {
        "source_key": book_plan.source_key,
        "source_title": book_plan.source_title,
        "source_author": book_plan.source_author,
        "calibre_book": asdict(book_plan.book) if book_plan.book else None,
        "candidates": [
            {
                "book_id": candidate.book.book_id,
                "title": candidate.book.title,
                "authors": candidate.book.authors,
                "score": candidate.score,
                "reasons": candidate.reasons,
            }
            for candidate in book_plan.candidates
        ],
        "new_count": book_plan.new_count,
        "duplicate_count": book_plan.duplicate_count,
        "skipped_count": book_plan.skipped_count,
        "skipped_reason": book_plan.skipped_reason,
        "conflicts": [asdict(conflict) for conflict in book_plan.conflicts],
        "annotations": [
            {
                "hash": annotation.annotation_hash,
                "kind": annotation.clipping.kind,
                "text": annotation.clipping.text,
                "location_sort": annotation.location_sort,
                "created_at": annotation.clipping.created_at.isoformat() if annotation.clipping.created_at else None,
            }
            for annotation in book_plan.annotations
        ],
    }
