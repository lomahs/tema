"""Dataclasses shared by the Excel reader and the API."""
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class SheetConfig:
    """One row of a workbook's TOOL_DATA sheet.

    Each row says where to find one device's results inside one test case
    sheet. Several devices usually share a sheet, so several configs commonly
    name the same `sheet` with different column letters.

    Attributes:
        sheet: Name of the worksheet holding the test cases.
        device: Device this column block belongs to (e.g. "iPhone").
        start_row: First data row, 1-based and inclusive, as numbered in Excel.
        end_row: Last data row, 1-based and inclusive.
        test_no_col: Column letter of the test case number.
        scope_col: Column letter of the scope / responsible party.
        result_col: Column letter of the result (classified via `parser.status`).
        test_date_col: Column letter of the execution date.
        pic_col: Column letter of the person in charge who ran the case.
        ticket_id_col: Column letter of the bug ticket id, when the result needs one.
        note_col: Column letter of the free-text note, an alternative to a ticket id.
    """

    sheet: str
    device: str
    start_row: int
    end_row: int
    test_no_col: str
    scope_col: str
    result_col: str
    test_date_col: str
    pic_col: str
    ticket_id_col: str
    note_col: str


@dataclass
class TestCase:
    """A single test case row, read for one device.

    Every field past `row_num` is optional: rows inside the configured span are
    read verbatim, including blank ones and the group heading rows real test
    case sheets use as separators.

    Attributes:
        file_name: Basename of the source .xlsx.
        sheet: Worksheet the row came from.
        device: Device whose column block this row was read from.
        row_num: 1-based Excel row number, for pointing a tester back at the cell.
        case_no: Test case number as written in the sheet.
        scope: Scope / responsible party (e.g. "FPT", "JP").
        result: Raw result text; `parser.status.STATUS.classify` maps it to a
            status key. `None` means the case has not been run.
        test_date: Execution date, normalised to "YYYY-MM-DD".
        pic: Person in charge who executed the case.
        ticket_id: Bug ticket raised for a failing result.
        note: Free-text explanation; satisfies the same requirement as a ticket id.
    """

    file_name: str
    sheet: str
    device: str
    row_num: int = 0
    case_no: Optional[str] = None
    scope: Optional[str] = None
    result: Optional[str] = None
    test_date: Optional[str] = None
    pic: Optional[str] = None
    ticket_id: Optional[str] = None
    note: Optional[str] = None

    def to_dict(self):
        """Plain dict of every field, for JSON serialisation."""
        return asdict(self)
