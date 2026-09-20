"""The aggregation layer, exercised directly on `TestCase` objects.

`tests/test_api.py` covers the same numbers as they come out of the endpoints;
these tests pin the functions themselves, because the report publisher consumes
them without going anywhere near HTTP.
"""
import pytest

import aggregate
from parser import models
from parser.scope import SCOPES


def case(**kwargs):
    """A TestCase with the identifying fields filled in, so tests name only what matters.

    `models.TestCase` is reached through the module rather than imported by name:
    pytest tries to collect any module-level class called `Test*` and warns when
    it cannot.

    The default scope is a counted one. A blank Scope is not an unrecognised
    scope but a row that is not a case at all, so `_cases_for_config` drops it
    before a `TestCase` exists -- a fixture defaulting to `scope=None` was
    building something the reader never produces, and since the fallback stopped
    counting it would drop straight out of every figure under test.
    """
    return models.TestCase(**{
        "file_name": "TC.xlsx", "sheet": "Login", "device": "iPhone", "row_num": 4,
        "scope": "FPT",
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
    """Three cases, but a total of two: "TBD" matches no status.

    It therefore lands in the fallback, which the shipped taxonomy excludes, so
    it keeps its count and leaves the denominator. That is what makes the
    invariant the narrower one — total equals the sum of the *counted* columns,
    not of every column — and it is why the assertion is written against
    `STATUS.counted` rather than against `len`.
    """
    rows, _ = aggregate.summary_rows([
        case(result="OK"), case(result="TBD"), case(result=None),
    ])

    row = rows[0]
    assert sum(row[key] for key in aggregate.STATUS.counted) == row["total"] == 2
    assert sum(row[key] for key in aggregate.STATUS.excluded) == 1


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


def test_by_scope_splits_each_file_and_device_into_its_scope_groups(fixed_scopes):
    rows, _ = aggregate.summary_rows([
        case(result="OK", scope="FPT"),
        case(result="OK", scope="FPT (JM Support)"),
        case(result="NG", scope="JP"),
    ], by_scope=True)

    assert [(r["scope"], r["total"]) for r in rows] == [("FPT", 2), ("JP", 1)]
    assert all(r["file"] == "TC.xlsx" and r["device"] == "iPhone" for r in rows)


def test_an_unconfigured_or_blank_scope_lands_in_the_fallback_group(fixed_scopes):
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


def test_every_summary_row_names_the_device_family_it_belongs_to():
    """Summary's "By device type" mode merges on this, so the classification
    happens once here rather than in the browser — the report publisher reads
    the same rows and the two cannot disagree about what an iPhone is."""
    rows, _ = aggregate.summary_rows([
        case(device="iPhone Min size", result="OK"),
        case(device="iPhone Max size", result="NG"),
        case(device="Android 14", result="OK"),
    ])

    assert {r["device"]: r["device_family"] for r in rows} == {
        "iPhone Min size": "iPhone",
        "iPhone Max size": "iPhone",
        "Android 14": "Android 14",
    }


def test_the_device_families_of_a_file_add_up_to_its_combined_row():
    """Merging by family must not change any total, only how many rows show it."""
    cases = [
        case(device="iPhone Min size", result="OK"),
        case(device="iPhone Max size", result="NG"),
        case(device="iPad Pro", result="OK"),
    ]
    rows, _ = aggregate.summary_rows(cases)

    by_family = {}
    for r in rows:
        by_family[r["device_family"]] = by_family.get(r["device_family"], 0) + r["total"]

    assert by_family == {"iPhone": 2, "iPad": 1}
    assert sum(by_family.values()) == sum(r["total"] for r in rows)


@pytest.fixture
def jp_is_not_in_the_plan():
    """A taxonomy where JP work is reported but not counted toward the total."""
    from parser.scope import SCOPES, ScopeSet

    saved = dict(SCOPES.__dict__)
    SCOPES.adopt(ScopeSet.from_dict({
        "groups": [
            {"key": "FPT", "match": ["FPT"]},
            {"key": "JP", "match": ["JP"], "excluded": True},
        ],
        "fallback": {"key": "Other"},
    }))
    yield
    SCOPES.__dict__.clear()
    SCOPES.__dict__.update(saved)


def test_in_plan_keeps_only_the_cases_whose_scope_group_counts(jp_is_not_in_the_plan):
    """Neither an excluded group nor the fallback is in the plan.

    "Vendor" is configured nowhere, so it lands in the fallback -- and an
    unrecognised scope names no commitment anyone made, so it cannot sit in the
    denominator either. Summary's third table is where those cases stay visible;
    this is the figure they leave.
    """
    kept = aggregate.in_plan([
        case(result="OK", scope="FPT"),
        case(result="OK", scope="JP", row_num=5),
        case(result="OK", scope="Vendor", row_num=6),
    ])

    assert [c.scope for c in kept] == ["FPT"]


def test_daily_rows_leave_out_an_excluded_scope(jp_is_not_in_the_plan):
    rows = aggregate.daily_rows([
        case(result="OK", scope="FPT", pic="lee", test_date="2026-09-01"),
        case(result="OK", scope="JP", pic="lee", test_date="2026-09-01", row_num=5),
    ])

    assert len(rows) == 1
    assert rows[0]["total"] == 1


def test_productivity_rows_leave_out_an_excluded_scope(jp_is_not_in_the_plan):
    """Work outside the plan must not flatter -- or dilute -- anyone's rate."""
    rows = aggregate.productivity_rows([
        case(result="OK", scope="FPT", pic="lee", test_date="2026-09-01"),
        case(result="OK", scope="JP", pic="lee", test_date="2026-09-01", row_num=5),
        case(result="OK", scope="JP", pic="lee", test_date="2026-09-02", row_num=6),
    ])

    assert [(r["pic"], r["executed"], r["days"]) for r in rows] == [("lee", 1, 1)]


def test_issue_rows_leave_out_an_excluded_scope(jp_is_not_in_the_plan):
    rows = aggregate.issue_rows([
        case(result="NG", scope="FPT"),
        case(result="NG", scope="JP", row_num=5),
    ])

    assert [r["scope"] for r in rows] == ["FPT"]


def test_summary_rows_still_report_an_excluded_scope(jp_is_not_in_the_plan):
    """Summary is the one screen that shows it: the count has to stay visible,
    the same way an excluded status keeps its column."""
    rows, _ = aggregate.summary_rows([
        case(result="OK", scope="FPT"),
        case(result="OK", scope="JP", row_num=5),
    ], by_scope=True)

    assert sorted(r["scope"] for r in rows) == ["FPT", "JP"]
    assert all(r["total"] == 1 for r in rows)


# --- One workbook, read sheet by sheet -------------------------------------
#
# `file_rows` is Summary one level finer: the same (scope, device) split, cut
# again by the sheet each case was read from. It answers a different question --
# "what is in this file" rather than "how do the files compare" -- so unlike
# `daily_rows` and `issue_rows` it keeps every scope group, including one the
# plan excludes. A Scope column that could only ever say FPT would not be one.


def test_file_rows_group_by_sheet_scope_and_device(fixed_scopes):
    data = aggregate.file_rows([
        case(sheet="Login", scope="FPT", result="OK"),
        case(sheet="Login", scope="FPT", result="NG", device="iPad"),
        case(sheet="Login", scope="JP", result="OK", row_num=5),
        case(sheet="Search", scope="FPT", result="OK"),
    ], "TC.xlsx")

    assert [(r["sheet"], r["scope"], r["device"], r["total"]) for r in data["rows"]] == [
        ("Login", "FPT", "iPad", 1),
        ("Login", "FPT", "iPhone", 1),
        ("Login", "JP", "iPhone", 1),
        ("Search", "FPT", "iPhone", 1),
    ]


def test_file_rows_hold_only_the_file_asked_for():
    data = aggregate.file_rows([
        case(file_name="TC.xlsx", result="OK"),
        case(file_name="Other.xlsx", result="NG"),
    ], "TC.xlsx")

    assert data["file"] == "TC.xlsx"
    assert [r["total"] for r in data["rows"]] == [1]
    assert [c["file_name"] for c in data["cases"]] == ["TC.xlsx"]


def test_file_rows_keep_the_sheets_in_the_order_the_workbook_names_them():
    """Not alphabetical: the table should read alongside the file's own tabs."""
    data = aggregate.file_rows([
        case(sheet="Payment", scope="FPT", result="OK"),
        case(sheet="Login", scope="FPT", result="OK"),
        case(sheet="Account", scope="FPT", result="OK"),
    ], "TC.xlsx")

    assert [r["sheet"] for r in data["rows"]] == ["Payment", "Login", "Account"]


def test_the_sheet_rows_of_a_file_add_up_to_its_summary_rows():
    """The property that stops this page disagreeing with Summary."""
    cases = [
        case(sheet="Login", scope="FPT", result="OK"),
        case(sheet="Login", scope="JP", result="NG", row_num=5),
        case(sheet="Search", scope="FPT", result="保留", row_num=6),
        case(sheet="Search", scope="FPT", result=None, row_num=7),
        case(sheet="Search", scope="JP", result="対象外", pic=None, row_num=8),
    ]

    summary, _ = aggregate.summary_rows(cases, by_scope=True)
    rows = aggregate.file_rows(cases, "TC.xlsx")["rows"]

    for want in summary:
        mine = [r for r in rows if r["scope"] == want["scope"] and r["device"] == want["device"]]
        assert sum(r["total"] for r in mine) == want["total"]
        for key in aggregate.STATUS.keys:
            assert sum(r[key] for r in mine) == want[key]


def test_file_rows_report_a_scope_group_outside_the_plan(jp_is_not_in_the_plan):
    """Unlike Daily and Review: the Scope filter is half the point of the page."""
    data = aggregate.file_rows([
        case(scope="FPT", result="OK"),
        case(scope="JP", result="OK", row_num=5),
    ], "TC.xlsx")

    assert [r["scope"] for r in data["rows"]] == ["FPT", "JP"]
    assert [c["scope"] for c in data["cases"]] == ["FPT", "JP"]


def test_an_out_of_scope_case_is_counted_in_its_column_but_not_in_a_sheet_total():
    data = aggregate.file_rows([
        case(scope="FPT", result="OK"),
        case(scope="FPT", result="対象外", pic=None, row_num=5),
    ], "TC.xlsx")

    row = data["rows"][0]
    assert row["OOS"] == 1
    assert row["total"] == 1, "a case outside the plan cannot inflate the denominator"


def test_every_file_case_carries_the_status_it_was_classified_as():
    """Derived statuses included -- the row, not the Result cell, decides."""
    data = aggregate.file_rows([
        case(case_no="TC-1", scope="FPT", result="対象外", pic="lee"),
        case(case_no="TC-2", scope="FPT", result="対象外", pic=None, row_num=5),
    ], "TC.xlsx")

    assert [(c["case_no"], c["status"]) for c in data["cases"]] == [
        ("TC-1", "Cancel"), ("TC-2", "OOS"),
    ]


def test_every_file_row_names_the_device_family_it_belongs_to():
    data = aggregate.file_rows([
        case(device="iPhone Min size", result="OK"),
        case(device="iPhone Max size", result="NG"),
        case(device="Android 14", result="OK"),
    ], "TC.xlsx")

    assert {r["device"]: r["device_family"] for r in data["rows"]} == {
        "iPhone Min size": "iPhone",
        "iPhone Max size": "iPhone",
        "Android 14": "Android 14",
    }


def test_an_unknown_file_has_no_rows_and_no_cases():
    data = aggregate.file_rows([case(result="OK")], "Nope.xlsx")

    assert data == {"file": "Nope.xlsx", "rows": [], "cases": []}


def test_every_file_case_names_the_scope_group_it_was_classified_into(fixed_scopes):
    """The rows are keyed by group and the cases carry a raw Scope string, so
    the page would filter the two halves by two different vocabularies unless
    the classification rides along — the reasoning behind `device_family`."""
    data = aggregate.file_rows([
        case(scope="FPT (JM Support)", result="OK"),
        case(scope="Vendor", result="OK", row_num=5),
    ], "TC.xlsx")

    assert [(c["scope"], c["scope_group"]) for c in data["cases"]] == [
        ("FPT (JM Support)", "FPT"),
        ("Vendor", SCOPES.classify("Vendor")),
    ]
    assert {c["scope_group"] for c in data["cases"]} == {r["scope"] for r in data["rows"]}


# --- Cases of one status, for Detail's on-demand fetch ---------------------


def test_status_cases_holds_exactly_the_cases_of_that_status():
    cases = aggregate.status_cases([
        case(result="OK"),
        case(result="NG", row_num=5),
        case(result="OK", row_num=6),
    ], "OK")

    assert [c["row_num"] for c in cases] == [4, 6]
    assert {c["status"] for c in cases} == {"OK"}


def test_status_cases_classifies_the_whole_row_not_the_result_cell():
    """`対象外` with a PIC is a Cancel; without one it was never in the plan.

    The same rule every aggregate follows — `classify_case`, never `classify`.
    """
    owned = case(result="対象外", pic="lee")
    unowned = case(result="対象外", row_num=5)

    assert [c["row_num"] for c in aggregate.status_cases([owned, unowned], "Cancel")] == [4]
    assert [c["row_num"] for c in aggregate.status_cases([owned, unowned], "OOS")] == [5]


def test_the_statuses_between_them_account_for_every_loaded_case():
    """Detail fetches one status at a time, so the slices must partition the load.

    A case appearing in two of them would be double-counted the moment two
    status cards are pressed; one appearing in none could never be reached.
    """
    loaded = [
        case(result="OK"), case(result="NG", row_num=5),
        case(result="TBD", row_num=6), case(result=None, row_num=7),
        case(result="対象外", row_num=8), case(scope="JP", result="OK", row_num=9),
    ]

    seen = [(c["file_name"], c["row_num"])
            for key in aggregate.STATUS.keys
            for c in aggregate.status_cases(loaded, key)]

    assert sorted(seen) == sorted((c.file_name, c.row_num) for c in loaded)


def test_status_cases_keep_work_the_plan_excludes(jp_is_not_in_the_plan):
    """Detail's scope cards are how JP work is opted into, so it must arrive.

    That makes this endpoint's coverage Summary's rather than Review's — the
    same reasoning `file_rows` follows.
    """
    cases = aggregate.status_cases([
        case(result="OK", scope="FPT"),
        case(result="OK", scope="JP", row_num=5),
    ], "OK")

    assert [c["scope"] for c in cases] == ["FPT", "JP"]


def test_every_status_case_names_the_scope_group_it_was_classified_into(fixed_scopes):
    """Detail filters by group and the cell carries a raw string — one
    vocabulary, for the reason `file_rows` carries `scope_group` too."""
    cases = aggregate.status_cases([
        case(result="OK", scope="FPT (JM Support)"),
        case(result="OK", scope="Vendor", row_num=5),
    ], "OK")

    assert [(c["scope"], c["scope_group"]) for c in cases] == [
        ("FPT (JM Support)", "FPT"),
        ("Vendor", SCOPES.classify("Vendor")),
    ]


def test_status_cases_keeps_the_source_order_of_the_cases():
    cases = aggregate.status_cases([
        case(result="OK", row_num=9), case(result="OK", row_num=4),
    ], "OK")

    assert [c["row_num"] for c in cases] == [9, 4]


def test_an_unknown_status_key_has_no_cases():
    """Whether that is worth a 400 is the endpoint's business, not the aggregate's."""
    assert aggregate.status_cases([case(result="OK")], "Nope") == []


def test_every_status_case_names_the_device_family_it_belongs_to():
    """Summary merges a handset's sizes into one row, and that row is a door
    into Detail. Re-deriving the family in JavaScript would mean writing the
    substring rules there — `summary_rows` attaches it to every row for the
    same reason."""
    cases = aggregate.status_cases([
        case(device="iPhone Min size", result="OK"),
        case(device="Android 14", result="OK", row_num=5),
    ], "OK")

    assert [(c["device"], c["device_family"]) for c in cases] == [
        ("iPhone Min size", "iPhone"),
        ("Android 14", "Android 14"),
    ]
