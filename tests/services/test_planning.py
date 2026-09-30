"""The planning service: the plan, what actually happened, and what is left.

The repository is a stand-in here, which is what `PlanRepository` exists for —
these tests are about the reasoning, and reasoning that needs a file on disk to
be exercised is reasoning in the wrong layer.
"""
import pytest

from tcm.domain import case as models
from tcm.domain.plan import DayPlan, PlanSettings, PlanEntry
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

    _settings = None

    def settings(self):
        return self._settings or PlanSettings()

    def put_settings(self, settings):
        self._settings = settings

    _members = ()

    def members(self):
        return list(self._members)


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
    """`actual` is worked: a Pending is still in the pile."""
    svc = service()
    svc.save_day("2026-09-22", [entry(pic="An")])
    view = svc.day_view("2026-09-22", [
        case(pic="An", test_date="2026-09-22", result="OK"),
        case(pic="An", test_date="2026-09-22", result="保留", row_num=5),
    ])
    assert view["rows"][0]["actual"] == 1


def test_a_cancelled_case_counts_toward_the_plan():
    """Plan 100, 90 OK and 10 Cancel is on plan: the ten are no longer work to do."""
    svc = service()
    svc.save_day("2026-09-22", [entry(pic="An", planned=2)])
    view = svc.day_view("2026-09-22", [
        case(pic="An", test_date="2026-09-22", result="OK"),
        case(pic="An", test_date="2026-09-22", result="対象外", row_num=5),
    ])
    assert view["rows"][0]["diff"] == 0


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


def test_the_calendar_counts_a_cancelled_case_as_done():
    """So against plan is worked: a Cancel left the pile without being run."""
    svc = service()
    days = svc.calendar_view(None, None, [
        case(pic="An", test_date="2026-09-22", result="OK", row_num=1),
        case(pic="An", test_date="2026-09-22", result="対象外", row_num=2)])["days"]
    assert days[0]["actual"] == 2


def test_the_calendar_no_longer_carries_per_person_totals():
    """The Member tab asks `/api/member/*` for those; two sources would drift."""
    view = service().calendar_view(None, None, [])
    assert "by_pic" not in view and "actual_by_pic" not in view


# --- Daily's plan, under Daily's filters ---------------------------------------
# Daily filters its rows by file, device, PIC and date, so the plan it measures
# them against has to be filtered the same way: a PIC's worked cases over the
# whole team's plan is how one member on plan read as 60% attained.

def _two_members():
    svc = service()
    svc.save_day("2026-09-23", [entry(pic="An", file="A.xlsx", planned=30),
                                entry(pic="Binh", file="B.xlsx", planned=20)])
    cases = ([case(pic="An", file_name="A.xlsx", test_date="2026-09-23", result="OK", row_num=i)
              for i in range(20)]
             + [case(pic="An", file_name="A.xlsx", test_date="2026-09-23", result="対象外",
                     row_num=100 + i) for i in range(10)]
             + [case(pic="Binh", file_name="B.xlsx", test_date="2026-09-23", result="OK",
                     row_num=200 + i) for i in range(25)])
    return svc, cases


def test_daily_plan_unfiltered_is_the_whole_team():
    svc, cases = _two_members()
    assert svc.daily_plan(cases)["days"] == [
        {"date": "2026-09-23", "planned": 50, "worked": 55, "attain": 1.1}]


def test_daily_plan_follows_a_pic_filter_on_both_sides():
    svc, cases = _two_members()
    assert svc.daily_plan(cases, pic="An")["days"] == [
        {"date": "2026-09-23", "planned": 30, "worked": 30, "attain": 1.0}]


def test_daily_plan_follows_a_file_filter_on_both_sides():
    svc, cases = _two_members()
    day = svc.daily_plan(cases, file="B.xlsx")["days"][0]
    assert (day["planned"], day["worked"]) == (20, 25)


def test_a_filter_nobody_planned_has_no_plan_rather_than_a_plan_of_zero():
    svc, cases = _two_members()
    cases += [case(pic="Chi", file_name="A.xlsx", test_date="2026-09-23", result="OK", row_num=300)]
    assert svc.daily_plan(cases, pic="Chi")["days"] == [
        {"date": "2026-09-23", "planned": None, "worked": 1, "attain": None}]


def test_daily_plan_respects_the_date_range():
    svc, cases = _two_members()
    assert svc.daily_plan(cases, start="2026-09-24")["days"] == []


# --- the phase and the day board -------------------------------------------
# 2026-09-22 is a Tuesday. The load: ten cases nobody has run, four An ran on
# Monday and two An ran today.

def _load():
    return ([case(row_num=i) for i in range(10)]
            + [case(row_num=20 + i, result="OK", pic="An", test_date="2026-09-21") for i in range(4)]
            + [case(row_num=30 + i, result="OK", pic="An", test_date="2026-09-22") for i in range(2)])


def test_board_counts_the_day_s_devices_by_family_not_by_name():
    """Two iPhone blocks and an iPad read as "2 iPhone · 1 iPad", in config order."""
    svc = service()
    svc.save_settings({"phase_start": "2026-09-21", "phase_end": "2026-09-25"})
    svc.save_day("2026-09-23", [entry(device="iPad Air", planned=2),
                                entry(device="iPhone Min size", planned=2),
                                entry(pic="Bo", device="iPhone Max size", planned=2)])
    cs = [case(device=d, row_num=i) for i, d in
          enumerate(["iPad Air", "iPhone Min size", "iPhone Max size"])]
    assert svc.board_view(cs, "2026-09-23")["device_families"] == [
        {"key": "iPhone", "label": "iPhone", "slots": 2},
        {"key": "iPad", "label": "iPad", "slots": 1}]


def test_board_joins_plan_to_worked_and_reports_remaining_at_start():
    svc = service()
    svc.save_settings({"phase_start": "2026-09-21", "phase_end": "2026-09-25"})
    svc.save_day("2026-09-22", [entry(pic="An", planned=5), entry(pic="Bo", planned=4)])
    b = svc.board_view(_load(), "2026-09-22")
    slot = b["slots"][0]
    assert (slot["remaining"], slot["remaining_at_start"]) == (10, 12)
    assert slot["need_through"] == 9 and slot["over_by"] == 0
    cell = {c["pic"]: c for c in b["cells"]}
    assert (cell["An"]["planned"], cell["An"]["worked"]) == (5, 2)
    assert b["load"] == {"An": 5, "Bo": 4}
    assert b["members"] == ["An", "Bo"]


def test_board_flags_a_plan_bigger_than_what_is_left():
    svc = service()
    svc.save_day("2026-09-22", [entry(pic="An", planned=20)])
    assert svc.board_view(_load(), "2026-09-22")["slots"][0]["over_by"] == 8


def test_board_counts_other_days_from_today_on():
    svc = service()
    svc.save_day("2026-09-21", [entry(planned=7)])            # past: not a claim on what is left
    svc.save_day("2026-09-22", [entry(planned=5)])
    svc.save_day("2026-09-24", [entry(planned=3)])
    slot = svc.board_view(_load(), "2026-09-22")["slots"][0]
    assert slot["planned_other_days"] == 3


def test_board_keeps_a_slot_whose_file_is_no_longer_loaded():
    svc = service()
    svc.save_day("2026-09-22", [entry(file="Gone.xlsx", planned=3)])
    slots = svc.board_view(_load(), "2026-09-22")["slots"]
    gone = [s for s in slots if s["file"] == "Gone.xlsx"][0]
    assert gone["remaining"] == 0 and gone["over_by"] == 3
    assert slots[-1]["file"] == "Gone.xlsx"


def test_board_offers_slots_with_work_left_that_the_day_does_not_have():
    svc = service()
    cs = _load() + [case(device="iPad", row_num=50)]
    svc.save_day("2026-09-22", [entry(device="iPhone", planned=2)])
    svc.save_day("2026-09-23", [entry(device="iPad", planned=1)])
    avail = svc.board_view(cs, "2026-09-22")["available"]
    assert [(a["file"], a["device"]) for a in avail] == [("TC.xlsx", "iPad")]
    # The editor's "Other days" figure for a slot the day does not have yet.
    assert avail[0]["planned_other_days"] == 1


def test_worked_without_a_pic_counts_but_is_not_a_member():
    svc = service()
    cs = _load() + [case(row_num=99, result="OK", test_date="2026-09-22")]
    b = svc.board_view(cs, "2026-09-22")
    assert "N/A" not in b["members"]
    assert sum(c["worked"] for c in b["cells"]) == 3


def test_phase_view_kpis():
    svc = service()
    svc.save_settings({"phase_start": "2026-09-21", "phase_end": "2026-09-25"})
    svc.save_day("2026-09-22", [entry(planned=5)])
    svc.save_day("2026-09-23", [entry(planned=5)])
    k = svc.phase_view(_load())["kpis"]
    assert (k["remaining"], k["at_start"]) == (10, 16)
    assert (k["planned_today"], k["done_today"], k["members_today"]) == (5, 2, 1)
    assert k["needed_pace"] == 3                       # 10 left over Tue..Fri = 4 days
    # Today contributes only what is still to run (5 planned - 2 done = 3), then
    # Wednesday's 5: 8 of 10 covered, so the plan does not finish the phase.
    assert k["plan_finish"] is None and k["unplanned"] == 2
    # Monday is the only past phase day: 4 worked -> 4/day; 10 / 4 -> 3 workdays after Tue.
    assert k["rate"] == 4.0 and k["forecast_finish"] == "2026-09-25"


def test_a_plan_that_covers_what_is_left_names_its_finish_day():
    svc = service()
    svc.save_settings({"phase_start": "2026-09-21", "phase_end": "2026-09-25"})
    svc.save_day("2026-09-22", [entry(planned=5)])
    svc.save_day("2026-09-23", [entry(planned=4)])
    svc.save_day("2026-09-24", [entry(planned=9)])
    k = svc.phase_view(_load())["kpis"]
    assert k["plan_finish"] == "2026-09-24" and k["unplanned"] == 0


def test_no_execution_means_no_forecast():
    svc = service()
    svc.save_settings({"phase_start": "2026-09-22", "phase_end": "2026-09-25"})
    k = svc.phase_view([case(row_num=i) for i in range(5)])["kpis"]
    assert k["forecast_finish"] is None and k["plan_finish"] is None and k["unplanned"] == 5


def test_burndown_series_start_at_r0_and_reconcile():
    svc = service()
    svc.save_settings({"phase_start": "2026-09-21", "phase_end": "2026-09-25"})
    b = svc.phase_view(_load())["burndown"]
    assert b["actual"] == [16, 12, 10]
    assert len(b["plan"]) == len(b["axis"]) + 1
    assert b["axis"][b["today_index"]] == "2026-09-22"


def test_the_grid_marks_a_future_plan_beyond_what_is_left():
    svc = service()
    svc.save_settings({"phase_start": "2026-09-21", "phase_end": "2026-09-25"})
    svc.save_day("2026-09-23", [entry(planned=8)])
    svc.save_day("2026-09-24", [entry(planned=8)])
    cells = svc.phase_view(_load())["grid"]["slots"][0]["cells"]
    assert cells["2026-09-21"]["worked"] == 4
    assert not cells["2026-09-23"]["over_remaining"]
    assert cells["2026-09-24"]["over_remaining"]         # 16 planned > 12 left at start of today


def test_the_grid_runs_monday_to_friday_from_the_start_week_to_the_end_week():
    svc = service()
    svc.save_settings({"phase_start": "2026-09-23", "phase_end": "2026-10-06"})
    g = svc.phase_view(_load())["grid"]
    assert [w["start"] for w in g["weeks"]] == ["2026-09-21", "2026-09-28", "2026-10-05"]
    assert g["days"][0] == "2026-09-21" and g["days"][-1] == "2026-10-09"
    assert len(g["days"]) == 15
    first = g["weeks"][0]["days"]
    assert [d["in_phase"] for d in first] == [False, False, True, True, True]
    assert g["current"] == 0                              # today, 22 Sept, is in week one


def test_the_grid_totals_each_slot_against_every_plan_the_phase_holds():
    svc = service()
    svc.save_settings({"phase_start": "2026-09-21", "phase_end": "2026-09-25"})
    svc.save_day("2026-09-21", [entry(planned=3)])        # past
    svc.save_day("2026-09-24", [entry(planned=5)])        # future
    svc.save_day("2026-10-20", [entry(planned=2)])        # past the phase end: still a plan
    cs = _load() + [case(row_num=90, result="保留"),       # Pending: still to run
                    case(row_num=91, result="対象外")]     # no PIC: Out Of Scope, not a case
    slot = svc.phase_view(cs)["grid"]["slots"][0]
    assert slot["total"] == 17
    assert slot["plan_ahead"] == 7                        # the past day's 3 is history
    assert slot["remaining"] == 11
    assert slot["need_plan"] == 4                         # 11 left, 5 + 2 planned from today on
    assert slot["plan_ahead"] + slot["need_plan"] == slot["remaining"]


def test_need_plan_takes_only_what_today_s_plan_still_has_to_run():
    """An already ran 2 there today, and Remain has already dropped them."""
    svc = service()
    svc.save_settings({"phase_start": "2026-09-21", "phase_end": "2026-09-25"})
    svc.save_day("2026-09-22", [entry(pic="An", planned=5)])
    slot = svc.phase_view(_load())["grid"]["slots"][0]
    assert (slot["remaining"], slot["plan_ahead"], slot["need_plan"]) == (10, 3, 7)


def test_need_plan_is_capped_per_device_at_zero():
    svc = service()
    svc.save_settings({"phase_start": "2026-09-21", "phase_end": "2026-09-25"})
    svc.save_day("2026-09-24", [entry(planned=40), entry(pic="Bo", device="iPad", planned=3)])
    cs = _load() + [case(device="iPad", row_num=i) for i in range(5)]
    v = svc.phase_view(cs)
    need = {s["device"]: s["need_plan"] for s in v["grid"]["slots"]}
    assert need == {"iPhone": 0, "iPad": 2}               # iPhone's excess does not cover iPad
    # Plan ahead is not capped: planning past what is left is what it is there to show.
    assert {s["device"]: s["plan_ahead"] for s in v["grid"]["slots"]} == {"iPhone": 40, "iPad": 3}
    # The table's answer and the Unplanned KPI are one figure.
    assert sum(need.values()) == v["kpis"]["unplanned"]


def test_the_grid_lists_a_finished_slot_so_its_total_is_on_screen():
    svc = service()
    svc.save_settings({"phase_start": "2026-10-05", "phase_end": "2026-10-09"})
    cs = _load() + [case(file_name="Done.xlsx", row_num=1, result="OK", pic="An",
                         test_date="2026-09-01")]
    files = [s["file"] for s in svc.phase_view(cs)["grid"]["slots"]]
    assert "Done.xlsx" in files


def test_the_forecast_window_changes_the_rate():
    svc = service(today="2026-09-24")
    svc.save_settings({"phase_start": "2026-09-21", "phase_end": "2026-09-25"})
    cs = ([case(row_num=i) for i in range(10)]
          + [case(row_num=20 + i, result="OK", pic="An", test_date="2026-09-21") for i in range(6)]
          + [case(row_num=40 + i, result="OK", pic="An", test_date="2026-09-23") for i in range(2)])
    assert svc.phase_view(cs, window="all")["kpis"]["rate"] == round(8 / 3, 2)
    assert svc.phase_view(cs, window="3")["kpis"]["rate"] == round(8 / 3, 2)


def test_empty_workspace_is_zeros_not_an_error():
    v = service().phase_view([])
    assert v["kpis"]["remaining"] == 0 and v["grid"]["slots"] == []
    assert service().board_view([], "2026-09-22")["slots"] == []


def test_settings_default_from_the_load():
    s = service().get_settings(_load())
    assert (s["phase_start"], s["phase_end"], s["stored"]) == ("2026-09-21", "2026-09-29", False)


def test_saved_settings_win_over_the_defaults():
    svc = service()
    svc.save_settings({"phase_start": "2026-09-01", "phase_end": "2026-09-30", "daily_target": 20})
    s = svc.get_settings(_load())
    assert (s["phase_start"], s["daily_target"], s["stored"]) == ("2026-09-01", 20, True)


def test_weekend_work_inside_the_phase_still_burns_down():
    """Saturday is not on the axis, but the cases run on it left the pile."""
    svc = service()
    svc.save_settings({"phase_start": "2026-09-18", "phase_end": "2026-09-25"})
    cs = _load() + [case(row_num=60 + i, result="OK", pic="An", test_date="2026-09-19")
                    for i in range(3)]
    v = svc.phase_view(cs)
    assert v["burndown"]["actual"][-1] == v["kpis"]["remaining"]


def test_the_burndown_reconciles_with_excluded_and_undated_cases():
    """at_start - worked since the start == remaining, whatever else the load holds.

    An Out Of Scope case (対象外 with no PIC) is outside `counted`, so it is in
    neither pile; an OK with no test date left the pile before the phase could
    date it. Both used to inflate `at_start` by one each.
    """
    svc = service()
    svc.save_settings({"phase_start": "2026-09-21", "phase_end": "2026-09-25"})
    cs = _load() + [case(row_num=70, result="対象外"),          # OOS: excluded
                    case(row_num=71, result="OK", pic="An")]     # worked, undated
    v = svc.phase_view(cs)
    assert v["kpis"]["at_start"] == 16
    assert v["burndown"]["actual"][-1] == v["kpis"]["remaining"] == 10


# --- the board's members ---------------------------------------------------

def test_the_board_offers_the_roster_when_there_is_one():
    repo = FakePlanRepository({"2026-09-22": DayPlan.from_dict(
        "2026-09-22", {"entries": [entry(pic="Cy")]})})
    repo._members = ("An", "Bo")
    svc = PlanningService(repo, today=lambda: "2026-09-22")
    board = svc.board_view([case(pic="Zed", result="OK", test_date="2026-09-22")], "2026-09-22")
    # The roster, plus whoever the day's plan names -- not every PIC in the data.
    assert board["members"] == ["An", "Bo", "Cy"]


def test_without_a_roster_the_board_offers_everyone_as_before():
    svc = service()
    board = svc.board_view([case(pic="Zed", result="OK", test_date="2026-09-22")], "2026-09-22")
    assert board["members"] == ["Zed"]
