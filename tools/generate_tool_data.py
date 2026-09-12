"""Detect a workbook's TOOL_DATA rows from its test case sheets and, optionally,
write them into the workbook.

By default this only prints a preview - the detected rows plus anything it
could not resolve - so a human can sanity-check before anything is written.
Pass --write to actually add/replace the TOOL_DATA sheet in the file(s).

The detection and the writing live in `prepare.tool_data`, which the app's
`/api/prepare/tool-data` endpoint calls too, so the sheet this writes and the
one the Setup drawer writes cannot drift.

Usage:
    python -m tools.generate_tool_data --file sample/foo.xlsx
    python -m tools.generate_tool_data --folder sample
    python -m tools.generate_tool_data --file sample/foo.xlsx --write
    python -m tools.generate_tool_data --file sample/foo.xlsx --write --out sample/foo.generated.xlsx
"""

import argparse
import logging
import os
import sys

from parser.excel_reader import TOOL_DATA_SHEET, find_workbooks, parse_tool_data
from prepare.tool_data import detect_file, diff_configs, write_tool_data_sheet
from prepare.workbook import has_tool_data


log = logging.getLogger(__name__)


def _print_diff(path: str, configs: list) -> None:
    """Say what writing would change about the TOOL_DATA already in the file."""

    try:
        existing = parse_tool_data(path)
    except Exception as e:
        print(f"  existing {TOOL_DATA_SHEET} is unreadable ({e}); writing would replace it")
        return

    diff = diff_configs(existing, configs)
    if not diff.differs:
        print(f"  existing {TOOL_DATA_SHEET} matches detection; nothing would change")
        return

    for block in diff.changed:
        changes = ", ".join(
            f"{f['field']} {f['existing']}->{f['detected']}" for f in block["fields"]
        )
        print(f"  changed  {block['sheet']!r}:{block['device']!r}  {changes}")
    for sheet, device in diff.only_existing:
        print(f"  dropped  {sheet!r}:{device!r}  (in the sheet, not detected)")
    for sheet, device in diff.only_detected:
        print(f"  added    {sheet!r}:{device!r}  (detected, not in the sheet)")


def process_file(path: str, write: bool, out_path: str | None) -> None:
    name = os.path.basename(path)
    configs, unresolved = detect_file(path)

    print(f"\n=== {name} ===")
    if configs:
        print(f"{len(configs):>3} device config(s) detected:")
        for cfg in configs:
            print(
                f"  {cfg.sheet!r:<30} {cfg.device!r:<20} rows {cfg.start_row}-{cfg.end_row}  "
                f"no={cfg.test_no_col} scope={cfg.scope_col} result={cfg.result_col} "
                f"date={cfg.test_date_col} pic={cfg.pic_col} ticket={cfg.ticket_id_col} note={cfg.note_col}"
            )
    else:
        print("  no device config detected")

    if unresolved:
        print(f"{len(unresolved):>3} unresolved header(s):")
        for u in unresolved:
            print(f"  sheet={u.sheet!r} row={u.row}: {u.reason}")

    if configs and has_tool_data(path):
        _print_diff(path, configs)

    if write:
        if not configs:
            log.warning("[%s] Nothing detected, skipping write", name)
            return
        dest = write_tool_data_sheet(path, configs, out_path)
        print(f"  -> wrote {TOOL_DATA_SHEET} to {dest!r}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", action="append", dest="files", help="One workbook path; repeatable")
    group.add_argument("--folder", help="Scan every .xlsx under this folder, recursively")
    p.add_argument("--write", action="store_true", help="Write the detected TOOL_DATA sheet into the file(s)")
    p.add_argument("--out", help="Write to this path instead of overwriting (only with a single --file)")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.out and (args.folder or (args.files and len(args.files) > 1)):
        p.error("--out only makes sense with a single --file")

    paths = find_workbooks(args.folder) if args.folder else args.files

    if not paths:
        log.warning("No .xlsx files found")
        return 1

    for path in paths:
        process_file(path, write=args.write, out_path=args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
