import os
from datetime import datetime

import pytest

from parser.excel_reader import load_file, load_from_files, load_from_folder
from tests.conftest import config_row, write_workbook

# One device block in A-G, a second in A,B + H-L.
BLOCK_1 = "A B C D E F G"
BLOCK_2 = "A B H I J K L"


def test_a_real_date_cell_reads_back_as_an_iso_date(make_workbook):
    path = make_workbook(
        tool_data=[config_row("Login", "iPhone", 4, 4)],
        cells={"Login": {(4, "A"): "TC-1", (4, "C"): "OK",
                         (4, "D"): datetime(2026, 8, 1)}},
    )
    case = load_file(path)[0]
    assert case.test_date == "2026-08-01"


def test_a_date_cell_with_a_time_keeps_only_the_date(make_workbook):
    path = make_workbook(
        tool_data=[config_row("Login", "iPhone", 4, 4)],
        cells={"Login": {(4, "A"): "TC-1", (4, "C"): "OK",
                         (4, "D"): datetime(2026, 8, 2, 13, 30)}},
    )
    assert load_file(path)[0].test_date == "2026-08-02"


def test_a_text_date_with_a_midnight_time_is_trimmed(make_workbook):
    path = make_workbook(
        tool_data=[config_row("Login", "iPhone", 4, 4)],
        cells={"Login": {(4, "A"): "TC-1", (4, "C"): "OK",
                         (4, "D"): "2026-08-01 00:00:00"}},
    )
    assert load_file(path)[0].test_date == "2026-08-01"


def test_numeric_cells_do_not_gain_a_decimal_suffix(make_workbook):
    path = make_workbook(
        tool_data=[config_row("Login", "iPhone", 4, 4)],
        cells={"Login": {(4, "A"): 1, (4, "C"): "OK"}},
    )
    assert load_file(path)[0].case_no == "1"


def test_blank_cells_become_none(make_workbook):
    path = make_workbook(
        tool_data=[config_row("Login", "iPhone", 4, 4)],
        cells={"Login": {(4, "A"): "TC-1"}},
    )
    case = load_file(path)[0]
    assert (case.scope, case.result, case.test_date, case.pic) == (None,) * 4


def test_two_device_blocks_on_one_sheet_read_their_own_columns(make_workbook):
    """Guards the switch from `usecols` to positional slicing."""
    path = make_workbook(
        tool_data=[
            config_row("Login", "iPhone", 4, 5, cols=BLOCK_1),
            config_row("Login", "iPad", 4, 5, cols=BLOCK_2),
        ],
        cells={"Login": {
            (4, "A"): "TC-1", (4, "B"): "FPT",
            (4, "C"): "OK", (4, "D"): "2026-08-01", (4, "E"): "lee",
            (4, "H"): "NG", (4, "I"): "2026-08-02", (4, "J"): "kim",
            (4, "K"): "BUG-1", (4, "L"): "needs a fix",
            (5, "A"): "TC-2", (5, "C"): "OK", (5, "H"): "保留", (5, "K"): "BUG-2",
        }},
    )
    cases = load_file(path)
    by_device = {(c.device, c.case_no): c for c in cases}

    iphone = by_device[("iPhone", "TC-1")]
    assert (iphone.result, iphone.test_date, iphone.pic) == ("OK", "2026-08-01", "lee")

    ipad = by_device[("iPad", "TC-1")]
    assert (ipad.result, ipad.test_date, ipad.pic) == ("NG", "2026-08-02", "kim")
    assert (ipad.ticket_id, ipad.note) == ("BUG-1", "needs a fix")

    assert by_device[("iPad", "TC-2")].result == "保留"


def test_row_numbers_map_back_to_the_excel_rows(make_workbook):
    path = make_workbook(
        tool_data=[config_row("Login", "iPhone", 4, 6)],
        cells={"Login": {(4, "A"): "TC-1", (5, "A"): "TC-2", (6, "A"): "TC-3"}},
    )
    assert [c.row_num for c in load_file(path)] == [4, 5, 6]


@pytest.mark.parametrize("bad, message", [
    ({"start_row": "abc"}, "'start_row' must be a number"),
    ({"end_row": None}, "'end_row' is empty"),
    ({"end_row": 2}, "is before 'start_row'"),
    ({"result_col": "12"}, "'result_col' is not a column letter"),
    ({"pic_col": None}, "'pic_col' is empty"),
    ({"end_row": 10 ** 7}, "span more than"),
])
def test_a_malformed_tool_data_row_is_reported_with_its_row_number(make_workbook, bad, message):
    path = make_workbook(
        tool_data=[{**config_row("Login", "iPhone", 4, 20), **bad}],
        cells={"Login": {(4, "A"): "TC-1"}},
    )
    with pytest.raises(ValueError, match=message) as excinfo:
        load_file(path)
    # Header is row 1, so the first config row is Excel row 2.
    assert "TOOL_DATA row 2" in str(excinfo.value)


def test_a_bad_row_fails_only_its_own_file(tmp_path):
    good = write_workbook(
        tmp_path / "good.xlsx",
        [config_row("Login", "iPhone", 4, 4)],
        {"Login": {(4, "A"): "TC-1", (4, "C"): "OK"}},
    )
    write_workbook(
        tmp_path / "bad.xlsx",
        [config_row("Login", "iPhone", 4, "oops")],
        {"Login": {(4, "A"): "TC-1"}},
    )

    cases, file_results = load_from_folder(str(tmp_path))
    by_name = {r["file"]: r for r in file_results}

    assert by_name["good.xlsx"]["status"] == "OK"
    assert by_name["bad.xlsx"]["status"] == "Error"
    assert "TOOL_DATA row 2" in by_name["bad.xlsx"]["error"]
    assert [c.file_name for c in cases] == ["good.xlsx"]
    assert os.path.basename(good) == "good.xlsx"


def test_excel_lock_files_are_skipped_in_files_mode(tmp_path):
    real = write_workbook(
        tmp_path / "TC.xlsx",
        [config_row("Login", "iPhone", 4, 4)],
        {"Login": {(4, "A"): "TC-1", (4, "C"): "OK"}},
    )
    lock = write_workbook(
        tmp_path / "~$TC.xlsx",
        [config_row("Login", "iPhone", 4, 4)],
        {"Login": {(4, "A"): "TC-1", (4, "C"): "OK"}},
    )

    _, file_results = load_from_files([real, lock])
    assert [r["file"] for r in file_results] == ["TC.xlsx"]


def test_a_sheet_named_in_tool_data_but_absent_is_skipped(make_workbook):
    path = make_workbook(
        tool_data=[
            config_row("Login", "iPhone", 4, 4),
            config_row("Ghost", "iPhone", 4, 4),
        ],
        cells={"Login": {(4, "A"): "TC-1", (4, "C"): "OK"}},
    )
    cases = load_file(path)
    assert [c.sheet for c in cases] == ["Login"]


def test_columns_beyond_the_sheet_width_read_as_none(make_workbook):
    """A TOOL_DATA row can point past the last written column."""
    path = make_workbook(
        tool_data=[config_row("Login", "iPhone", 4, 4, cols="A B C D E Y Z")],
        cells={"Login": {(4, "A"): "TC-1", (4, "C"): "OK"}},
    )
    case = load_file(path)[0]
    assert (case.ticket_id, case.note) == (None, None)
    assert case.result == "OK"
