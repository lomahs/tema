"""The Member tab: each person against the plan, day by day and in total.

2026-09-21 is a Monday. Unless a test says otherwise today is Friday the 25th,
so the totals run through Thursday the 24th — today is half a day and is never
added in.
"""
import pytest

from tcm.services.members import MemberService
from tcm.services.planning import PlanningService
from tests.services.test_planning import FakePlanRepository, case, entry


def members(plans=None, today="2026-09-25", phase=None, roster=()):
    repo = FakePlanRepository()
    repo._members = roster
    planning = PlanningService(repo, today=lambda: today)
    for date, entries in (plans or {}).items():
        planning.save_day(date, entries)
    if phase:
        planning.save_settings({"phase_start": phase[0], "phase_end": phase[1]})
    return MemberService(planning)


_row = iter(range(10**6))


def ran(n, date, pic="An", result="OK", file="TC.xlsx", device="iPhone"):
    return [case(pic=pic, test_date=date, result=result, file_name=file, device=device,
                 row_num=next(_row)) for _ in range(n)]


def totals_of(svc, cases, pic="An"):
    return next(m for m in svc.totals(cases)["members"] if m["pic"] == pic)


def cell(svc, cases, date, pic="An", week="2026-09-21"):
    return svc.week(cases, week)["cells"].get(pic, {}).get(date)


# --- what counts --------------------------------------------------------------

def test_a_cancel_counts_toward_the_plan_but_not_toward_executed():
    """Plan 100, 90 OK and 10 Cancel is on plan: the ten are no longer work to do."""
    svc = members({"2026-09-22": [entry(planned=100)]})
    cases = ran(90, "2026-09-22") + ran(10, "2026-09-22", result="対象外")

    t = totals_of(svc, cases)
    assert (t["planned"], t["actual"], t["delta"]) == (100, 100, 0)
    assert (t["executed"], t["cancel"]) == (90, 10)
    assert t["attainment"] == 1.0


def test_a_pending_case_is_still_owed():
    svc = members({"2026-09-22": [entry(planned=10)]})
    cases = ran(5, "2026-09-22") + ran(5, "2026-09-22", result="保留")
    assert totals_of(svc, cases)["delta"] == -5


@pytest.mark.parametrize("first, second, adherence, delta", [
    (20, 30, 50 / 60, -10),   # behind, never caught up
    (20, 40, 1.0, 0),         # behind, caught up the next day
    (40, 20, 1.0, 0),         # ran ahead
    (40, 40, 1.0, 20),        # beat the plan: capped, the excess is in the delta
])
def test_adherence_is_cumulative_per_slot_and_capped(first, second, adherence, delta):
    svc = members({"2026-09-22": [entry(planned=30)], "2026-09-23": [entry(planned=30)]})
    cases = ran(first, "2026-09-22") + ran(second, "2026-09-23")

    t = totals_of(svc, cases)
    assert t["adherence"] == pytest.approx(adherence)
    assert t["delta"] == delta


def test_work_on_another_slot_makes_up_the_count_but_not_the_slot():
    """Planned 30 on one file, ran 20 there and 10 on another: on pace, off plan."""
    svc = members({"2026-09-22": [entry(file="A.xlsx", planned=30)]})
    cases = ran(20, "2026-09-22", file="A.xlsx") + ran(10, "2026-09-22", file="B.xlsx")

    c = cell(svc, cases, "2026-09-22")
    assert (c["planned"], c["actual"], c["delta"]) == (30, 30, 0)
    assert c["short"] == [{"file": "A.xlsx", "device": "iPhone", "planned": 30, "actual": 20}]
    assert totals_of(svc, cases)["adherence"] == pytest.approx(20 / 30)


# --- when it counts -----------------------------------------------------------

def test_today_and_the_future_are_left_out_of_the_totals():
    svc = members({"2026-09-24": [entry(planned=10)],
                   "2026-09-25": [entry(planned=30)],
                   "2026-09-28": [entry(planned=30)]})
    cases = ran(10, "2026-09-24") + ran(5, "2026-09-25")

    t = totals_of(svc, cases)
    assert (t["planned"], t["actual"], t["delta"]) == (10, 10, 0)


def test_today_is_drawn_in_progress_and_the_future_as_plan_only():
    svc = members({"2026-09-25": [entry(planned=30)], "2026-09-28": [entry(planned=30)]})
    cases = ran(5, "2026-09-25")

    today = cell(svc, cases, "2026-09-25")
    assert (today["state"], today["actual"], today["delta"]) == ("today", 5, None)
    ahead = cell(svc, cases, "2026-09-28", week="2026-09-28")
    assert (ahead["state"], ahead["planned"], ahead["actual"]) == ("future", 30, None)


def test_a_day_with_no_plan_counts_as_work_but_has_no_delta_of_its_own():
    svc = members({"2026-09-22": [entry(planned=10)]})
    cases = ran(10, "2026-09-22") + ran(7, "2026-09-23")

    t = totals_of(svc, cases)
    assert (t["planned"], t["actual"], t["delta"], t["unplanned"]) == (10, 17, 7, 7)
    c = cell(svc, cases, "2026-09-23")
    assert (c["planned"], c["actual"], c["delta"], c["state"]) == (None, 7, None, "past")


def test_work_before_the_phase_began_is_still_counted():
    svc = members(phase=("2026-09-21", "2026-09-30"))
    cases = ran(4, "2026-09-15")
    assert totals_of(svc, cases)["actual"] == 4


def test_a_day_nobody_planned_or_worked_has_no_cell():
    svc = members({"2026-09-22": [entry(planned=10)]})
    assert cell(svc, [], "2026-09-23") is None


# --- who is listed ------------------------------------------------------------

def test_members_are_the_roster_the_plan_and_whoever_worked():
    svc = members({"2026-09-22": [entry(pic="Binh")]}, roster=["Chi"])
    listed = [m["pic"] for m in svc.totals(ran(1, "2026-09-22", pic="An"))["members"]]
    assert listed == ["An", "Binh", "Chi"]


def test_cases_nobody_owns_are_a_row_of_their_own_set_aside():
    svc = members()
    rows = svc.totals(ran(3, "2026-09-22", pic=None))["members"]
    assert rows[-1]["pic"] == "N/A"
    assert rows[-1]["aside"] is True
    assert (rows[-1]["actual"], rows[-1]["delta"], rows[-1]["adherence"]) == (3, None, None)


# --- everything reconciles ----------------------------------------------------

def _mixed():
    svc = members({"2026-09-22": [entry(pic="An", planned=30), entry(pic="Binh", planned=20)],
                   "2026-09-23": [entry(pic="An", planned=30)]})
    cases = (ran(25, "2026-09-22", pic="An") + ran(5, "2026-09-22", pic="An", result="対象外")
             + ran(12, "2026-09-23", pic="An") + ran(20, "2026-09-22", pic="Binh")
             + ran(6, "2026-09-19", pic="Binh")                     # a Saturday
             + ran(3, "2026-09-16", pic=None)
             + ran(4, "2026-09-25", pic="An"))                      # today
    return svc, cases


def test_executed_plus_cancel_in_productivity_is_actual_in_the_totals():
    svc, cases = _mixed()
    actual = {m["pic"]: m["actual"] for m in svc.totals(cases)["members"]}
    for row in svc.productivity(cases)["rows"]:
        assert row["executed"] + row["Cancel"] == actual.get(row["pic"], 0)


def test_the_team_row_adds_up_its_members():
    svc, cases = _mixed()
    view = svc.totals(cases)
    for field in ("planned", "actual", "executed", "cancel", "unplanned"):
        assert view["team"][field] == sum(m[field] for m in view["members"])
    assert view["team"]["delta"] == view["team"]["actual"] - view["team"]["planned"]


def test_the_cells_of_every_week_add_up_to_the_totals_but_for_weekends():
    """A weekend has no column, so its work is the one gap — and only that."""
    svc, cases = _mixed()
    through = svc.totals(cases)["through"]
    summed = {}
    for week in svc.weeks(cases)["weeks"]:
        for pic, by_date in svc.week(cases, week["start"])["cells"].items():
            summed[pic] = summed.get(pic, 0) + sum(
                c["actual"] or 0 for d, c in by_date.items() if d <= through)
    totals = {m["pic"]: m["actual"] for m in svc.totals(cases)["members"]}
    assert summed == {"An": 42, "Binh": 20, "N/A": 3}
    assert totals == {"An": 42, "Binh": 26, "N/A": 3}


def test_the_week_team_row_adds_up_each_day():
    svc, cases = _mixed()
    week = svc.week(cases, "2026-09-21")
    assert week["team"]["2026-09-22"] == {"planned": 50, "actual": 50, "delta": 0}


# --- productivity ---------------------------------------------------------------

def test_productivity_stops_at_yesterday_and_carries_attainment():
    svc = members({"2026-09-22": [entry(planned=20)]})
    cases = ran(10, "2026-09-22") + ran(6, "2026-09-25")
    row = svc.productivity(cases)["rows"][0]
    assert (row["executed"], row["days"], row["planned"]) == (10, 1, 20)
    assert row["attainment"] == 0.5


def test_productivity_rates_failures_among_executed_cases():
    svc = members()
    cases = ran(3, "2026-09-22") + ran(1, "2026-09-22", result="NG")
    assert svc.productivity(cases)["rows"][0]["ng_rate"] == 0.25


def test_an_unplanned_member_has_no_attainment_and_nothing_executed_no_ng_rate():
    svc = members()
    row = svc.productivity(ran(2, "2026-09-22", result="対象外"))["rows"][0]
    assert (row["attainment"], row["ng_rate"]) == (None, None)


def test_the_productivity_team_row_sums_members_and_rates_person_days():
    svc = members()
    cases = ran(4, "2026-09-22", pic="An") + ran(2, "2026-09-23", pic="Binh")
    team = svc.productivity(cases)["team"]
    assert (team["executed"], team["days"], team["productivity"]) == (6, 2, 3.0)


# --- weeks ------------------------------------------------------------------------

def test_a_week_is_monday_to_friday():
    svc = members(phase=("2026-09-21", "2026-09-25"))
    weeks = svc.weeks([])["weeks"]
    assert [w["start"] for w in weeks] == ["2026-09-21"]
    assert [d["date"] for d in weeks[0]["days"]] == [
        "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25"]


def test_days_outside_the_phase_are_marked_so():
    svc = members(phase=("2026-09-23", "2026-09-30"))
    days = svc.weeks([])["weeks"][0]["days"]
    assert [d["in_phase"] for d in days] == [False, False, True, True, True]


def test_a_week_with_work_before_the_phase_is_listed_and_an_empty_gap_is_not():
    svc = members(phase=("2026-09-21", "2026-09-25"))
    weeks = svc.weeks(ran(1, "2026-09-02"))["weeks"]
    assert [w["start"] for w in weeks] == ["2026-08-31", "2026-09-21"]


def test_the_current_week_is_the_one_holding_today_even_on_a_saturday():
    svc = members(phase=("2026-09-14", "2026-10-02"), today="2026-09-26")
    view = svc.weeks([])
    assert view["weeks"][view["current"]]["start"] == "2026-09-21"


def test_a_week_must_start_on_a_monday():
    with pytest.raises(ValueError, match="Monday"):
        members().week([], "2026-09-22")
