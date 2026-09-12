"""Detect a workbook's TOOL_DATA rows from the layout of its test case sheets.

Real test case sheets carry no TOOL_DATA of their own the first time they are
handed to this tool; a human copy-pastes column letters into TOOL_DATA by eye.
This module automates that first pass:

1. A device block is announced by a cell naming a device ("Pad(Flex)",
   "27系Phone") a few rows above the header.
2. The header row is the one holding both a test-number cell and a scope cell.
3. Each device's five result columns are read from the header row itself or
   the row directly below it - sheets do both across the sample set.
4. Data starts two rows below the header row and runs to the sheet's last
   non-blank row.

Every label matched along the way comes from `parser/sheet_labels.json`
via `parser.sheet_labels`, so adapting to differently-headed sheets is a
config edit rather than a change here.

The result is a best-effort list of `SheetConfig`; sheets where a header row
has no device block, or a device block is missing one of the five result
columns, are skipped and reported back separately so a human can finish them.
"""

import logging
from dataclasses import dataclass

from openpyxl.utils import get_column_letter

from parser.models import SheetConfig
from parser.sheet_labels import LABELS, RESULT_FIELDS


log = logging.getLogger(__name__)


@dataclass
class Unresolved:
    """A header row this pass could not turn into (a) full device config(s)."""

    sheet: str
    row: int
    reason: str


def _norm(value) -> str:
    """Cell text, trimmed of ASCII and ideographic (U+3000) whitespace."""

    if value is None:
        return ""
    return str(value).strip().strip("\u3000").strip()


def _is_header_label(field: str, value) -> bool:
    text = _norm(value)
    return bool(text) and LABELS.matches_header(field, text)


def _is_device_label(value) -> bool:
    text = _norm(value)
    return bool(text) and LABELS.is_device(text)


def _is_result_column_label(field: str, value) -> bool:
    text = _norm(value)
    return bool(text) and LABELS.matches_result_column(field, text)


def _find_header_rows(rows: list[tuple]) -> list[tuple[int, int, int]]:
    """Rows carrying both a test-number and a scope cell: `(row_idx, no_col, scope_col)`."""

    headers = []
    for row_idx, row in enumerate(rows[:LABELS.max_header_scan_rows]):
        no_col = None
        scope_col = None
        for col_idx, value in enumerate(row):
            if no_col is None and _is_header_label("test_no_col", value):
                no_col = col_idx
            elif no_col is not None and scope_col is None and _is_header_label("scope_col", value):
                scope_col = col_idx
                break

        if no_col is not None and scope_col is not None:
            headers.append((row_idx, no_col, scope_col))
    return headers


def _find_device_row(rows: list[tuple], header_idx: int) -> list[tuple[int, str]]:
    """Row above `header_idx` naming devices, as `(col_idx, device_name)`.

    Picks the row with the most device cells in the window, not just the
    nearest one - a stray single "iPhone/iPad" label in an unrelated summary
    column (seen right above some headers) would otherwise outrank the real,
    multi-device row further up.
    """

    floor = max(header_idx - LABELS.device_row_window, -1)
    best: list[tuple[int, str]] = []
    for row_idx in range(header_idx - 1, floor, -1):
        row = rows[row_idx]
        devices = [
            (col_idx, _norm(value))
            for col_idx, value in enumerate(row)
            if _is_device_label(value)
        ]
        if len(devices) > len(best):
            best = sorted(devices)
    return best


def _scan_sub_columns(rows: list[tuple], header_idx: int, start_col: int, end_col: int) -> dict[str, int]:
    """Column index for each of the 5 result fields, within `[start_col, end_col)`."""

    found: dict[str, int] = {}
    for row_idx in (header_idx, header_idx + 1):
        if row_idx >= len(rows):
            continue
        row = rows[row_idx]
        for col_idx in range(start_col, min(end_col, len(row))):
            value = row[col_idx]
            for field in RESULT_FIELDS:
                if field not in found and _is_result_column_label(field, value):
                    found[field] = col_idx
    return found


def _last_data_row(rows: list[tuple], after_idx: int, columns: range) -> int:
    """1-based Excel row number of the last non-blank row within `columns`."""

    for row_idx in range(len(rows) - 1, after_idx, -1):
        row = rows[row_idx]
        for col_idx in columns:
            if col_idx < len(row) and _norm(row[col_idx]):
                return row_idx + 1

    # Nothing below the header row: report a 1-row (empty) span rather than
    # end_row < start_row, which SheetConfig would reject.
    return after_idx + 2


def detect_sheet_configs(sheet_name: str, rows: list[tuple]) -> tuple[list[SheetConfig], list[Unresolved]]:
    """Detect TOOL_DATA rows for one already-read sheet (list of value tuples)."""

    configs: list[SheetConfig] = []
    unresolved: list[Unresolved] = []

    for header_idx, no_col, scope_col in _find_header_rows(rows):
        excel_header_row = header_idx + 1
        devices = _find_device_row(rows, header_idx)
        if not devices:
            unresolved.append(Unresolved(sheet_name, excel_header_row, "no device row (pad/phone) found above header"))
            continue

        row_width = max(len(rows[header_idx]), len(rows[header_idx + 1]) if header_idx + 1 < len(rows) else 0)
        start_row = excel_header_row + 2
        end_row = None  # computed lazily, shared by every device in this section

        for position, (device_col, device_name) in enumerate(devices):
            block_end = devices[position + 1][0] if position + 1 < len(devices) else row_width
            sub_cols = _scan_sub_columns(rows, header_idx, device_col, block_end)
            missing = [field for field in RESULT_FIELDS if field not in sub_cols]
            if missing:
                unresolved.append(
                    Unresolved(
                        sheet_name,
                        excel_header_row,
                        f"device '{device_name}': missing column(s) {', '.join(missing)}",
                    )
                )
                continue

            if end_row is None:
                span = range(no_col, max(c for c in sub_cols.values()) + 1)
                end_row = _last_data_row(rows, header_idx, span)

            configs.append(
                SheetConfig(
                    sheet=sheet_name,
                    device=device_name,
                    start_row=start_row,
                    end_row=end_row,
                    test_no_col=get_column_letter(no_col + 1),
                    scope_col=get_column_letter(scope_col + 1),
                    result_col=get_column_letter(sub_cols["result_col"] + 1),
                    test_date_col=get_column_letter(sub_cols["test_date_col"] + 1),
                    pic_col=get_column_letter(sub_cols["pic_col"] + 1),
                    ticket_id_col=get_column_letter(sub_cols["ticket_id_col"] + 1),
                    note_col=get_column_letter(sub_cols["note_col"] + 1),
                )
            )

    return configs, unresolved


def detect_workbook_configs(sheets: dict[str, list[tuple]]) -> tuple[list[SheetConfig], list[Unresolved]]:
    """Detect TOOL_DATA rows across every already-read sheet in a workbook.

    Args:
        sheets: Sheet name -> rows (each row a tuple of cell values, as from
            `openpyxl`'s `iter_rows(values_only=True)`). The TOOL_DATA sheet
            itself, if present, should not be included.
    """

    all_configs: list[SheetConfig] = []
    all_unresolved: list[Unresolved] = []
    for sheet_name, rows in sheets.items():
        configs, unresolved = detect_sheet_configs(sheet_name, rows)
        all_configs.extend(configs)
        all_unresolved.extend(unresolved)
        log.info("[%s] Detected %d device config(s), %d unresolved", sheet_name, len(configs), len(unresolved))
    return all_configs, all_unresolved
