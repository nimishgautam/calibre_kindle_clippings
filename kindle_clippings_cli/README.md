# Kindle Clippings CLI

Standalone importer for applying Kindle `My Clippings.txt` highlights and notes to a Calibre library.

Run it with Calibre's Python environment:

```bash
calibre-debug -e calibre_kindle_clippings.py -- \
  --clippings "/path/to/My Clippings.txt" \
  --library "/path/to/Calibre Library"
```

Useful options:

```bash
--dry-run            Build the plan and write the JSON report, but do not change Calibre metadata.
--non-interactive    Use defaults, skip ambiguous matches, and do not prompt.
--destination FIELD  Use a known destination, e.g. Comments or #annotations.
--report PATH        Write the JSON report to a specific path.
--config PATH        Use a specific local config file.
```

Behavior:

- Imports Kindle highlights and notes. Bookmarks are skipped and counted in the report.
- Uses Calibre's Python API, so it should be run with `calibre-debug`.
- Chooses an annotations destination by inspecting comments-type columns and existing annotation content, then asks for confirmation in interactive mode.
- Ranks Calibre book matches by title and author. Ambiguous matches are resolved with a chooser or manual search.
- Saves accepted book matches in the local config file, including the source title/author and Calibre book ID/title/authors. Skipped books are not saved, so they will be asked about again on a later run.
- Keeps existing matching annotations by default.
- Shows conflicts in the review console; use `conflicts`, `conflict N`, `import N`, and `keep N` before `apply`.
- Copies `metadata.db` to a timestamped backup before writing.
- Writes a JSON report with match decisions, inserted counts, skips, conflicts, parse issues, and backup path.
