import os
from datetime import datetime

import pytest

from parser.excel_reader import (
    find_workbooks, load_file, load_from_files, load_from_folder,
)
from tcm.domain.case import SheetConfig
from tests.conftest import config_row, write_workbook

# One device block in A-G, a second in A,B + H-L.
BLOCK_1 = "A B C D E F G"
BLOCK_2 = "A B H I J K L"


def test_a_real_date_cell_reads_back_as_an_iso_date(make_workbook):
    path = make_workbook(
        tool_data=[config_row("Login", "iPhone", 4, 4)],
        cells={"Login": {(4, "A"): "TC-1", (4, "B"): "FPT", (4, "C"): "OK",
                         (4, "D"): datetime(2026, 8, 1)}},
    )
    case = load_file(path)[0]
    assert case.test_date == "2026-08-01"


def test_a_date_cell_with_a_time_keeps_only_the_date(make_workbook):
    path = make_workbook(
        tool_data=[config_row("Login", "iPhone", 4, 4)],
        cells={"Login": {(4, "A"): "TC-1", (4, "B"): "FPT", (4, "C"): "OK",
                         (4, "D"): datetime(2026, 8, 2, 13, 30)}},
    )
    assert load_file(path)[0].test_date == "2026-08-02"


def test_a_text_date_with_a_midnight_time_is_trimmed(make_workbook):
    path = make_workbook(
        tool_data=[config_row("Login", "iPhone", 4, 4)],
        cells={"Login": {(4, "A"): "TC-1", (4, "B"): "FPT", (4, "C"): "OK",
                         (4, "D"): "2026-08-01 00:00:00"}},
    )
    assert load_file(path)[0].test_date == "2026-08-01"


def test_numeric_cells_do_not_gain_a_decimal_suffix(make_workbook):
    path = make_workbook(
        tool_data=[config_row("Login", "iPhone", 4, 4)],
        cells={"Login": {(4, "A"): 1, (4, "B"): "FPT", (4, "C"): "OK"}},
    )
    assert load_file(path)[0].case_no == "1"


def test_blank_cells_become_none(make_workbook):
    """Scope is not among them: a row without one is not read at all."""
    path = make_workbook(
        tool_data=[config_row("Login", "iPhone", 4, 4)],
        cells={"Login": {(4, "A"): "TC-1", (4, "B"): "FPT"}},
    )
    case = load_file(path)[0]
    assert (case.result, case.test_date, case.pic, case.note) == (None,) * 4


def test_a_row_with_no_scope_is_not_read_as_a_case(make_workbook):
    """A blank Scope cell marks a section heading, not work anyone planned."""
    path = make_workbook(
        tool_data=[config_row("Login", "iPhone", 4, 6)],
        cells={"Login": {
            (4, "A"): "TC-1", (4, "B"): "FPT", (4, "C"): "OK",
            (5, "A"): "Login screen", (5, "C"): "OK",
            (6, "A"): "TC-2", (6, "B"): "JP", (6, "C"): "NG",
        }},
    )
    assert [c.case_no for c in load_file(path)] == ["TC-1", "TC-2"]


def test_a_scope_of_only_spaces_is_no_scope(make_workbook):
    path = make_workbook(
        tool_data=[config_row("Login", "iPhone", 4, 4)],
        cells={"Login": {(4, "A"): "TC-1", (4, "B"): "   ", (4, "C"): "OK"}},
    )
    assert load_file(path) == []


def test_the_per_file_count_leaves_out_the_rows_with_no_scope(make_workbook):
    """The drawer's count and the totals on screen have to be the same number."""
    path = make_workbook(
        tool_data=[config_row("Login", "iPhone", 4, 5)],
        cells={"Login": {
            (4, "A"): "TC-1", (4, "B"): "FPT", (4, "C"): "OK",
            (5, "A"): "Login screen", (5, "C"): "OK",
        }},
    )
    cases, file_results = load_from_files([path])
    assert len(cases) == 1
    assert file_results[0]["cases"] == 1


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
            (5, "A"): "TC-2", (5, "B"): "JP",
            (5, "C"): "OK", (5, "H"): "保留", (5, "K"): "BUG-2",
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
        cells={"Login": {(4, "A"): "TC-1", (4, "B"): "FPT",
                         (5, "A"): "TC-2", (5, "B"): "FPT",
                         (6, "A"): "TC-3", (6, "B"): "FPT"}},
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
        {"Login": {(4, "A"): "TC-1", (4, "B"): "FPT", (4, "C"): "OK"}},
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
        {"Login": {(4, "A"): "TC-1", (4, "B"): "FPT", (4, "C"): "OK"}},
    )
    lock = write_workbook(
        tmp_path / "~$TC.xlsx",
        [config_row("Login", "iPhone", 4, 4)],
        {"Login": {(4, "A"): "TC-1", (4, "B"): "FPT", (4, "C"): "OK"}},
    )

    _, file_results = load_from_files([real, lock])
    assert [r["file"] for r in file_results] == ["TC.xlsx"]


def test_a_sheet_named_in_tool_data_but_absent_is_skipped(make_workbook):
    path = make_workbook(
        tool_data=[
            config_row("Login", "iPhone", 4, 4),
            config_row("Ghost", "iPhone", 4, 4),
        ],
        cells={"Login": {(4, "A"): "TC-1", (4, "B"): "FPT", (4, "C"): "OK"}},
    )
    cases = load_file(path)
    assert [c.sheet for c in cases] == ["Login"]


def test_columns_beyond_the_sheet_width_read_as_none(make_workbook):
    """A TOOL_DATA row can point past the last written column."""
    path = make_workbook(
        tool_data=[config_row("Login", "iPhone", 4, 4, cols="A B C D E Y Z")],
        cells={"Login": {(4, "A"): "TC-1", (4, "B"): "FPT", (4, "C"): "OK"}},
    )
    case = load_file(path)[0]
    assert (case.ticket_id, case.note) == (None, None)
    assert case.result == "OK"


# --- finding workbooks -----------------------------------------------------
#
# One definition of "every workbook under here", shared by loading, the prepare
# endpoints and the CLIs — four places that each used to glob for themselves.

def test_find_workbooks_lists_xlsx_files_in_order(tmp_path):
    for name in ("b.xlsx", "a.xlsx"):
        write_workbook(tmp_path / name, [config_row("Login", "iPhone", 4, 4)], {})

    assert [os.path.basename(p) for p in find_workbooks(str(tmp_path))] == ["a.xlsx", "b.xlsx"]


def test_find_workbooks_recurses_into_subfolders(tmp_path):
    nested = tmp_path / "round2"
    nested.mkdir()
    write_workbook(nested / "deep.xlsx", [config_row("Login", "iPhone", 4, 4)], {})

    assert [os.path.basename(p) for p in find_workbooks(str(tmp_path))] == ["deep.xlsx"]


def test_find_workbooks_skips_excel_lock_files(tmp_path):
    write_workbook(tmp_path / "TC.xlsx", [config_row("Login", "iPhone", 4, 4)], {})
    write_workbook(tmp_path / "~$TC.xlsx", [config_row("Login", "iPhone", 4, 4)], {})

    assert [os.path.basename(p) for p in find_workbooks(str(tmp_path))] == ["TC.xlsx"]


def test_find_workbooks_ignores_files_that_are_not_workbooks(tmp_path):
    write_workbook(tmp_path / "TC.xlsx", [config_row("Login", "iPhone", 4, 4)], {})
    (tmp_path / "notes.txt").write_text("not a workbook")

    assert [os.path.basename(p) for p in find_workbooks(str(tmp_path))] == ["TC.xlsx"]


def test_sheet_config_round_trips_through_to_dict():
    """The endpoints serialise configs; hand-listing 11 fields invites drift."""
    cfg = SheetConfig(**config_row("Login", "iPhone", 4, 8, cols="A B C D E F G"))

    assert cfg.to_dict() == {
        "sheet": "Login", "device": "iPhone", "start_row": 4, "end_row": 8,
        "test_no_col": "A", "scope_col": "B", "result_col": "C",
        "test_date_col": "D", "pic_col": "E", "ticket_id_col": "F", "note_col": "G",
    }


def test_each_file_result_carries_the_path_it_was_read_from(tmp_path):
    """A basename does not identify a workbook; the folder scan is recursive.

    The Tools view joins these results to `prepare.runner.describe` to put a
    workbook's TOOL_DATA state on the same row as its case count, and two
    subfolders may each hold a "TC.xlsx".
    """
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    for folder in ("a", "b"):
        write_workbook(
            tmp_path / folder / "TC.xlsx",
            [config_row("Login", "iPhone", 4, 4)],
            {"Login": {(4, "A"): "TC-1", (4, "B"): "FPT", (4, "C"): "OK"}},
        )

    _, file_results = load_from_folder(str(tmp_path))

    assert [r["file"] for r in file_results] == ["TC.xlsx", "TC.xlsx"]
    assert sorted(os.path.relpath(r["path"], tmp_path) for r in file_results) == [
        os.path.join("a", "TC.xlsx"), os.path.join("b", "TC.xlsx"),
    ]


def test_a_failed_file_result_carries_its_path_too(make_workbook):
    """The row that needs identifying most is the one that could not be read."""
    path = make_workbook("bad.xlsx", [config_row("Login", "iPhone", 4, "oops")],
                         {"Login": {(4, "A"): "TC-1"}})

    _, file_results = load_from_files([path])

    assert file_results[0]["status"] == "Error"
    assert file_results[0]["path"] == path
