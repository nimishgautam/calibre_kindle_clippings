from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from datetime import timezone
from difflib import unified_diff
from html.parser import HTMLParser

from .models import Conflict, ParsedClipping, RenderedAnnotation
from .text import normalize_text


ANNOTATIONS_HEADER = '<div class="user_annotations" style="margin:0"></div>'
COMMENTS_DIVIDER = '<div class="comments_divider"><p style="text-align:center;margin:1em 0 1em 0">&middot;  &middot;  &bull;  &middot;  &#x2726;  &middot;  &bull;  &middot; &middot;</p></div>'


@dataclass
class ExistingAnnotation:
    annotation_hash: str | None
    location_sort: str
    text: str
    html: str


def render_annotation(clipping: ParsedClipping) -> RenderedAnnotation:
    location_sort = make_location_sort(clipping)
    annotation_hash = make_annotation_hash(clipping)
    timestamp = ""
    timestamp_attr = ""
    if clipping.created_at:
        timestamp = html.escape(clipping.created_at.strftime("%d %b %Y %H:%M:%S"))
        timestamp_attr = str(int(clipping.created_at.replace(tzinfo=timezone.utc).timestamp()))

    location = display_location(clipping)
    content = html.escape(clipping.text.strip())
    if clipping.kind == "note":
        body = f'<p class="note" style="margin:0 0 0.5em 0">{content}</p>'
    else:
        body = f'<p class="highlight" style="margin:0 0 0.5em 0">{content}</p>'

    row = (
        '<table cellpadding="0" width="100%" style="font-size:80%;color:#555">'
        f'<tr><td class="location" style="text-align:left">{html.escape(location)}</td>'
        f'<td class="timestamp" uts="{timestamp_attr}" style="text-align:right">{timestamp}</td></tr>'
        "</table>"
    )
    rendered = (
        f'<div class="annotation" genre="" hash="{annotation_hash}" '
        f'kind="{html.escape(clipping.kind)}" location_sort="{location_sort}" reader="Kindle" '
        'style="margin:0 0 0.5em 0">'
        f"{body}{row}</div>"
    )
    return RenderedAnnotation(clipping=clipping, annotation_hash=annotation_hash, html=rendered, location_sort=location_sort)


def make_annotation_hash(clipping: ParsedClipping) -> str:
    parts = [
        clipping.kind,
        normalize_text(clipping.text),
        str(clipping.begin or ""),
        str(clipping.end or ""),
        str(clipping.page or ""),
        clipping.created_at.isoformat() if clipping.created_at else "",
    ]
    return hashlib.sha1("\0".join(parts).encode("utf-8")).hexdigest()


def make_location_sort(clipping: ParsedClipping) -> str:
    if clipping.begin is not None:
        return f"{clipping.begin:010d}"
    if clipping.page is not None:
        return f"p{clipping.page:010d}"
    return f"o{clipping.order:010d}"


def display_location(clipping: ParsedClipping) -> str:
    parts = []
    if clipping.page is not None:
        parts.append(f"Page {clipping.page}")
    if clipping.begin is not None and clipping.end is not None and clipping.begin != clipping.end:
        parts.append(f"Location {clipping.begin}-{clipping.end}")
    elif clipping.begin is not None:
        parts.append(f"Location {clipping.begin}")
    return " | ".join(parts)


def build_user_annotations(annotations: list[RenderedAnnotation]) -> str:
    sorted_annotations = sorted(annotations, key=lambda item: item.location_sort)
    return '<div class="user_annotations" style="margin:0">' + "".join(item.html for item in sorted_annotations) + "</div>"


def merge_destination_html(existing_html: str | None, incoming: list[RenderedAnnotation], conflicts: list[Conflict]) -> tuple[str, int, int]:
    existing_html = existing_html or ""
    existing = extract_existing_annotations(existing_html)
    existing_hashes = {item.annotation_hash for item in existing if item.annotation_hash}
    conflict_by_hash = {conflict.incoming_hash: conflict for conflict in conflicts}

    accepted: list[RenderedAnnotation] = []
    duplicate_count = 0
    for annotation in incoming:
        if annotation.annotation_hash in existing_hashes:
            duplicate_count += 1
            continue
        conflict = conflict_by_hash.get(annotation.annotation_hash)
        if conflict and conflict.resolution == "keep":
            continue
        accepted.append(annotation)

    old_uas = _find_user_annotations_block(existing_html)
    old_annotation_html = [item.html for item in existing]
    if conflicts:
        replace_locations = {conflict.location_sort for conflict in conflicts if conflict.resolution == "import"}
        if replace_locations:
            old_annotation_html = [item.html for item in existing if item.location_sort not in replace_locations]

    combined_html = old_annotation_html + [item.html for item in accepted]
    combined_html.sort(key=_location_sort_from_html)
    annotations_html = '<div class="user_annotations" style="margin:0">' + "".join(combined_html) + "</div>"

    if old_uas:
        start, end = old_uas
        return existing_html[:start] + annotations_html + existing_html[end:], len(accepted), duplicate_count
    if existing_html.strip():
        return existing_html + COMMENTS_DIVIDER + annotations_html, len(accepted), duplicate_count
    return annotations_html, len(accepted), duplicate_count


def classify_conflicts(existing_html: str | None, incoming: list[RenderedAnnotation], book_id: int, title: str) -> tuple[list[Conflict], int]:
    existing = extract_existing_annotations(existing_html or "")
    existing_hashes = {item.annotation_hash for item in existing if item.annotation_hash}
    by_location = {item.location_sort: item for item in existing if item.location_sort}
    conflicts: list[Conflict] = []
    duplicates = 0
    for annotation in incoming:
        if annotation.annotation_hash in existing_hashes:
            duplicates += 1
            continue
        existing_at_location = by_location.get(annotation.location_sort)
        if existing_at_location:
            conflicts.append(
                Conflict(
                    book_id=book_id,
                    title=title,
                    location_sort=annotation.location_sort,
                    incoming_hash=annotation.annotation_hash,
                    existing_hash=existing_at_location.annotation_hash,
                    incoming_text=plain_annotation_text(annotation.html),
                    existing_text=existing_at_location.text,
                )
            )
    return conflicts, duplicates


def conflict_diff(conflict: Conflict) -> str:
    return "".join(
        unified_diff(
            conflict.existing_text.splitlines(keepends=True),
            conflict.incoming_text.splitlines(keepends=True),
            fromfile="existing",
            tofile="incoming",
        )
    )


def extract_existing_annotations(source: str) -> list[ExistingAnnotation]:
    parser = _AnnotationParser()
    parser.feed(source or "")
    return parser.annotations


def plain_annotation_text(source: str) -> str:
    parser = _PlainTextParser()
    parser.feed(source or "")
    return re.sub(r"\n{3,}", "\n\n", parser.text.strip())


def _find_user_annotations_block(source: str) -> tuple[int, int] | None:
    match = re.search(r'<div\b[^>]*class=["\']user_annotations["\'][^>]*>', source or "", re.IGNORECASE)
    if not match:
        return None
    depth = 0
    tag_re = re.compile(r"</?div\b[^>]*>", re.IGNORECASE)
    for tag in tag_re.finditer(source, match.start()):
        if tag.group(0).startswith("</"):
            depth -= 1
            if depth == 0:
                return match.start(), tag.end()
        else:
            depth += 1
    return None


def _location_sort_from_html(source: str) -> str:
    match = re.search(r'location_sort=["\']([^"\']*)["\']', source)
    return match.group(1) if match else ""


class _AnnotationParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.annotations: list[ExistingAnnotation] = []
        self._depth = 0
        self._current_attrs: dict[str, str] | None = None
        self._current_parts: list[str] = []
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        if tag == "div" and "annotation" in attrs_dict.get("class", "").split() and self._current_attrs is None:
            self._current_attrs = attrs_dict
            self._depth = 1
            self._current_parts = [self.get_starttag_text() or ""]
            self._current_text = []
            return
        if self._current_attrs is not None:
            if tag == "div":
                self._depth += 1
            self._current_parts.append(self.get_starttag_text() or "")

    def handle_endtag(self, tag: str) -> None:
        if self._current_attrs is None:
            return
        self._current_parts.append(f"</{tag}>")
        if tag == "div":
            self._depth -= 1
            if self._depth == 0:
                self.annotations.append(
                    ExistingAnnotation(
                        annotation_hash=self._current_attrs.get("hash"),
                        location_sort=self._current_attrs.get("location_sort", ""),
                        text=re.sub(r"\n{3,}", "\n\n", "\n".join(part.strip() for part in self._current_text if part.strip())),
                        html="".join(self._current_parts),
                    )
                )
                self._current_attrs = None
                self._current_parts = []
                self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_attrs is not None:
            self._current_parts.append(html.escape(data))
            if data.strip():
                self._current_text.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._current_attrs is not None:
            self._current_parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._current_attrs is not None:
            self._current_parts.append(f"&#{name};")


class _PlainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    @property
    def text(self) -> str:
        return "".join(self.parts)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"p", "tr", "table", "div"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "tr", "table", "div"}:
            self.parts.append("\n")
