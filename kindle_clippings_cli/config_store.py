from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


def default_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / "calibre-kindle-clippings" / "config.json"
    return Path.home() / ".config" / "calibre-kindle-clippings" / "config.json"


class ConfigStore:
    def __init__(self, path: str | None = None) -> None:
        self.path = Path(path) if path else default_config_path()
        self.data: dict[str, Any] = {}

    def load(self) -> None:
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as handle:
                self.data = json.load(handle)
        else:
            self.data = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(self.data, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")

    def library_key(self, library_path: str) -> str:
        return str(Path(library_path).expanduser().resolve())

    def library_config(self, library_path: str) -> dict[str, Any]:
        libraries = self.data.setdefault("libraries", {})
        return libraries.setdefault(self.library_key(library_path), {})

    def get_destination(self, library_path: str) -> str | None:
        return self.library_config(library_path).get("destination_field")

    def set_destination(self, library_path: str, field: str) -> None:
        self.library_config(library_path)["destination_field"] = field

    def get_mapping(self, library_path: str, source_key: str) -> int | None:
        mappings = self.library_config(library_path).setdefault("book_mappings", {})
        value = mappings.get(source_key)
        if isinstance(value, dict):
            value = value.get("book_id")
        return int(value) if value is not None else None

    def set_mapping(
        self,
        library_path: str,
        source_key: str,
        book_id: int,
        source_title: str,
        source_author: str | None,
        calibre_title: str,
        calibre_authors: list[str],
    ) -> None:
        mappings = self.library_config(library_path).setdefault("book_mappings", {})
        mappings[source_key] = {
            "book_id": int(book_id),
            "source_title": source_title,
            "source_author": source_author,
            "calibre_title": calibre_title,
            "calibre_authors": calibre_authors,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
