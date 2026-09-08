"""The aggregation layer, exercised directly on `TestCase` objects.

`tests/test_api.py` covers the same numbers as they come out of the endpoints;
these tests pin the functions themselves, because the report publisher consumes
them without going anywhere near HTTP.
"""
import aggregate
from parser import models


def case(**kwargs):
    """A TestCase with the identifying fields filled in, so tests name only what matters.

    `models.TestCase` is reached through the module rather than imported by name:
    pytest tries to collect any module-level class called `Test*` and warns when
    it cannot.
    """
    return models.TestCase(**{
        "file_name": "TC.xlsx", "sheet": "Login", "device": "iPhone", "row_num": 4,
        **kwargs,
    })


def test_summary_rows_group_by_file_and_device():
    rows, _ = aggregate.summary_rows([
        case(result="OK"),
        case(result="NG", row_num=5),
        case(device="iPad", result="OK"),
    ])

    assert [(r["file"], r["device"], r["total"]) for r in rows] == [
        ("TC.xlsx", "iPad", 1),
        ("TC.xlsx", "iPhone", 2),
    ]
    assert rows[1]["OK"] == 1 and rows[1]["NG"] == 1


def test_a_summary_rows_status_columns_add_up_to_its_total():
    rows, _ = aggregate.summary_rows([
        case(result="OK"), case(result="TBD"), case(result=None),
    ])

    row = rows[0]
    assert sum(row[key] for key in aggregate.STATUS.counted) == row["total"] == 3


def test_an_out_of_scope_case_is_counted_in_its_column_but_not_in_the_total():
    """The one column that deliberately sits outside the sum.

    A Cancel naming no PIC was never in the plan, so it must not inflate the
    denominator progress is read against — but it still has to be visible, or
    the rows would silently stop accounting for every case in the file.
    """
    rows, _ = aggregate.summary_rows([
        case(result="OK", pic="lee"),
        case(result="対象外", pic="lee"),
        case(result="対象外", pic=None),
    ])

    row = rows[0]
    assert row["OOS"] == 1
    assert row["Cancel"] == 1, "a Cancel that names a PIC is untouched"
    assert row["total"] == 2, "the out-of-scope case is not in the total"
    assert sum(row[key] for key in aggregate.STATUS.counted) == row["total"]
    assert sum(row[key] for key in aggregate.STATUS.keys) == 3, "no case has vanished"


def test_daily_rows_leave_out_of_scope_cases_out_of_the_total_too():
    rows = aggregate.daily_rows([
        case(result="OK", pic="lee", test_date="2026-08-05"),
        case(result="対象外", pic=None, test_date="2026-08-05"),
    ])

    assert len(rows) == 2, "a case with no PIC buckets under N/A"
    assert {r["pic"]: (r["total"], r["OOS"]) for r in rows} == {
        "lee": (1, 0), "N/A": (0, 1),
    }


def test_an_out_of_scope_case_is_never_asked_for_a_reason():
    """The boundary the rule turns on is the PIC, not the result text.

    Both cases below read `対象外` and carry neither a ticket nor a note. Only
    the one someone owns is a Missing Reason; the other is simply not in scope.
    """
    _, missing = aggregate.summary_rows([
        case(case_no="TC-1", result="対象外", pic="lee"),
        case(case_no="TC-2", result="対象外", pic=None),
    ])

    assert [m["case_no"] for m in missing] == ["TC-1"]


def test_issue_rows_leave_out_of_scope_cases_alone():
    """Nobody has to chase up a case that was never in the plan."""
    rows = aggregate.issue_rows([
        case(case_no="TC-1", result="対象外", pic="lee"),
        case(case_no="TC-2", result="対象外", pic=None),
    ])

    assert [(r["case_no"], r["status"]) for r in rows] == [("TC-1", "Cancel")]


def test_summary_flags_cases_that_need_a_reason_and_carry_none():
    _, missing = aggregate.summary_rows([
        case(case_no="TC-1", result="NG", ticket_id="BUG-1"),
        case(case_no="TC-2", result="NG", note="known flake"),
        case(case_no="TC-3", result="NG"),
        case(case_no="TC-4", result="OK"),
    ])

    assert [m["case_no"] for m in missing] == ["TC-3"]


def test_daily_rows_group_by_date_file_device_and_pic():
    rows = aggregate.daily_rows([
        case(result="OK", test_date="2026-08-05", pic="lee"),
        case(result="NG", test_date="2026-08-05", pic="lee"),
        case(result="OK", test_date="2026-08-06", pic="lee"),
    ])

    assert [(r["date"], r["pic"], r["total"]) for r in rows] == [
        ("2026-08-05", "lee", 2),
        ("2026-08-06", "lee", 1),
    ]


def test_daily_rows_leave_out_undated_cases():
    assert aggregate.daily_rows([case(result="OK", pic="lee")]) == []


def test_daily_rows_name_an_absent_pic_rather_than_dropping_the_row():
    rows = aggregate.daily_rows([case(result="OK", test_date="2026-08-05")])
    assert rows[0]["pic"] == "N/A"


def test_productivity_rows_measure_executed_cases_per_working_day():
    rows = aggregate.productivity_rows([
        case(result="OK", test_date="2026-08-03", pic="alice"),
        case(result="NG", test_date="2026-08-03", pic="alice"),
        case(result="OK", test_date="2026-08-04", pic="alice"),
    ])

    assert rows[0]["executed"] == 3
    assert rows[0]["days"] == 2
    assert rows[0]["productivity"] == 1.5


def test_issue_rows_hold_exactly_the_statuses_the_taxonomy_flags():
    rows = aggregate.issue_rows([
        case(case_no="TC-1", result="OK"),
        case(case_no="TC-2", result="NG"),
        case(case_no="TC-3", result="NG-OK"),
        case(case_no="TC-4", result="保留"),
        case(case_no="TC-5", result="対象外", pic="lee"),
        case(case_no="TC-6", result=None),
        case(case_no="TC-7", result="TBD"),
    ])

    assert [(r["case_no"], r["status"]) for r in rows] == [
        ("TC-2", "NG"), ("TC-4", "Pending"), ("TC-5", "Cancel"),
    ]


def test_an_issue_row_carries_what_a_reader_needs_to_chase_it_up():
    rows = aggregate.issue_rows([
        case(row_num=7, case_no="TC-2", scope="FPT", result="NG",
             test_date="2026-08-05", pic="lee", ticket_id="BUG-1", note="retest"),
    ])

    assert rows[0] == {
        "file": "TC.xlsx", "sheet": "Login", "device": "iPhone", "row": 7,
        "case_no": "TC-2", "scope": "FPT", "status": "NG", "result": "NG",
        "test_date": "2026-08-05", "pic": "lee", "ticket_id": "BUG-1", "note": "retest",
    }


def test_issue_rows_keep_the_source_order_of_the_cases():
    rows = aggregate.issue_rows([
        case(case_no="TC-9", result="保留", row_num=9),
        case(case_no="TC-2", result="NG", row_num=2),
    ])

    assert [r["case_no"] for r in rows] == ["TC-9", "TC-2"]


def test_every_aggregate_is_empty_when_nothing_is_loaded():
    assert aggregate.summary_rows([]) == ([], [])
    assert aggregate.daily_rows([]) == []
    assert aggregate.productivity_rows([]) == []
    assert aggregate.issue_rows([]) == []


# --- Scope split -----------------------------------------------------------
# Summary reports FPT and JP work as separate tables. The publisher does not,
# so the same function has to serve both granularities without them drifting.

def test_summary_rows_are_not_split_by_scope_by_default():
    """The report's sheet keeps one row per (file, device)."""
    rows, _ = aggregate.summary_rows([
        case(result="OK", scope="FPT"),
        case(result="OK", scope="JP"),
    ])

    assert len(rows) == 1
    assert rows[0]["total"] == 2
    assert "scope" not in rows[0]


def test_by_scope_splits_each_file_and_device_into_its_scope_groups():
    rows, _ = aggregate.summary_rows([
        case(result="OK", scope="FPT"),
        case(result="OK", scope="FPT (JM Support)"),
        case(result="NG", scope="JP"),
    ], by_scope=True)

    assert [(r["scope"], r["total"]) for r in rows] == [("FPT", 2), ("JP", 1)]
    assert all(r["file"] == "TC.xlsx" and r["device"] == "iPhone" for r in rows)


def test_an_unconfigured_or_blank_scope_lands_in_the_fallback_group():
    """Nothing may go missing: the tables have to account for every case."""
    rows, _ = aggregate.summary_rows([
        case(result="OK", scope="Vendor"),
        case(result="OK", scope=None),
    ], by_scope=True)

    assert [(r["scope"], r["total"]) for r in rows] == [("Other", 2)]


def test_the_scope_rows_of_a_file_add_up_to_its_unscoped_row():
    """The one property that stops the screen and the report disagreeing."""
    cases = [
        case(result="OK", scope="FPT"), case(result="NG", scope="JP"),
        case(result="保留", scope="Vendor"), case(result=None, scope="FPT"),
        case(result="対象外", scope="JP", pic=None),
    ]

    flat, _ = aggregate.summary_rows(cases)
    scoped, _ = aggregate.summary_rows(cases, by_scope=True)

    assert sum(r["total"] for r in scoped) == flat[0]["total"]
    for key in aggregate.STATUS.keys:
        assert sum(r[key] for r in scoped) == flat[0][key]


def test_the_scope_split_does_not_change_which_cases_owe_a_reason():
    cases = [
        case(case_no="TC-1", result="NG", scope="FPT"),
        case(case_no="TC-2", result="NG", scope="JP", ticket_id="BUG-1"),
    ]

    _, flat = aggregate.summary_rows(cases)
    _, scoped = aggregate.summary_rows(cases, by_scope=True)

    assert [m["case_no"] for m in flat] == [m["case_no"] for m in scoped] == ["TC-1"]
