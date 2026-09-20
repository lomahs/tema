"""Reading a workbook the way both preparation steps need it.

Detecting a layout and planning a results wipe both want the same thing: every
test case sheet as plain values, with TOOL_DATA left out — it describes the
sheets rather than being one of them. `data_only` resolves formulas, so a
result a formula produces is judged on what it shows, and the caller never
sees `"=IF(...)"`.
"""

from openpyxl import load_workbook

from tcm.infrastructure.excel.reader import TOOL_DATA_SHEET


def read_sheets(path: str) -> dict[str, list[tuple]]:
    """Every sheet except TOOL_DATA, as `{name: [row tuples]}`."""

    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        return {
            name: list(wb[name].iter_rows(values_only=True))
            for name in wb.sheetnames
            if name != TOOL_DATA_SHEET
        }
    finally:
        wb.close()


def has_tool_data(path: str) -> bool:
    """Whether the workbook carries a TOOL_DATA sheet.

    This is what decides whether a file is offered Create or Check, so it asks
    only for the sheet names — `read_only` avoids parsing a large workbook just
    to answer a yes/no.
    """

    wb = load_workbook(path, read_only=True)
    try:
        return TOOL_DATA_SHEET in wb.sheetnames
    finally:
        wb.close()
