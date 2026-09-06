"""Writing the three report tables into a workbook that already exists.

Each publish is keyed on `run_date`: rows carrying that date are removed before
the new ones are appended, so running twice in a day replaces the day rather
than doubling it. That also makes a publish safe to retry — which matters,
because there is no way to roll back a half-finished one.
"""
import logging
from datetime import date, datetime, timedelta

import aggregate
from report.builder import build_rows
from report.layout import LAYOUT, ReportLayout, SheetLayout
from sharepoint.links import share_url_to_item
from sharepoint.workbook import Workbook

log = logging.getLogger(__name__)

#: Excel counts days from this date (its 1900 leap year bug included).
EXCEL_EPOCH = date(1899, 12, 30)

#: Which aggregate builds each dataset's rows.
DATASET_ROWS = {
    "summary": lambda cases: aggregate.summary_rows(cases)[0],
    "daily": aggregate.daily_rows,
    "issues": aggregate.issue_rows,
}


class SheetMissing(Exception):
    """The report file has no sheet by the name the layout asks for."""


def publish(cases, workbook, layout: ReportLayout = LAYOUT, run_date=None) -> dict:
    """Replace `run_date`'s rows in every sheet of `layout` with `cases`' totals.

    Args:
        cases: Loaded `TestCase` objects.
        workbook: An open `sharepoint.workbook.Workbook`, or anything offering
            the same operations.
        layout: Which sheet and columns each dataset goes to.
        run_date: The day being published, "YYYY-MM-DD". Defaults to today.

    Returns:
        `{"run_date": ..., "sheets": [{"sheet", "deleted", "appended"}, ...]}`.

    Raises:
        SheetMissing: A sheet named in the layout is not in the workbook. Every
            sheet is checked before anything is written, so a layout that does
            not fit the file leaves it untouched rather than half-updated.
    """
    run_date = run_date or datetime.now().strftime("%Y-%m-%d")

    present = set(workbook.worksheet_names())
    absent = [s.sheet for s in layout.sheets if s.sheet not in present]
    if absent:
        raise SheetMissing(
            f"The report file has no sheet named {', '.join(repr(s) for s in absent)}. "
            f"It has: {', '.join(sorted(present)) or '(none)'}."
        )

    reports = []
    for sheet_layout in layout.sheets:
        rows = build_rows(DATASET_ROWS[sheet_layout.dataset](cases), sheet_layout, run_date)
        reports.append(_publish_sheet(workbook, sheet_layout, rows, run_date))

    return {"run_date": run_date, "sheets": reports}


def _publish_sheet(workbook, layout: SheetLayout, rows: list[list], run_date: str) -> dict:
    table = workbook.table_at(layout.sheet, layout.header_row)
    if table:
        deleted = _replace_in_table(workbook, table, layout, rows, run_date)
    else:
        deleted = _replace_in_range(workbook, layout, rows, run_date)

    log.info("%s: removed %s row(s) for %s, appended %s",
             layout.sheet, deleted, run_date, len(rows))
    return {"sheet": layout.sheet, "deleted": deleted, "appended": len(rows)}


def _replace_in_range(workbook, layout: SheetLayout, rows: list[list], run_date: str) -> int:
    """Range mode: delete this day's blocks bottom-up, then write below the rest."""
    used = workbook.used_range(layout.sheet)
    matches = _matching_rows(used, layout, run_date)

    deleted = 0
    for first_row, count in reversed(_contiguous_blocks(matches)):
        # Bottom-up: deleting shifts everything below it up, which would move
        # the blocks still to come.
        workbook.delete_rows(layout.sheet, first_row, count,
                             layout.first_column_index, layout.width)
        deleted += count

    if rows:
        # Re-read: the deletions above changed where the data now ends.
        last_row = workbook.used_range(layout.sheet).last_row if deleted else used.last_row
        first_row = max(last_row + 1, layout.header_row + 1)
        workbook.write_values(layout.sheet, first_row, layout.first_column_index, rows)

    return deleted


def _matching_rows(used, layout: SheetLayout, run_date: str) -> list[int]:
    """1-based sheet rows below the header whose run_date cell is `run_date`."""
    offset = layout.first_column_index + layout.run_date_index - 1 - used.column_index
    if offset < 0:
        return []

    matches = []
    for i, values in enumerate(used.values):
        row_num = used.first_row + i
        if row_num <= layout.header_row or offset >= len(values):
            continue
        if _normalise_date(values[offset]) == run_date:
            matches.append(row_num)
    return matches


def _replace_in_table(workbook, table: str, layout: SheetLayout,
                      rows: list[list], run_date: str) -> int:
    """Table mode: the table extends its own formatting over the rows it gains."""
    matches = [
        index for index, values in workbook.table_rows(table)
        if layout.run_date_index < len(values)
        and _normalise_date(values[layout.run_date_index]) == run_date
    ]

    # Descending: deleting a row renumbers every row after it.
    for index in sorted(matches, reverse=True):
        workbook.table_delete_row(table, index)

    if rows:
        workbook.table_add_rows(table, rows)

    return len(matches)


def _contiguous_blocks(row_numbers: list[int]) -> list[tuple[int, int]]:
    """Collapse sorted row numbers into (first_row, count) runs."""
    blocks = []
    for row in sorted(row_numbers):
        if blocks and row == blocks[-1][0] + blocks[-1][1]:
            blocks[-1] = (blocks[-1][0], blocks[-1][1] + 1)
        else:
            blocks.append((row, 1))
    return blocks


def _normalise_date(value) -> str:
    """Reduce whatever a run_date cell holds to "YYYY-MM-DD", or "" if it holds no date.

    The column is written as text, but a sheet formatted as Date hands the value
    back as an Excel serial number instead — and a re-run must still recognise
    its own rows either way.
    """
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        return (EXCEL_EPOCH + timedelta(days=int(value))).isoformat()

    text = str(value).strip()
    # "2026-09-06 00:00:00" and "2026-09-06T00:00:00" both start with the date.
    return text[:10] if len(text) >= 10 and text[4] == "-" and text[7] == "-" else text


def publish_to_url(cases, client, url: str, run_date=None,
                   layout: ReportLayout = LAYOUT, workbook_factory=None) -> dict:
    """Resolve a pasted SharePoint link, then publish into the workbook behind it.

    All three sheets are written inside one workbook session, so the file sees
    a single logical edit rather than three.

    Args:
        workbook_factory: Builds the workbook from (client, ref). Injectable so
            tests can drive the publish without a session.

    Returns:
        What `publish` returns, plus the `file` and `web_url` it went to.
    """
    factory = workbook_factory or Workbook
    ref = share_url_to_item(client, url)

    with factory(client, ref) as workbook:
        result = publish(cases, workbook, layout=layout, run_date=run_date)

    return {**result, "file": ref.name, "web_url": ref.web_url}
