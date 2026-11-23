import unittest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from kindle_clippings_cli.config_store import ConfigStore, default_config_path
from kindle_clippings_cli.matching import confident_match, rank_candidates
from kindle_clippings_cli.models import BookAnnotations, CalibreBook
from kindle_clippings_cli.parser import group_clippings, parse_bytes
from kindle_clippings_cli.render import classify_conflicts, merge_destination_html, render_annotation


SAMPLE = b"""The Valley of the Moon (Jack London)
- Your Highlight Location 1024-25 | Added on Sunday, February 06, 2011, 10:03 AM

highlight text
==========
The Valley of the Moon (Jack London)
- Your Note Loc. 1026 | Added on Sunday, February 06, 2011, 10:04 AM

note text
==========
The Valley of the Moon (Jack London)
- Your Bookmark Location 1027 | Added on Sunday, February 06, 2011, 10:05 AM


==========
"""


class ParserTests(unittest.TestCase):
    def test_underlines_use_highlight_representation(self):
        highlights, _ = parse_bytes(SAMPLE)
        underlines, issues = parse_bytes(SAMPLE.replace(b"Your Highlight", b"Your Underline"))
        self.assertEqual([], issues)
        self.assertEqual("highlight", underlines[0].kind)
        self.assertEqual(render_annotation(highlights[0]).html, render_annotation(underlines[0]).html)
        self.assertEqual(render_annotation(highlights[0]).annotation_hash, render_annotation(underlines[0]).annotation_hash)

    def test_parse_and_group_kindle_clippings(self):
        clippings, issues = parse_bytes(SAMPLE)

        self.assertEqual([], issues)
        self.assertEqual(3, len(clippings))
        self.assertEqual("highlight", clippings[0].kind)
        self.assertEqual(1024, clippings[0].begin)
        self.assertEqual(1025, clippings[0].end)
        self.assertEqual("note", clippings[1].kind)
        self.assertEqual("bookmark", clippings[2].kind)

        groups = group_clippings([clipping for clipping in clippings if clipping.kind != "bookmark"])
        self.assertEqual(1, len(groups))
        self.assertEqual(2, len(groups[0].clippings))


class MatchingTests(unittest.TestCase):
    def test_structured_titles_beat_unrelated_fuzzy_candidates(self):
        cases = [
            ("Practical Gardening", "Alex Morgan", "Practical Gardening: A Guide to Plants"),
            ("Practical Gardening (Classic Edition)", "Morgan, Alex", "Practical Gardening"),
            ("Practical Gardening - Alex Morgan", None, "Practical Gardening"),
            ("Garden, The - Alex Morgan", None, "The Garden"),
            ("Practical Gardening_ A Guide - Alex Morgan", None, "Practical Gardening: A Guide"),
            ("Practical Gardening: The Basics", "Alex Morgan", "Practical Gardening: The Basics: An Illustrated Guide"),
        ]
        for title, author, target in cases:
            with self.subTest(title=title):
                source = BookAnnotations(key="x", title=title, author=author)
                candidates = rank_candidates(source, [
                    CalibreBook(book_id=1, title="Gardens and Plants", authors=["Someone Else"]),
                    CalibreBook(book_id=2, title=target, authors=["Alex Morgan"]),
                ])
                self.assertEqual(2, confident_match(candidates).book.book_id)

    def test_uncertain_editions_and_authors_require_a_choice(self):
        cases = [
            ("Practical Gardening: Summary", "Alex Morgan", "Practical Gardening", "Alex Morgan"),
            ("A Comprehensive Guide to Growing Flowers and Vegetables: Summary", "Alex Morgan", "A Comprehensive Guide to Growing Flowers and Vegetables", "Alex Morgan"),
            ("Practical Gardening: Volume III", "Alex Morgan", "Practical Gardening", "Alex Morgan"),
            ("Garden", "Alex Morgan", "Garden: A Guide to Plants", "Alex Morgan"),
            ("Practical Gardening: Flowers", "Alex Morgan", "Practical Gardening: Vegetables", "Alex Morgan"),
            ("Practical Gardening", "Alex Morgan", "Practical Gardening: A Guide", "Taylor Smith"),
            ("Practical Gardening", "Alex Morgan", "Practical Gardening: A Guide", ""),
        ]
        for title, author, target, target_author in cases:
            with self.subTest(title=title, target_author=target_author):
                candidates = rank_candidates(BookAnnotations(key="x", title=title, author=author), [
                    CalibreBook(book_id=2, title=target, authors=[target_author]),
                ])
                self.assertIsNone(confident_match(candidates))

    def test_multiple_editions_remain_ambiguous(self):
        source = BookAnnotations(key="x", title="Practical Gardening", author="Alex Morgan")
        candidates = rank_candidates(source, [
            CalibreBook(book_id=1, title="Practical Gardening: First Edition", authors=["Alex Morgan"]),
            CalibreBook(book_id=2, title="Practical Gardening: Second Edition", authors=["Alex Morgan"]),
        ])
        self.assertIsNone(confident_match(candidates))

    def test_ranks_exact_title_and_author_as_confident(self):
        source = BookAnnotations(key="x", title="The Valley of the Moon", author="Jack London")
        books = [
            CalibreBook(book_id=1, title="The Valley of Fear", authors=["Arthur Conan Doyle"]),
            CalibreBook(book_id=2, title="The Valley of the Moon", authors=["Jack London"]),
        ]

        candidates = rank_candidates(source, books)

        self.assertEqual(2, candidates[0].book.book_id)
        self.assertIsNotNone(confident_match(candidates))


class RenderTests(unittest.TestCase):
    def test_duplicate_annotation_is_not_reinserted(self):
        clipping = parse_bytes(SAMPLE)[0][0]
        rendered = render_annotation(clipping)
        existing = '<div class="user_annotations" style="margin:0">' + rendered.html + "</div>"

        conflicts, duplicates = classify_conflicts(existing, [rendered], 1, "Book")
        merged, new_count, duplicate_count = merge_destination_html(existing, [rendered], conflicts)

        self.assertEqual([], conflicts)
        self.assertEqual(1, duplicates)
        self.assertEqual(0, new_count)
        self.assertEqual(1, duplicate_count)
        self.assertEqual(1, merged.count('class="annotation"'))

    def test_same_location_different_text_is_conflict_and_keeps_existing_by_default(self):
        first, _ = parse_bytes(SAMPLE)
        incoming = render_annotation(first[0])
        changed = render_annotation(first[0])
        changed.html = changed.html.replace("highlight text", "changed text")
        changed.annotation_hash = "changed"
        existing = '<div class="user_annotations" style="margin:0">' + incoming.html + "</div>"

        conflicts, _ = classify_conflicts(existing, [changed], 1, "Book")
        merged, new_count, _ = merge_destination_html(existing, [changed], conflicts)

        self.assertEqual(1, len(conflicts))
        self.assertEqual("keep", conflicts[0].resolution)
        self.assertEqual(0, new_count)
        self.assertIn("highlight text", merged)
        self.assertNotIn("changed text", merged)


class ConfigStoreTests(unittest.TestCase):
    def test_xdg_config_and_library_specific_mapping_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}):
                self.assertEqual(Path(directory) / "calibre-kindle-clippings/config.json", default_config_path())
                store = ConfigStore()
                store.set_mapping("/library", "summary|writer", 42, "Summary", "Writer", "Original", ["Writer"])
                store.save()
                restored = ConfigStore()
                restored.load()
                self.assertEqual(42, restored.get_mapping("/library", "summary|writer"))
                self.assertIsNone(restored.get_mapping("/other-library", "summary|writer"))

    def test_mapping_supports_readable_records_and_old_integer_values(self):
        store = ConfigStore()
        store.data = {}

        store.set_mapping(
            "/library",
            "source-key",
            42,
            "Source Title",
            "Source Author",
            "Calibre Title",
            ["Calibre Author"],
        )

        self.assertEqual(42, store.get_mapping("/library", "source-key"))
        record = store.library_config("/library")["book_mappings"]["source-key"]
        self.assertEqual("Source Title", record["source_title"])
        self.assertEqual("Calibre Title", record["calibre_title"])

        store.library_config("/library")["book_mappings"]["old-key"] = 7
        self.assertEqual(7, store.get_mapping("/library", "old-key"))


if __name__ == "__main__":
    unittest.main()
