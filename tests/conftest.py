import pytest
from openpyxl import Workbook
from openpyxl.utils import column_index_from_string

from parser.excel_reader import TOOL_DATA_SHEET, TOOL_DATA_COLUMNS

DEFAULT_COLS = "A B C D E F G"

_COL_KEYS = [
    "test_no_col", "scope_col", "result_col", "test_date_col",
    "pic_col", "ticket_id_col", "note_col",
]


def config_row(sheet, device, start_row, end_row, cols=DEFAULT_COLS, **overrides):
    """One TOOL_DATA row. `cols` is the 7 column letters, in TOOL_DATA order."""
    row = {
        "sheet": sheet,
        "device": device,
        "start_row": start_row,
        "end_row": end_row,
        **dict(zip(_COL_KEYS, cols.split())),
    }
    row.update(overrides)
    return row


def write_workbook(path, tool_data, cells):
    """Build an .xlsx. `cells` maps sheet name -> {(row, "A"): value}."""
    wb = Workbook()
    td = wb.active
    td.title = TOOL_DATA_SHEET
    td.append(TOOL_DATA_COLUMNS)
    for row in tool_data:
        td.append([row.get(name) for name in TOOL_DATA_COLUMNS])

    for sheet_name, sheet_cells in cells.items():
        ws = wb.create_sheet(sheet_name)
        for (row_num, letter), value in sheet_cells.items():
            ws.cell(row=row_num, column=column_index_from_string(letter), value=value)

    wb.save(path)
    return str(path)


@pytest.fixture
def make_workbook(tmp_path):
    def _make(name="TC.xlsx", tool_data=(), cells=None):
        return write_workbook(tmp_path / name, list(tool_data), cells or {})
    return _make
