"""Empty the result cells of test case workbooks, keeping chosen statuses.

Starting a new test round on last round's workbook means wiping what the last
round wrote - result / confirmation / ticket / notes - on every case except the
ones marked Cancel, which stay out of scope from one round to the next.
The rows themselves, and every other column, are left exactly as they are.

Which rows and columns to touch comes from the workbook's TOOL_DATA sheet, so
run ``tools.generate_tool_data`` first on a workbook that has none.

Previews by default - nothing is written until you pass ``--apply`` - because a
cleared cell is not recoverable from the file.

The planning and the writing live in `prepare.clear`, which the app's
`/api/prepare/clear` endpoint calls too, so this and the Setup drawer clear
exactly the same cells.

Usage:
    python -m tools.clear_results --file sample/foo.xlsx
    python -m tools.clear_results --folder sample --apply
    python -m tools.clear_results --file sample/foo.xlsx --apply --out sample/foo.clean.xlsx
    python -m tools.clear_results --folder sample --keep Cancel --keep Pending --apply
"""

import argparse
import logging
import os
import sys
from collections import Counter

from parser.excel_reader import find_workbooks
from parser.status import STATUS
from prepare.clear import DEFAULT_KEEP, FilePlan, apply_plan, plan_file


log = logging.getLogger(__name__)


def _report(name: str, plan: FilePlan) -> None:
    """Print a short preview/apply report."""

    print(f"\n=== {name} ===")

    if not plan.items:
        print("Nothing to clean")
    else:
        blocks = Counter((item.sheet, item.device) for item in plan.items)
        for (sheet, device), count in blocks.items():
            print(f"{sheet!r}:{device!r} {count:>5} row(s)")

        breakdown = ", ".join(
            f"{status} {count}"
            for status, count in Counter(
                item.status for item in plan.items
            ).most_common()
        )
        print(f"Plan: {len(plan.items)} row(s) to clean ({breakdown})")

    if plan.kept:
        kept = ", ".join(
            f"{status} {count}" for status, count in plan.kept.most_common()
        )
        print(f"Kept: {kept}")


def process_file(path: str, keep: set[str], apply: bool, out_path: str | None) -> int:
    """Return the number of rows cleared, or that would be cleared."""

    name = os.path.basename(path)

    try:
        plan = plan_file(path, keep)
    except Exception as exc:
        print(f"\n=== {name} ===")
        print(f"Skipped: {exc}")
        return 0

    _report(name, plan)

    if apply and plan.items:
        dest = apply_plan(path, plan, out_path)
        print(f"Wrote: {dest}")

    return len(plan.items)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", dest="files", nargs="+", help="One or more .xlsx files")
    group.add_argument("--folder", help="Scan every .xlsx under this folder, recursively")

    parser.add_argument(
        "--keep",
        action="append",
        default=list(DEFAULT_KEEP),
        help=(
            "Status key to leave untouched; repeatable. "
            f"Known keys: {', '.join(STATUS.keys)}"
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write to the workbook instead of previewing only",
    )
    parser.add_argument(
        "--out",
        help="Write to this path instead of overwriting; only with a single --file",
    )

    args = parser.parse_args(argv)

    if args.out and (args.folder or len(args.files) > 1):
        parser.error("--out only makes sense with a single --file")

    unknown = [key for key in args.keep if key not in STATUS.keys]
    if unknown:
        parser.error(
            f"Unknown status key(s) {', '.join(unknown)}; "
            f"expected one of {', '.join(STATUS.keys)}"
        )

    return args


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    args = _parse_args(argv)

    keep = set(args.keep or DEFAULT_KEEP)

    files = find_workbooks(args.folder) if args.folder else args.files

    total = 0
    for path in files:
        total += process_file(path, keep, args.apply, args.out)

    if not args.apply and total:
        print("\nPreview only. Re-run with --apply to write changes.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
