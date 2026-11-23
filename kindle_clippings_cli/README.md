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

- Imports Kindle highlights, underlines (as highlights), and notes. Bookmarks are skipped and counted in the report.
- Uses Calibre's Python API, so it should be run with `calibre-debug`.
- Chooses an annotations destination by inspecting comments-type columns and existing annotation content, then asks for confirmation in interactive mode.
- Ranks Calibre book matches by title and author. Ambiguous matches are resolved with a chooser or manual search.
- Recognizes subtitle and parenthetical suffix differences, trailing articles, and embedded `Title - Author` names when supported by the library's author metadata. Different subtitles, summaries, numbered volumes, short titles, and uncertain author names can still require a manual choice. Multiple plausible editions remain ambiguous.
- Saves accepted book matches in the local config file, including the source title/author and Calibre book ID/title/authors. Skipped books are not saved, so they will be asked about again on a later run.
- Keeps existing matching annotations by default.
- Shows conflicts in the review console; use `conflicts`, `conflict N`, `import N`, and `keep N` before `apply`.
- Copies `metadata.db` to a timestamped backup before writing.
- Writes a JSON report with match decisions, inserted counts, skips, conflicts, parse issues, and backup path.

## Local book mappings

Preferences live in `$XDG_CONFIG_HOME/calibre-kindle-clippings/config.json`, or
`~/.config/calibre-kindle-clippings/config.json` when `XDG_CONFIG_HOME` is unset.
Use `--config PATH` to override this location. These are local files, outside the
repository, and mappings are scoped to the absolute Calibre library path.

To map a Kindle-only summary or volume to another form in Calibre, run
interactively and select the intended book (or use manual search). That choice
is saved after accepting the review, including during a dry run, and reused on
later runs. Saved mappings take priority over automatic matching. Remove an
entry from `book_mappings` to choose again. Skipped books are not remembered.

Mapping keys are the normalized `source_key` values in the JSON report. Entries
include the Calibre `book_id` and readable source and target metadata. For example:

```json
{
  "libraries": {
    "/path/to/Calibre Library": {
      "book_mappings": {
        "example title summary|example author": {
          "book_id": 42,
          "source_title": "Example Title: Summary",
          "source_author": "Example Author",
          "calibre_title": "Example Title",
          "calibre_authors": ["Example Author"]
        }
      }
    }
  }
}
```

Mappings refer to IDs in that library; review them if you replace or rebuild the
library database. A missing target ID falls back to normal matching.
