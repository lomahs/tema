"""Where each aggregate value lands in the SharePoint report workbook.

The report file already exists and is formatted by hand, so the app must be told
which of its columns holds what. That mapping is a JSON file rather than code,
for the same reason `parser/result_status.json` is: changing the report's shape
should not mean editing Python.

A column is either a named field of the dataset, or `{"expand": "statuses"}`,
which becomes one column per status **in taxonomy order**. Flagging a new status
in `parser/result_status.json` therefore widens the report on its own.
"""
import json
import logging
import os
from dataclasses import dataclass

from openpyxl.utils import column_index_from_string, get_column_letter

from parser.status import STATUS

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "report_layout.json")

#: The column every sheet must carry: it is the key the publisher deletes on,
#: so re-running on the same day replaces that day's rows instead of doubling them.
RUN_DATE = "run_date"

#: Fields each dataset offers, beyond the status columns an expansion adds.
#: Names match the keys `aggregate` puts in its row dicts.
DATASET_FIELDS = {
    "summary": [RUN_DATE, "file", "device", "total"],
    "daily": [RUN_DATE, "date", "file", "device", "pic", "total"],
    "issues": [RUN_DATE, "file", "sheet", "device", "row", "case_no", "scope",
               "status", "result", "test_date", "pic", "ticket_id", "note"],
}

#: Datasets whose rows are buckets, and so have a count per status.
COUNTED_DATASETS = ("summary", "daily")


@dataclass(frozen=True)
class Column:
    """One report column: a dataset field, or the count of one status."""

    field: str
    is_status: bool = False


@dataclass(frozen=True)
class SheetLayout:
    """One dataset's destination: which sheet, which row, which columns."""

    dataset: str
    sheet: str
    header_row: int
    first_column: str
    columns: list[Column]
    run_date_index: int

    @property
    def width(self) -> int:
        return len(self.columns)

    @property
    def first_column_index(self) -> int:
        """1-based Excel column number of the leftmost written column."""
        return column_index_from_string(self.first_column)

    @property
    def run_date_column(self) -> str:
        """Excel column letter holding `run_date`, which dedupe scans."""
        return get_column_letter(self.first_column_index + self.run_date_index)


class ReportLayout:
    """The destination of every dataset, validated up front."""

    def __init__(self, sheets: list[SheetLayout]):
        self.sheets = sheets

    @classmethod
    def load(cls, path: str = DEFAULT_CONFIG_PATH, status_set=STATUS) -> "ReportLayout":
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return cls.from_dict(raw, status_set=status_set, source=path)

    @classmethod
    def from_dict(cls, raw: dict, status_set=STATUS, source: str = "<dict>") -> "ReportLayout":
        entries = raw.get("sheets")
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"{source}: 'sheets' must be a non-empty list")

        sheets: list[SheetLayout] = []
        for i, entry in enumerate(entries):
            sheets.append(_parse_sheet(entry, i, status_set, source))

        seen = set()
        for sheet in sheets:
            if sheet.sheet in seen:
                raise ValueError(f"{source}: duplicate sheet '{sheet.sheet}'")
            seen.add(sheet.sheet)

        return cls(sheets)


def _parse_sheet(entry, index: int, status_set, source: str) -> SheetLayout:
    where = f"{source}: sheets[{index}]"
    if not isinstance(entry, dict):
        raise ValueError(f"{where} must be an object")

    dataset = entry.get("dataset")
    if dataset not in DATASET_FIELDS:
        raise ValueError(
            f"{where} names unknown dataset {dataset!r}; "
            f"expected one of {sorted(DATASET_FIELDS)}"
        )

    sheet = entry.get("sheet")
    if not isinstance(sheet, str) or not sheet.strip():
        raise ValueError(f"{where} needs a non-empty 'sheet'")
    sheet = sheet.strip()

    header_row = entry.get("header_row", 1)
    if not isinstance(header_row, int) or isinstance(header_row, bool) or header_row < 1:
        raise ValueError(f"{where} needs 'header_row' to be an integer >= 1, got {header_row!r}")

    first_column = str(entry.get("first_column", "A")).strip().upper()
    try:
        column_index_from_string(first_column)
    except (ValueError, TypeError):
        raise ValueError(
            f"{where} needs 'first_column' to be a column letter, got {first_column!r}"
        ) from None

    raw_columns = entry.get("columns")
    if not isinstance(raw_columns, list) or not raw_columns:
        raise ValueError(f"{where} needs 'columns' to be a non-empty list")

    known = DATASET_FIELDS[dataset]
    columns: list[Column] = []
    for j, col in enumerate(raw_columns):
        columns.extend(_parse_column(col, f"{where}.columns[{j}]", dataset, known, status_set))

    run_date_positions = [k for k, c in enumerate(columns) if not c.is_status and c.field == RUN_DATE]
    if len(run_date_positions) != 1:
        raise ValueError(
            f"{where} must carry exactly one '{RUN_DATE}' column, got {len(run_date_positions)}"
        )

    return SheetLayout(
        dataset=dataset,
        sheet=sheet,
        header_row=header_row,
        first_column=first_column,
        columns=columns,
        run_date_index=run_date_positions[0],
    )


def _parse_column(col, where: str, dataset: str, known: list[str], status_set) -> list[Column]:
    if not isinstance(col, dict):
        raise ValueError(f"{where} must be an object")

    has_field, has_expand = "field" in col, "expand" in col
    if has_field == has_expand:
        raise ValueError(f"{where} needs either 'field' or 'expand', not both or neither")

    if has_expand:
        if col["expand"] != "statuses":
            raise ValueError(f"{where} names unknown expansion {col['expand']!r}")
        if dataset not in COUNTED_DATASETS:
            raise ValueError(
                f"{where} cannot expand statuses on dataset '{dataset}': "
                f"its rows are individual cases, not status buckets"
            )
        # `counted`, not `keys`: a status the taxonomy excludes from the total
        # gets no report column, which keeps the sheet's status columns adding
        # up to its `total` and keeps the workbook's width unchanged when the
        # taxonomy grows an excluded status.
        return [Column(key, is_status=True) for key in status_set.counted]

    field = col["field"]
    if field not in known:
        raise ValueError(
            f"{where}: {field!r} is not a field of dataset {dataset!r}; expected one of {known}"
        )
    return [Column(field)]


def _load_default() -> ReportLayout:
    from config import REPORT_LAYOUT_CONFIG

    path = REPORT_LAYOUT_CONFIG
    try:
        return ReportLayout.load(path)
    except Exception as e:
        if path == DEFAULT_CONFIG_PATH:
            raise
        log.error("Failed to load report layout '%s': %s — using defaults", path, e)
        return ReportLayout.load(DEFAULT_CONFIG_PATH)


LAYOUT = _load_default()
