"""Planning and applying a results wipe, as the clearing module exposes it.

`tcm.infrastructure.excel.clearing` is the code under test here. The rules
that matter are all about restraint: a row already empty is not worth listing,
a kept status is left alone, and nothing outside the five result columns is
ever touched.
"""

import pytest

from tcm.infrastructure.excel.clearing import apply_plan, plan_file
from tests.conftest import config_row, write_workbook


@pytest.fixture
def workbook(tmp_path):
    """One device block holding a run's worth of results, plus two rows to leave."""
    return write_workbook(
        tmp_path / "TC.xlsx",
        [config_row("Login", "iPhone", 4, 8, cols="A B C D E F G")],
        {"Login": {
            (4, "A"): "TC-1", (4, "B"): "FPT", (4, "C"): "OK",
            (4, "D"): "2026-08-05", (4, "E"): "lee",
            (5, "A"): "TC-2", (5, "B"): "FPT", (5, "C"): "NG",
            (5, "D"): "2026-08-05", (5, "E"): "lee", (5, "F"): "BUG-1",
            # Cancel: out of scope this round and the next, so it survives.
            (6, "A"): "TC-3", (6, "B"): "FPT", (6, "C"): "対象外",
            (6, "D"): "2026-08-05", (6, "E"): "lee", (6, "G"): "dropped",
            # Never run: nothing to clear.
            (7, "A"): "TC-4", (7, "B"): "FPT",
            (8, "A"): "TC-5", (8, "B"): "JP", (8, "C"): "OK",
            (8, "D"): "2026-08-06", (8, "E"): "kim",
        }},
    )


def test_plan_lists_the_rows_carrying_a_result(workbook):
    plan = plan_file(workbook, keep=set())

    assert [item.row for item in plan.items] == [4, 5, 6, 8]


def test_plan_skips_rows_whose_result_cells_are_already_blank(workbook):
    plan = plan_file(workbook, keep=set())

    # Row 7 has a number and a scope but was never run.
    assert 7 not in [item.row for item in plan.items]


def test_plan_leaves_kept_statuses_alone_and_counts_them(workbook):
    plan = plan_file(workbook, keep={"Cancel"})

    assert [item.row for item in plan.items] == [4, 5, 8]
    assert plan.kept["Cancel"] == 1


def test_plan_carries_the_five_result_columns_of_its_config(workbook):
    plan = plan_file(workbook, keep=set())

    assert plan.items[0].columns == ("C", "D", "E", "F", "G")


def test_apply_blanks_the_planned_cells(workbook):
    from openpyxl import load_workbook

    apply_plan(workbook, plan_file(workbook, keep={"Cancel"}))

    ws = load_workbook(workbook)["Login"]
    assert [ws[f"{c}4"].value for c in "CDEFG"] == [None] * 5
    assert [ws[f"{c}5"].value for c in "CDEFG"] == [None] * 5


def test_apply_leaves_every_other_column_as_it_was(workbook):
    from openpyxl import load_workbook

    apply_plan(workbook, plan_file(workbook, keep={"Cancel"}))

    ws = load_workbook(workbook)["Login"]
    assert [ws[f"A{row}"].value for row in range(4, 9)] == [
        "TC-1", "TC-2", "TC-3", "TC-4", "TC-5",
    ]
    assert ws["B4"].value == "FPT"


def test_apply_does_not_touch_a_kept_row(workbook):
    from openpyxl import load_workbook

    apply_plan(workbook, plan_file(workbook, keep={"Cancel"}))

    ws = load_workbook(workbook)["Login"]
    assert ws["C6"].value == "対象外"
    assert ws["G6"].value == "dropped"


def test_a_cancel_with_no_pic_is_planned_as_out_of_scope(tmp_path):
    """The derived status, not the raw one — same rule the views read by.

    `対象外` with a PIC is a decision someone made; without one the case was
    never in the plan. Reporting both as Cancel would let "keep Cancel" wipe
    the rows that were never in scope to begin with.
    """
    path = write_workbook(
        tmp_path / "OOS.xlsx",
        [config_row("Login", "iPhone", 4, 5, cols="A B C D E F G")],
        {"Login": {
            (4, "A"): "TC-1", (4, "C"): "対象外", (4, "D"): "2026-08-05", (4, "E"): "lee",
            (5, "A"): "TC-2", (5, "C"): "対象外", (5, "D"): "2026-08-05",
        }},
    )

    plan = plan_file(path, keep=set())

    assert {item.row: item.status for item in plan.items} == {4: "Cancel", 5: "OOS"}


def test_keeping_out_of_scope_leaves_the_unowned_row_alone(tmp_path):
    path = write_workbook(
        tmp_path / "OOS.xlsx",
        [config_row("Login", "iPhone", 4, 5, cols="A B C D E F G")],
        {"Login": {
            (4, "A"): "TC-1", (4, "C"): "対象外", (4, "D"): "2026-08-05", (4, "E"): "lee",
            (5, "A"): "TC-2", (5, "C"): "対象外", (5, "D"): "2026-08-05",
        }},
    )

    plan = plan_file(path, keep={"OOS"})

    assert [item.row for item in plan.items] == [4]
    assert plan.kept["OOS"] == 1


def test_apply_can_write_to_a_different_path(workbook, tmp_path):
    from openpyxl import load_workbook

    dest = apply_plan(workbook, plan_file(workbook, keep=set()), str(tmp_path / "out.xlsx"))

    assert dest == str(tmp_path / "out.xlsx")
    # The original is untouched.
    assert load_workbook(workbook)["Login"]["C4"].value == "OK"
    assert load_workbook(dest)["Login"]["C4"].value is None


def test_planning_a_workbook_with_no_tool_data_is_an_error(tmp_path):
    path = write_workbook(tmp_path / "Bare.xlsx", None, {"Login": {(4, "A"): "TC-1"}})

    with pytest.raises(ValueError, match="TOOL_DATA"):
        plan_file(path, keep=set())
