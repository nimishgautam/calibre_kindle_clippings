#!/usr/bin/env python3
r"""Launcher for running the standalone importer with calibre-debug.

Usage:
    calibre-debug -e calibre_kindle_clippings.py -- --clippings /path/My\ Clippings.txt --library /path/Library
"""

from __future__ import annotations

import os
import sys


ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from kindle_clippings_cli.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
