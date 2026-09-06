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
    assert sum(row[key] for key in aggregate.STATUS.keys) == row["total"] == 3


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
        case(case_no="TC-5", result="対象外"),
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
