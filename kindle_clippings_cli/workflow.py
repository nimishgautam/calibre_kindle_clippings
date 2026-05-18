from __future__ import annotations

from pathlib import Path

from .calibre_adapter import CalibreAdapter, choose_likely_destination, score_destination
from .config_store import ConfigStore
from .matching import confident_match, rank_candidates
from .models import BookAnnotations, BookPlan, CalibreBook, Destination, ImportPlan
from .parser import group_clippings, parse_file
from .render import classify_conflicts, conflict_diff, merge_destination_html, render_annotation


class Console:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def print(self, message: str = "") -> None:
        if self.enabled:
            print(message)

    def ask(self, prompt: str, default: str | None = None) -> str:
        if default:
            prompt = f"{prompt} [{default}] "
        else:
            prompt = f"{prompt} "
        value = input(prompt).strip()
        return value or (default or "")


def build_plan(
    clippings_path: str,
    library_path: str,
    config: ConfigStore,
    destination_arg: str | None = None,
    interactive: bool = True,
    console: Console | None = None,
) -> ImportPlan:
    console = console or Console(interactive)
    clippings, issues = parse_file(clippings_path)
    skipped_bookmarks = sum(1 for clipping in clippings if clipping.kind == "bookmark")
    importable = [clipping for clipping in clippings if clipping.kind in {"highlight", "note"} and clipping.text.strip()]
    groups = group_clippings(importable)

    with CalibreAdapter(library_path, read_only=True) as adapter:
        adapter.validate()
        destinations = adapter.destinations()
        destination_fields = [destination.field for destination in destinations if not destination.is_comments]
        books = adapter.books(destination_fields=destination_fields)
        destination = resolve_destination(
            destinations=destinations,
            books=books,
            library_path=library_path,
            config=config,
            destination_arg=destination_arg,
            interactive=interactive,
            console=console,
        )
        plans = [
            plan_book(group, books, library_path, config, adapter, destination, interactive=interactive, console=console)
            for group in groups
        ]

    return ImportPlan(
        clippings_path=str(Path(clippings_path).expanduser().resolve()),
        library_path=str(Path(library_path).expanduser().resolve()),
        destination=destination,
        books=plans,
        parse_issues=issues,
        skipped_bookmarks=skipped_bookmarks,
    )


def resolve_destination(
    destinations: list[Destination],
    books: list[CalibreBook],
    library_path: str,
    config: ConfigStore,
    destination_arg: str | None,
    interactive: bool,
    console: Console,
) -> Destination:
    if destination_arg:
        destination = find_destination(destinations, destination_arg)
        if destination is None:
            valid = ", ".join(destination.field for destination in destinations)
            raise ValueError(f"Unknown destination {destination_arg!r}. Valid fields: {valid}")
        config.set_destination(library_path, destination.field)
        return destination

    likely = choose_likely_destination(destinations, books, remembered_field=config.get_destination(library_path))
    if not interactive:
        return likely

    console.print("\nAnnotation destination candidates:")
    scored = sorted(((score_destination(destination, books), destination) for destination in destinations), key=lambda item: (-item[0][0], item[1].name.casefold()))
    for idx, ((score, reasons), destination) in enumerate(scored, 1):
        marker = "default" if destination.field == likely.field else ""
        reason = "; ".join(reasons) if reasons else "no annotation-specific signals"
        console.print(f"  {idx}. {destination.name} ({destination.field}) score={score} {marker} - {reason}")
    answer = console.ask("Choose destination number", default=str([item[1].field for item in scored].index(likely.field) + 1))
    try:
        destination = scored[int(answer) - 1][1]
    except Exception:
        raise ValueError(f"Invalid destination selection: {answer}")
    config.set_destination(library_path, destination.field)
    return destination


def find_destination(destinations: list[Destination], value: str) -> Destination | None:
    value_cf = value.casefold()
    for destination in destinations:
        if destination.field.casefold() == value_cf or destination.name.casefold() == value_cf:
            return destination
    return None


def plan_book(
    group: BookAnnotations,
    books: list[CalibreBook],
    library_path: str,
    config: ConfigStore,
    adapter: CalibreAdapter,
    destination: Destination,
    interactive: bool,
    console: Console,
) -> BookPlan:
    candidates = rank_candidates(group, books)
    chosen: CalibreBook | None = None
    remembered_id = config.get_mapping(library_path, group.key)
    if remembered_id is not None:
        chosen = next((book for book in books if book.book_id == remembered_id), None)

    if chosen is None:
        confident = confident_match(candidates)
        if confident:
            chosen = confident.book

    if chosen is None and interactive:
        chosen = choose_book_interactively(group, candidates, books, console)

    annotations = [render_annotation(clipping) for clipping in group.clippings]
    plan = BookPlan(
        source_key=group.key,
        source_title=group.title,
        source_author=group.author,
        book=chosen,
        candidates=candidates,
        annotations=annotations,
    )
    if chosen is None:
        plan.skipped_count = len(annotations)
        plan.skipped_reason = "no matched Calibre book"
        return plan

    recompute_book_plan(adapter, destination, plan)
    return plan


def persist_matched_books(plan: ImportPlan, config: ConfigStore) -> int:
    saved = 0
    for book_plan in plan.matched_books:
        if book_plan.book is None:
            continue
        config.set_mapping(
            plan.library_path,
            book_plan.source_key,
            book_plan.book.book_id,
            book_plan.source_title,
            book_plan.source_author,
            book_plan.book.title,
            book_plan.book.authors,
        )
        saved += 1
    return saved


def choose_book_interactively(
    group: BookAnnotations,
    candidates: list,
    books: list[CalibreBook],
    console: Console,
) -> CalibreBook | None:
    console.print(f"\nMatch needed: {group.title}" + (f" by {group.author}" if group.author else ""))
    for idx, candidate in enumerate(candidates, 1):
        authors = ", ".join(candidate.book.authors)
        console.print(f"  {idx}. [{candidate.book.book_id}] {candidate.book.title} by {authors} score={candidate.score:.2f} ({'; '.join(candidate.reasons)})")
    console.print("  s. Search manually")
    console.print("  k. Skip this book")
    answer = console.ask("Select match", default="1" if candidates else "s")
    if answer.lower() == "k":
        return None
    if answer.lower() == "s":
        return search_books(books, console)
    try:
        return candidates[int(answer) - 1].book
    except Exception:
        console.print("Invalid selection; skipping this book.")
        return None


def search_books(books: list[CalibreBook], console: Console) -> CalibreBook | None:
    query = console.ask("Search title/author")
    if not query:
        return None
    query_cf = query.casefold()
    matches = [
        book
        for book in books
        if query_cf in book.title.casefold() or any(query_cf in author.casefold() for author in book.authors)
    ][:20]
    if not matches:
        console.print("No matches.")
        return None
    for idx, book in enumerate(matches, 1):
        console.print(f"  {idx}. [{book.book_id}] {book.title} by {', '.join(book.authors)}")
    answer = console.ask("Select match number, or k to skip", default="1")
    if answer.lower() == "k":
        return None
    try:
        return matches[int(answer) - 1]
    except Exception:
        console.print("Invalid selection; skipping this book.")
        return None


def recompute_plan(adapter: CalibreAdapter, plan: ImportPlan) -> None:
    for book_plan in plan.matched_books:
        recompute_book_plan(adapter, plan.destination, book_plan)


def recompute_book_plan(adapter: CalibreAdapter, destination: Destination, plan: BookPlan) -> None:
    assert plan.book is not None
    existing_html = adapter.read_destination_html(plan.book.book_id, destination)
    conflicts, duplicates = classify_conflicts(existing_html, plan.annotations, plan.book.book_id, plan.book.title)
    previous_resolution = {conflict.incoming_hash: conflict.resolution for conflict in plan.conflicts}
    for conflict in conflicts:
        conflict.resolution = previous_resolution.get(conflict.incoming_hash, conflict.resolution)
    final_html, new_count, duplicate_count = merge_destination_html(existing_html, plan.annotations, conflicts)
    plan.conflicts = conflicts
    plan.final_html = final_html
    plan.new_count = new_count
    plan.duplicate_count = max(duplicates, duplicate_count)
    plan.skipped_count = len(plan.annotations) - plan.new_count - plan.duplicate_count


def review_plan(plan: ImportPlan, interactive: bool, console: Console | None = None) -> bool:
    console = console or Console(interactive)
    print_summary(plan, console)
    if not interactive:
        return True
    console.print("\nReview commands: summary, books, conflicts, conflict N, import N, keep N, apply, abort")
    while True:
        command = console.ask("review>", default="apply").strip()
        if command in {"apply", "a"}:
            return True
        if command in {"abort", "q", "quit"}:
            return False
        if command == "summary":
            print_summary(plan, console)
        elif command == "books":
            print_books(plan, console)
        elif command == "conflicts":
            print_conflicts(plan, console)
        elif command.startswith("conflict "):
            show_conflict(plan, command, console)
        elif command.startswith("import "):
            set_conflict_resolution(plan, command, "import", console)
        elif command.startswith("keep "):
            set_conflict_resolution(plan, command, "keep", console)
        else:
            console.print("Unknown command.")


def apply_plan(plan: ImportPlan) -> None:
    with CalibreAdapter(plan.library_path, read_only=False) as adapter:
        plan.backup_path = adapter.backup_metadata_db()
        recompute_plan(adapter, plan)
        updates = {
            book.book.book_id: book.final_html
            for book in plan.matched_books
            if book.book is not None and book.final_html is not None and book.new_count > 0
        }
        adapter.write_destination_html_bulk(plan.destination, updates)


def print_summary(plan: ImportPlan, console: Console) -> None:
    console.print("\nImport summary:")
    console.print(f"  Destination: {plan.destination.name} ({plan.destination.field})")
    console.print(f"  Matched books: {len(plan.matched_books)}")
    console.print(f"  Skipped books: {len(plan.skipped_books)}")
    console.print(f"  New annotations: {sum(book.new_count for book in plan.books)}")
    console.print(f"  Duplicates kept: {sum(book.duplicate_count for book in plan.books)}")
    console.print(f"  Conflicts: {sum(len(book.conflicts) for book in plan.books)}")
    console.print(f"  Skipped bookmarks: {plan.skipped_bookmarks}")
    if plan.parse_issues:
        console.print(f"  Parse issues: {len(plan.parse_issues)}")


def print_books(plan: ImportPlan, console: Console) -> None:
    for idx, book in enumerate(plan.books, 1):
        target = f"[{book.book.book_id}] {book.book.title}" if book.book else f"SKIPPED: {book.skipped_reason}"
        console.print(f"{idx}. {book.source_title} -> {target}; new={book.new_count}, dup={book.duplicate_count}, conflicts={len(book.conflicts)}")


def all_conflicts(plan: ImportPlan) -> list:
    conflicts = []
    for book in plan.books:
        conflicts.extend(book.conflicts)
    return conflicts


def print_conflicts(plan: ImportPlan, console: Console) -> None:
    conflicts = all_conflicts(plan)
    if not conflicts:
        console.print("No conflicts.")
        return
    for idx, conflict in enumerate(conflicts, 1):
        console.print(f"{idx}. [{conflict.resolution}] {conflict.title} at {conflict.location_sort}")


def show_conflict(plan: ImportPlan, command: str, console: Console) -> None:
    conflict = _conflict_from_command(plan, command, console)
    if conflict:
        console.print(conflict_diff(conflict) or "No textual diff available.")


def set_conflict_resolution(plan: ImportPlan, command: str, resolution: str, console: Console) -> None:
    conflict = _conflict_from_command(plan, command, console)
    if conflict:
        conflict.resolution = resolution
        console.print(f"Conflict set to {resolution}.")


def _conflict_from_command(plan: ImportPlan, command: str, console: Console):
    parts = command.split()
    if len(parts) != 2 or not parts[1].isdigit():
        console.print("Expected command with conflict number.")
        return None
    conflicts = all_conflicts(plan)
    idx = int(parts[1]) - 1
    if idx < 0 or idx >= len(conflicts):
        console.print("Conflict number out of range.")
        return None
    return conflicts[idx]
