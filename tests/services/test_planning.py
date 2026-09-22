"""The planning service: the plan, what actually happened, and what is left.

The repository is a stand-in here, which is what `PlanRepository` exists for —
these tests are about the reasoning, and reasoning that needs a file on disk to
be exercised is reasoning in the wrong layer.
"""
import pytest

from tcm.domain import case as models
from tcm.domain.plan import DayPlan, PlanEntry
from tcm.services.planning import PlanningService


class FakePlanRepository:
    """The plan in a dict. Answers the three methods `PlanRepository` names."""

    def __init__(self, days=None):
        self._days = dict(days or {})

    def day(self, date):
        return self._days.get(date) or DayPlan.empty(date)

    def days(self):
        return [self._days[d] for d in sorted(self._days)]

    def put_day(self, day):
        self._days[day.date] = day


def service(days=None, today="2026-09-22"):
    return PlanningService(FakePlanRepository(days), today=lambda: today)


def entry(pic="An", file="TC.xlsx", device="iPhone", planned=30):
    return {"pic": pic, "file": file, "device": device, "planned": planned}


def case(**kwargs):
    return models.TestCase(**{
        "file_name": "TC.xlsx", "sheet": "Login", "device": "iPhone", "row_num": 4,
        "scope": "FPT",
        **kwargs,
    })


# --- the lazy baseline -----------------------------------------------------

def test_planning_a_future_day_freezes_nothing():
    """Editing tomorrow is planning, not adjusting: there is nothing to diverge from."""
    svc = service(today="2026-09-22")
    svc.save_day("2026-09-24", [entry()])
    assert svc.get_day("2026-09-24").baseline is None


def test_the_first_edit_on_the_day_itself_freezes_what_was_there_before_it():
    svc = service(today="2026-09-20")
    svc.save_day("2026-09-22", [entry(planned=30)])          # planned two days ahead
    # The day arrives, and the plan is rearranged. The *pre-edit* state is what
    # the day is judged against.
    svc = PlanningService(svc.repository, today=lambda: "2026-09-22")
    svc.save_day("2026-09-22", [entry(file="Other.xlsx", planned=10)])

    day = svc.get_day("2026-09-22")
    assert [e.file for e in day.baseline] == ["TC.xlsx"]
    assert [e.file for e in day.entries] == ["Other.xlsx"]


def test_a_second_adjustment_leaves_the_baseline_where_it_was():
    """Otherwise the baseline chases the plan and the day always looks on target."""
    svc = service(today="2026-09-20")
    svc.save_day("2026-09-22", [entry(planned=30)])
    svc = PlanningService(svc.repository, today=lambda: "2026-09-22")
    svc.save_day("2026-09-22", [entry(planned=10)])
    svc.save_day("2026-09-22", [entry(planned=5)])
    assert [e.planned for e in svc.get_day("2026-09-22").baseline] == [30]


def test_the_first_edit_of_a_day_that_never_had_a_plan_freezes_an_empty_baseline():
    """Deciding at 9am to test something unplanned still counts as an adjustment."""
    svc = service(today="2026-09-22")
    svc.save_day("2026-09-22", [entry()])
    assert svc.get_day("2026-09-22").baseline == []


def test_editing_a_past_day_is_an_adjustment_too():
    svc = service(today="2026-09-24")
    svc.save_day("2026-09-22", [entry(planned=30)])
    assert svc.get_day("2026-09-22").baseline == []


def test_a_day_nobody_adjusted_has_no_baseline_and_that_is_correct():
    """Nothing diverged, so the plan as it stands *is* what was planned."""
    svc = service(today="2026-09-20")
    svc.save_day("2026-09-22", [entry()])
    assert svc.get_day("2026-09-22").baseline is None


def test_rebaseline_makes_the_current_plan_the_one_to_judge_against():
    svc = service(today="2026-09-20")
    svc.save_day("2026-09-22", [entry(planned=30)])
    svc = PlanningService(svc.repository, today=lambda: "2026-09-22")
    svc.save_day("2026-09-22", [entry(planned=10)])
    svc.rebaseline("2026-09-22")
    assert [e.planned for e in svc.get_day("2026-09-22").baseline] == [10]


def test_the_freeze_is_stamped_with_when_it_happened():
    svc = service(today="2026-09-22")
    svc.save_day("2026-09-22", [entry()])
    assert svc.get_day("2026-09-22").baseline_at


def test_a_refused_row_does_not_reach_the_store():
    svc = service(today="2026-09-22")
    with pytest.raises(ValueError, match="planned"):
        svc.save_day("2026-09-22", [entry(planned=0)])
    assert svc.get_day("2026-09-22").entries == []


# --- the day view ----------------------------------------------------------

def test_a_planned_row_is_joined_to_what_that_person_actually_did():
    svc = service()
    svc.save_day("2026-09-22", [entry(pic="An", planned=30)])
    view = svc.day_view("2026-09-22", [
        case(pic="An", test_date="2026-09-22", result="OK"),
        case(pic="An", test_date="2026-09-22", result="NG", row_num=5),
    ])

    assert len(view["rows"]) == 1
    row = view["rows"][0]
    assert row["planned"] == 30
    assert row["actual"] == 2
    assert row["diff"] == -28


def test_work_on_another_day_does_not_count_toward_this_one():
    svc = service()
    svc.save_day("2026-09-22", [entry(pic="An")])
    view = svc.day_view("2026-09-22", [case(pic="An", test_date="2026-09-21", result="OK")])
    assert view["rows"][0]["actual"] == 0


def test_a_case_run_but_not_finished_is_not_counted_as_done():
    """`actual` is executed work, the same measure Productivity and Summary use."""
    svc = service()
    svc.save_day("2026-09-22", [entry(pic="An")])
    view = svc.day_view("2026-09-22", [
        case(pic="An", test_date="2026-09-22", result="OK"),
        case(pic="An", test_date="2026-09-22", result="保留", row_num=5),
    ])
    assert view["rows"][0]["actual"] == 1


def test_work_nobody_planned_still_shows_up():
    """A table that hid it would hide work that was done. The row has no plan."""
    svc = service()
    svc.save_day("2026-09-22", [entry(pic="An", file="TC.xlsx")])
    view = svc.day_view("2026-09-22", [
        case(pic="Binh", file_name="Other.xlsx", test_date="2026-09-22", result="OK"),
    ])

    unplanned = [r for r in view["rows"] if r["pic"] == "Binh"]
    assert len(unplanned) == 1
    assert unplanned[0]["planned"] is None
    assert unplanned[0]["actual"] == 1


def test_the_day_view_totals_both_sides():
    svc = service()
    svc.save_day("2026-09-22", [entry(pic="An", planned=30),
                                entry(pic="Binh", planned=20)])
    view = svc.day_view("2026-09-22", [case(pic="An", test_date="2026-09-22", result="OK")])
    assert view["planned_total"] == 50
    assert view["actual_total"] == 1


def test_the_day_view_carries_the_baseline_for_each_row():
    svc = service(today="2026-09-20")
    svc.save_day("2026-09-22", [entry(pic="An", planned=30)])
    svc = PlanningService(svc.repository, today=lambda: "2026-09-22")
    svc.save_day("2026-09-22", [entry(pic="An", planned=10)])
    view = svc.day_view("2026-09-22", [])
    assert view["rows"][0]["baseline"] == 30
    assert view["baseline_total"] == 30


# --- the person view -------------------------------------------------------

def test_the_person_view_lists_one_persons_days():
    svc = service()
    svc.save_day("2026-09-22", [entry(pic="An", planned=30), entry(pic="Binh", planned=20)])
    svc.save_day("2026-09-23", [entry(pic="An", planned=15)])

    view = svc.person_view("An", [])
    assert [r["date"] for r in view["rows"]] == ["2026-09-22", "2026-09-23"]
    assert view["planned_total"] == 45


def test_the_person_view_counts_what_that_person_actually_ran():
    svc = service()
    svc.save_day("2026-09-22", [entry(pic="An", planned=30)])
    view = svc.person_view("An", [
        case(pic="An", test_date="2026-09-22", result="OK"),
        case(pic="Binh", test_date="2026-09-22", result="OK", row_num=5),
    ])
    assert view["actual_total"] == 1


# --- the calendar ----------------------------------------------------------

def test_the_calendar_totals_each_day():
    svc = service()
    svc.save_day("2026-09-22", [entry(pic="An", planned=30), entry(pic="Binh", planned=20)])
    svc.save_day("2026-09-23", [entry(pic="An", planned=15)])

    days = svc.calendar_view(None, None, [])["days"]
    assert [(d["date"], d["planned"], d["people"]) for d in days] == [
        ("2026-09-22", 50, 2),
        ("2026-09-23", 15, 1),
    ]


def test_the_calendar_can_be_bounded_to_a_range():
    svc = service()
    for date in ("2026-09-21", "2026-09-22", "2026-09-23"):
        svc.save_day(date, [entry()])
    days = svc.calendar_view("2026-09-22", "2026-09-22", [])["days"]
    assert [d["date"] for d in days] == ["2026-09-22"]


def test_a_day_worked_without_a_plan_still_appears_in_the_calendar():
    svc = service()
    days = svc.calendar_view(None, None, [
        case(pic="An", test_date="2026-09-22", result="OK")])["days"]
    assert [(d["date"], d["planned"], d["actual"]) for d in days] == [("2026-09-22", 0, 1)]


# --- the suggestion --------------------------------------------------------

def test_suggestions_are_the_blocks_with_cases_left():
    svc = service()
    rows = svc.suggest([case(result=None), case(result="OK", row_num=5)], "2026-09-22")
    assert [(r["file"], r["device"], r["remaining"]) for r in rows] == [
        ("TC.xlsx", "iPhone", 1)]


def test_suggestions_can_be_narrowed_to_one_device_family():
    """The point of the control: the tester has one handset in their hand."""
    svc = service()
    rows = svc.suggest([
        case(device="iPhone Min size", result=None),
        case(device="iPad", result=None, row_num=5),
    ], "2026-09-22", device_family="iPhone")
    assert [r["device"] for r in rows] == ["iPhone Min size"]


def test_work_already_given_to_someone_today_is_subtracted():
    svc = service()
    svc.save_day("2026-09-22", [entry(pic="An", file="TC.xlsx", device="iPhone", planned=3)])
    rows = svc.suggest([case(result=None, row_num=i) for i in range(10)], "2026-09-22")

    assert rows[0]["remaining"] == 10
    assert rows[0]["assigned"] == 3
    assert rows[0]["free"] == 7


def test_the_suggestion_names_who_already_has_it():
    """A number that shrank with no explanation is one nobody trusts."""
    svc = service()
    svc.save_day("2026-09-22", [entry(pic="An", planned=3)])
    rows = svc.suggest([case(result=None, row_num=i) for i in range(10)], "2026-09-22")
    assert rows[0]["assigned_to"] == [{"pic": "An", "planned": 3}]


def test_a_block_given_out_entirely_has_nothing_free_but_is_still_listed():
    """Adding a second person to it is a decision, not an error."""
    svc = service()
    svc.save_day("2026-09-22", [entry(pic="An", planned=50)])
    rows = svc.suggest([case(result=None, row_num=i) for i in range(10)], "2026-09-22")
    assert rows[0]["free"] == 0


def test_blocks_with_nothing_free_sort_below_the_ones_with_work_left():
    svc = service()
    svc.save_day("2026-09-22", [entry(pic="An", file="Taken.xlsx", planned=50)])
    rows = svc.suggest(
        [case(file_name="Taken.xlsx", result=None, row_num=i) for i in range(2)]
        + [case(file_name="Free.xlsx", result=None, row_num=i) for i in range(9)],
        "2026-09-22")
    assert [r["file"] for r in rows] == ["Free.xlsx", "Taken.xlsx"]


def test_suggestions_put_the_nearly_finished_block_first():
    svc = service()
    rows = svc.suggest(
        [case(file_name="Big.xlsx", result=None, row_num=i) for i in range(9)]
        + [case(file_name="Small.xlsx", result=None, row_num=i) for i in range(2)],
        "2026-09-22")
    assert [r["file"] for r in rows] == ["Small.xlsx", "Big.xlsx"]


def test_the_calendar_also_totals_each_persons_plan():
    """Productivity measures a member against what *they* were planned for.

    It reports over every day at once, so a per-day calendar cannot answer it
    and a request per member would be one request per row. The figure rides on
    the calendar instead, which the browser already fetches once.
    """
    svc = service()
    svc.save_day("2026-09-22", [entry(pic="An", planned=30), entry(pic="Binh", planned=20)])
    svc.save_day("2026-09-23", [entry(pic="An", planned=15)])

    assert svc.calendar_view(None, None, [])["by_pic"] == {"An": 45, "Binh": 20}


def test_the_per_person_totals_respect_the_range():
    svc = service()
    svc.save_day("2026-09-22", [entry(pic="An", planned=30)])
    svc.save_day("2026-09-23", [entry(pic="An", planned=15)])

    assert svc.calendar_view("2026-09-23", None, [])["by_pic"] == {"An": 15}
