import os
import glob
import logging
import re
from collections import OrderedDict
from datetime import date, datetime

import pandas as pd
from openpyxl.utils import column_index_from_string

from tcm.domain.case import CASE_COLUMNS, SheetConfig, TestCase
from tcm.domain.scope import SCOPES

log = logging.getLogger(__name__)

TOOL_DATA_SHEET = "TOOL_DATA"

TOOL_DATA_COLUMNS = [
    "sheet", "device", "start_row", "end_row",
    "test_no_col", "scope_col", "result_col", "test_date_col",
    "pic_col", "ticket_id_col", "note_col",
]

# The TOOL_DATA header occupies row 1, so its first data row is Excel row 2.
TOOL_DATA_FIRST_DATA_ROW = 2

# A typo like end_row=1000000 would otherwise allocate a huge frame.
MAX_ROW_SPAN = 100_000

LOCK_FILE_PREFIX = "~$"

# Excel columns holding a date, but typed as text, come through as
# "2026-08-01 00:00:00". Only applied to the test_date field.
_MIDNIGHT_SUFFIX = re.compile(r"[ T]00:00:00(\.0+)?$")

def _cell_text(row, name: str) -> str:
    """A TOOL_DATA cell as trimmed text. Blank cells arrive as NaN, which is
    truthy — so `str(value)` alone would yield the string "nan"."""
    raw = row[name]
    if raw is None or (not isinstance(raw, str) and pd.isna(raw)):
        return ""
    return str(raw).strip()


def _require_int(row, name: str, excel_row: int) -> int:
    text = _cell_text(row, name)
    if not text:
        raise ValueError(f"{TOOL_DATA_SHEET} row {excel_row}: '{name}' is empty")
    try:
        # Excel may hand back "4" or "4.0" depending on how the cell was typed.
        return int(float(text))
    except ValueError:
        raise ValueError(
            f"{TOOL_DATA_SHEET} row {excel_row}: '{name}' must be a number, got {text!r}"
        ) from None


def _require_column(row, name: str, excel_row: int) -> str:
    letter = _cell_text(row, name).upper()
    if not letter:
        raise ValueError(f"{TOOL_DATA_SHEET} row {excel_row}: '{name}' is empty")
    try:
        column_index_from_string(letter)
    except ValueError:
        raise ValueError(
            f"{TOOL_DATA_SHEET} row {excel_row}: '{name}' is not a column letter, got {letter!r}"
        ) from None
    return letter


def _parse_config_row(row, excel_row: int) -> SheetConfig:
    start_row = _require_int(row, "start_row", excel_row)
    end_row = _require_int(row, "end_row", excel_row)

    if start_row < 1:
        raise ValueError(f"{TOOL_DATA_SHEET} row {excel_row}: 'start_row' must be >= 1, got {start_row}")
    if end_row < start_row:
        raise ValueError(
            f"{TOOL_DATA_SHEET} row {excel_row}: 'end_row' ({end_row}) is before "
            f"'start_row' ({start_row})"
        )
    if end_row - start_row + 1 > MAX_ROW_SPAN:
        raise ValueError(
            f"{TOOL_DATA_SHEET} row {excel_row}: rows {start_row}-{end_row} span more than "
            f"{MAX_ROW_SPAN} rows"
        )

    return SheetConfig(
        sheet=_cell_text(row, "sheet"),
        device=_cell_text(row, "device"),
        start_row=start_row,
        end_row=end_row,
        **{name: _require_column(row, name, excel_row) for _, name in CASE_COLUMNS},
    )


def parse_tool_data(source) -> list[SheetConfig]:
    """Read the TOOL_DATA sheet. `source` is a path or an open `pd.ExcelFile`."""
    label = source if isinstance(source, str) else getattr(source, "io", source)
    log.info("Parsing %s sheet from %s", TOOL_DATA_SHEET, os.path.basename(str(label)))
    try:
        df = pd.read_excel(source, sheet_name=TOOL_DATA_SHEET, dtype=str)
    except ValueError:
        raise ValueError(f"Sheet '{TOOL_DATA_SHEET}' not found") from None

    df.columns = df.columns.str.strip().str.lower()

    for name in TOOL_DATA_COLUMNS:
        if name not in df.columns:
            raise ValueError(f"Missing column '{name}' in {TOOL_DATA_SHEET}")

    df = df.dropna(subset=["sheet"])

    configs = []
    for position, (_, row) in enumerate(df.iterrows()):
        excel_row = TOOL_DATA_FIRST_DATA_ROW + position
        cfg = _parse_config_row(row, excel_row)
        log.debug("Config: sheet=%s device=%s rows=%s-%s",
                  cfg.sheet, cfg.device, cfg.start_row, cfg.end_row)
        configs.append(cfg)
    log.info("Found %d config(s) in %s", len(configs), TOOL_DATA_SHEET)
    return configs


def _col_idx(letter: str) -> int:
    """Excel column letter -> 0-based DataFrame column index."""
    return column_index_from_string(letter) - 1


def _clean(v):
    """Normalise one cell to a trimmed string, or None when it is blank."""
    if v is None:
        return None
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    if not isinstance(v, str) and pd.isna(v):
        return None
    s = str(v).strip()
    return s or None


def _clean_date(v):
    """Like `_clean`, but drops a midnight time left over from a text date cell."""
    s = _clean(v)
    if s is None:
        return None
    return _MIDNIGHT_SUFFIX.sub("", s).strip() or None


def read_test_cases(df: pd.DataFrame, config: SheetConfig, file_name: str) -> list[TestCase]:
    """Slice one device's columns out of an already-parsed sheet."""
    log.info("[%s] Reading sheet '%s' for device '%s' (rows %d-%d)",
             file_name, config.sheet, config.device, config.start_row, config.end_row)

    col_map = {field: _col_idx(getattr(config, attr)) for field, attr in CASE_COLUMNS}
    width = df.shape[1]
    missing = [attr for field, attr in CASE_COLUMNS if col_map[field] >= width]
    if missing:
        log.warning("[%s] Sheet '%s' has only %d column(s); %s out of range",
                    file_name, config.sheet, width, ", ".join(missing))

    # start_row/end_row are 1-based inclusive Excel rows; the frame is 0-based.
    rows = df.iloc[config.start_row - 1:config.end_row]

    def cell(row, field):
        idx = col_map[field]
        return row.iloc[idx] if idx < width else None

    cases = []
    skipped = 0
    for offset, (_, row) in enumerate(rows.iterrows()):
        scope = _clean(cell(row, "scope"))
        # A row with no Scope names no commitment: a section heading, a spacer,
        # or slack at the end of a generously sized block. It is not a test
        # case, so it never becomes one -- which keeps the per-file count the
        # reader reports and the totals every view draws the same number.
        if SCOPES.is_unscoped(scope):
            skipped += 1
            continue
        cases.append(TestCase(
            file_name=file_name,
            sheet=config.sheet,
            device=config.device,
            row_num=config.start_row + offset,
            case_no=_clean(cell(row, "case_no")),
            scope=scope,
            result=_clean(cell(row, "result")),
            test_date=_clean_date(cell(row, "test_date")),
            pic=_clean(cell(row, "pic")),
            ticket_id=_clean(cell(row, "ticket_id")),
            note=_clean(cell(row, "note")),
        ))
    log.info("[%s] Read %d case(s) from sheet '%s' / device '%s' (%d row(s) with no scope skipped)",
             file_name, len(cases), config.sheet, config.device, skipped)
    return cases


def load_file(file_path: str) -> list[TestCase]:
    """Read every test case out of one workbook.

    Raises:
        ValueError: If TOOL_DATA is missing, malformed, or names a bad column.
            Callers that process many files should use `load_files`, which
            isolates these per file.
    """
    file_name = os.path.basename(file_path)
    log.info("[%s] Opening file", file_name)

    cases = []
    # One handle for the whole workbook: TOOL_DATA plus each test case sheet.
    with pd.ExcelFile(file_path) as xl:
        configs = parse_tool_data(xl)

        # Several configs (one per device) usually share a sheet. Parse each
        # sheet once and slice it per config, instead of re-reading the whole
        # workbook for every TOOL_DATA row.
        by_sheet: "OrderedDict[str, list[SheetConfig]]" = OrderedDict()
        for cfg in configs:
            by_sheet.setdefault(cfg.sheet, []).append(cfg)

        available = set(xl.sheet_names)
        for sheet_name, sheet_configs in by_sheet.items():
            if sheet_name not in available:
                log.warning("[%s] Sheet '%s' not found, skipping", file_name, sheet_name)
                continue
            # dtype=object keeps real dates as datetime and whole numbers as int,
            # so `_clean` can normalise them instead of receiving the already
            # stringified "2026-08-01 00:00:00" or "1.0".
            df = xl.parse(sheet_name=sheet_name, header=None, dtype=object)
            for cfg in sheet_configs:
                cases.extend(read_test_cases(df, cfg, file_name))

    log.info("[%s] Total: %d case(s) from %d config(s)", file_name, len(cases), len(configs))
    return cases


def find_workbooks(folder_path: str) -> list[str]:
    """Every .xlsx under `folder_path`, recursively, in a stable order.

    Excel lock files (``~$name.xlsx``, left behind by an open workbook) are
    left out. This is the one definition of "the workbooks in this folder" —
    loading and the prepare endpoints both resolve a folder through it, so a
    file one of them acts on is always one the other can see.
    """
    paths = sorted(glob.glob(os.path.join(folder_path, "**", "*.xlsx"), recursive=True))
    return [p for p in paths if not os.path.basename(p).startswith(LOCK_FILE_PREFIX)]


def load_files(file_paths: list[str]) -> tuple[list[TestCase], list[dict]]:
    """Load every path, isolating failures so one bad file doesn't sink the rest.

    Excel lock files (``~$name.xlsx``, left behind by an open workbook) are
    skipped silently rather than reported as errors.

    Returns:
        `(cases, file_results)` where each file result is
        `{"file", "path", "status": "OK", "cases": n}` or
        `{"file", "path", "status": "Error", "error": msg}`. Skipped lock files
        appear in neither.

    `path` is there because `file` is only a basename and the folder scan is
    recursive: two subfolders may each hold a "TC.xlsx", and the Tools view
    joins these results to `prepare.runner.describe` on the path to put a
    workbook's case count and its TOOL_DATA state on one row.
    """
    all_cases = []
    file_results = []
    for path in file_paths:
        name = os.path.basename(path)
        if name.startswith(LOCK_FILE_PREFIX):
            log.debug("Skipping Excel lock file %s", name)
            continue
        try:
            cases = load_file(path)
            all_cases.extend(cases)
            file_results.append({"file": name, "path": path, "status": "OK",
                                 "cases": len(cases)})
        except Exception as e:
            log.error("[%s] Failed: %s", name, e)
            file_results.append({"file": name, "path": path, "status": "Error",
                                 "error": str(e)})
    return all_cases, file_results


def load_from_folder(folder_path: str) -> tuple[list[TestCase], list[dict]]:
    """Load every .xlsx under `folder_path`, recursively.

    Returns:
        `(cases, file_results)` — see `load_files` for the per-file result shape.
    """
    files = find_workbooks(folder_path)
    log.info("Scanning folder '%s' (recursive): found %d .xlsx file(s)", folder_path, len(files))
    all_cases, file_results = load_files(files)
    log.info("Folder done: %d case(s) from %d file(s)", len(all_cases), len(file_results))
    return all_cases, file_results


def load_from_files(file_paths: list[str]) -> tuple[list[TestCase], list[dict]]:
    """Load an explicit list of workbook paths.

    Returns:
        `(cases, file_results)` — see `load_files` for the per-file result shape.
    """
    log.info("Loading %d specific file(s)", len(file_paths))
    all_cases, file_results = load_files(file_paths)
    log.info("Files done: %d case(s) from %d file(s)", len(all_cases), len(file_results))
    return all_cases, file_results
