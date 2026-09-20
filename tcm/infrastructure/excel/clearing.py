"""Empty the result cells of test case workbooks, keeping chosen statuses.

Starting a new test round on last round's workbook means wiping what the last
round wrote - result / confirmation date / PIC / ticket / note - on every case
except the ones whose status is worth carrying over. Cancel is the usual one:
a case cancelled out of scope stays out of scope from one round to the next.
The rows themselves, and every other column, are left exactly as they are.

Which rows and columns to touch comes from the workbook's TOOL_DATA sheet, so
`tcm.infrastructure.excel.tool_data` has to have run on a workbook that has
none.

Planning is separate from applying because a cleared cell is not recoverable
from the file: `/api/prepare/clear` shows the plan first and writes only on a
second, explicit request.
"""

import logging
import os
from collections import Counter
from dataclasses import dataclass, field

from openpyxl import load_workbook
from openpyxl.cell import MergedCell
from openpyxl.utils import column_index_from_string

from tcm.infrastructure.excel.reader import TOOL_DATA_SHEET, parse_tool_data
from tcm.domain.case import CASE_COLUMNS, SheetConfig, TestCase
from tcm.domain.status import STATUS
from tcm.infrastructure.excel.workbook import read_sheets


log = logging.getLogger(__name__)

# The cells one test round writes. Cleaning exactly these returns a case to
# "not yet started" without disturbing its number, scope, or description.
CLEARED_FIELDS = (
    "result_col",
    "test_date_col",
    "pic_col",
    "ticket_id_col",
    "note_col",
)
DEFAULT_KEEP = ("Cancel",)

# The `TestCase` fields a test round writes; all five blank means it never ran.
# Derived from CASE_COLUMNS so the two lists cannot fall out of step.
_CLEARED_CASE_FIELDS = tuple(
    field for field, attr in CASE_COLUMNS if attr in CLEARED_FIELDS
)


def _text(value):
    """A cell as trimmed text, or None when blank — `TestCase`'s convention."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass
class Cleaning:
    """One row whose result cells would be emptied."""

    sheet: str
    device: str
    row: int
    status: str
    columns: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "sheet": self.sheet,
            "device": self.device,
            "row": self.row,
            "status": self.status,
            "columns": list(self.columns),
        }


@dataclass
class FilePlan:
    """Every row one workbook would have cleared, and what was left alone."""

    items: list[Cleaning] = field(default_factory=list)
    kept: Counter = field(default_factory=Counter)

    def to_dict(self) -> dict:
        """The plan as JSON, summarised per device block.

        The rows themselves are not sent: a folder of real workbooks runs to
        tens of thousands of them, and what a person checks before allowing the
        write is the shape of the plan, not every row in it.
        """
        blocks = Counter((item.sheet, item.device) for item in self.items)
        return {
            "rows": len(self.items),
            "blocks": [
                {"sheet": sheet, "device": device, "rows": count}
                for (sheet, device), count in blocks.items()
            ],
            "by_status": dict(Counter(item.status for item in self.items)),
            "kept": dict(self.kept),
        }


def blank(value) -> bool:
    """Return whether a workbook cell value should be treated as blank."""

    return value is None or str(value).strip() == ""


def plan_sheet(values: list[tuple], config: SheetConfig, keep: set[str],
               file_name: str = "") -> FilePlan:
    """Add one device block's clearable rows to a plan.

    ``values`` holds cached cell values, so a result produced by a formula is
    classified on what it shows rather than on its formula text. Rows whose five
    result cells are already blank are skipped - there is nothing to clean and
    listing them would bury the rows that matter.
    """

    letters = {name: getattr(config, name) for name in CLEARED_FIELDS}

    # Every column, not just the five that get cleared: a status can be derived
    # from the rest of the row (Out Of Scope is a Cancel with no PIC), so the
    # row has to be classified whole or the plan would report a status the
    # views never show.
    indexes = {
        field: column_index_from_string(getattr(config, attr)) - 1
        for field, attr in CASE_COLUMNS
    }

    plan = FilePlan()

    for row_num in range(config.start_row, config.end_row + 1):
        row = values[row_num - 1] if 0 <= row_num - 1 < len(values) else ()
        cells = {
            field: row[index] if index < len(row) else None
            for field, index in indexes.items()
        }

        if all(blank(cells[field]) for field in _CLEARED_CASE_FIELDS):
            continue

        status = STATUS.classify_case(TestCase(
            file_name=file_name,
            sheet=config.sheet,
            device=config.device,
            row_num=row_num,
            **{field: _text(cells[field]) for field, _ in CASE_COLUMNS},
        ))
        if status in keep:
            plan.kept[status] += 1
            continue

        plan.items.append(
            Cleaning(
                sheet=config.sheet,
                device=config.device,
                row=row_num,
                status=status,
                columns=tuple(letters[name] for name in CLEARED_FIELDS),
            )
        )

    return plan


def plan_file(path: str, keep: set[str]) -> FilePlan:
    """Plan which rows of one workbook would be cleared.

    Raises:
        ValueError: If the workbook has no usable TOOL_DATA sheet.
    """

    name = os.path.basename(path)
    configs = parse_tool_data(path)
    sheets = read_sheets(path)

    plan = FilePlan()
    for config in configs:
        if config.sheet not in sheets:
            log.warning(
                "[%s] %s names sheet %r, which the workbook does not have",
                name,
                TOOL_DATA_SHEET,
                config.sheet,
            )
            continue

        sheet_plan = plan_sheet(sheets[config.sheet], config, keep, file_name=name)
        plan.items.extend(sheet_plan.items)
        plan.kept.update(sheet_plan.kept)

    return plan


def apply_plan(path: str, plan: FilePlan, out_path: str | None = None) -> str:
    """Blank the planned cells.

    Loaded with formulas intact, so only the targeted cells change. Every other
    workbook path is saved back as it was.
    """

    wb = load_workbook(path)
    dest = out_path or path

    try:
        for item in plan.items:
            ws = wb[item.sheet]
            for letter in item.columns:
                cell = ws[f"{letter}{item.row}"]

                # A merged range only holds its value in the top-left cell; the
                # rest are read-only stand-ins.
                if isinstance(cell, MergedCell):
                    continue

                cell.value = None

        wb.save(dest)
    finally:
        wb.close()

    return dest
