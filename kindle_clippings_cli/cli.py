from __future__ import annotations

import argparse
import sys

from . import __version__
from .config_store import ConfigStore
from .report import default_report_path, write_report
from .workflow import Console, apply_plan, build_plan, persist_matched_books, review_plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="calibre_kindle_clippings.py",
        description="Import Kindle My Clippings annotations into a Calibre library.",
    )
    parser.add_argument("--clippings", required=True, help="Path to Kindle My Clippings.txt")
    parser.add_argument("--library", required=True, help="Path to the Calibre library directory")
    parser.add_argument("--destination", help="Destination field/name, e.g. Comments or #annotations")
    parser.add_argument("--config", help="Path to local CLI config JSON")
    parser.add_argument("--report", help="Path to write JSON report")
    parser.add_argument("--dry-run", action="store_true", help="Build and review the plan without writing to Calibre")
    parser.add_argument("--non-interactive", action="store_true", help="Do not prompt; skip ambiguous matches and use defaults")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    interactive = (not args.non_interactive) and sys.stdin.isatty()
    console = Console(enabled=True)
    config = ConfigStore(args.config)
    config.load()

    try:
        plan = build_plan(
            clippings_path=args.clippings,
            library_path=args.library,
            config=config,
            destination_arg=args.destination,
            interactive=interactive,
            console=console,
        )
        accepted = review_plan(plan, interactive=interactive, console=console)
        if not accepted:
            console.print("Aborted before writing.")
            return 2
        if args.dry_run:
            console.print("Dry run: no Calibre metadata was changed.")
        else:
            apply_plan(plan)
            console.print(f"Updated Calibre metadata. Backup: {plan.backup_path}")

        saved_mappings = persist_matched_books(plan, config)
        report_path = args.report or default_report_path(args.clippings)
        write_report(plan, report_path)
        config.save()
        console.print(f"Saved matched book mappings: {saved_mappings}")
        console.print(f"Report: {report_path}")
        return 0
    except KeyboardInterrupt:
        console.print("\nInterrupted.")
        return 130
    except Exception as exc:
        console.print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
