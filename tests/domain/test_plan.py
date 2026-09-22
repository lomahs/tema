"""The plan vocabulary: what a planned day is allowed to say.

These are the invariants the endpoint's 400 carries the message of, the same
arrangement `ScopeSet` and `StatusSet` already use — validation is written once,
in the domain, so an edit made from the browser is checked by the same rules as
one made on disk.
"""
import pytest

from tcm.domain.plan import DayPlan, PlanEntry


def entry(pic="An", file="TC.xlsx", device="iPhone Min size", planned=30):
    return {"pic": pic, "file": file, "device": device, "planned": planned}


# --- PlanEntry -------------------------------------------------------------

def test_an_entry_round_trips_through_a_dict():
    e = PlanEntry.from_dict(entry(planned=42))
    assert e.pic == "An"
    assert e.file == "TC.xlsx"
    assert e.device == "iPhone Min size"
    assert e.planned == 42
    assert e.to_dict() == entry(planned=42)


@pytest.mark.parametrize("planned", [0, -1])
def test_a_plan_of_no_cases_is_refused(planned):
    # Nobody plans zero cases for a person on a file; a row saying so is a
    # half-finished edit, and it would divide into every attainment figure.
    with pytest.raises(ValueError, match="planned"):
        PlanEntry.from_dict(entry(planned=planned))


def test_a_fractional_plan_is_refused():
    with pytest.raises(ValueError, match="planned"):
        PlanEntry.from_dict(entry(planned=12.5))


@pytest.mark.parametrize("field", ["pic", "file", "device"])
def test_the_three_names_may_not_be_blank(field):
    with pytest.raises(ValueError, match=field):
        PlanEntry.from_dict(entry(**{field: "  "}))


def test_the_names_are_stripped():
    e = PlanEntry.from_dict(entry(pic=" An ", file=" TC.xlsx "))
    assert e.pic == "An"
    assert e.file == "TC.xlsx"


def test_an_entry_is_keyed_by_who_does_what_on_which_device():
    # The key is what `daily_rows` groups by minus the date, which is what lets
    # a plan row be joined to its actual without a second definition of either.
    assert PlanEntry.from_dict(entry()).key == ("An", "TC.xlsx", "iPhone Min size")


# --- DayPlan ---------------------------------------------------------------

def test_a_day_holds_its_entries_and_totals_them():
    day = DayPlan.from_dict("2026-09-22", {"entries": [entry(planned=10),
                                                       entry(pic="Binh", planned=25)]})
    assert day.date == "2026-09-22"
    assert len(day.entries) == 2
    assert day.planned_total == 35


def test_a_day_with_no_entries_is_allowed():
    # Clearing a day's plan is a thing someone does; it must not be an error.
    day = DayPlan.from_dict("2026-09-22", {"entries": []})
    assert day.entries == []
    assert day.planned_total == 0


@pytest.mark.parametrize("date", ["22-09-2026", "2026-9-22", "tomorrow", ""])
def test_a_date_that_is_not_an_iso_day_is_refused(date):
    # Every date in the app is "YYYY-MM-DD" — `TestCase.test_date` is normalised
    # to it, and the plan is joined to actuals on exactly that string.
    with pytest.raises(ValueError, match="date"):
        DayPlan.from_dict(date, {"entries": []})


def test_a_date_that_is_not_a_real_day_is_refused():
    with pytest.raises(ValueError, match="date"):
        DayPlan.from_dict("2026-02-30", {"entries": []})


def test_two_entries_for_the_same_person_file_and_device_are_refused():
    # Two such rows are one row with the counts added. Left as two, the actual
    # for that (pic, file, device) joins onto both and is counted twice.
    with pytest.raises(ValueError, match="duplicate"):
        DayPlan.from_dict("2026-09-22", {"entries": [entry(), entry(planned=5)]})


def test_the_same_person_may_plan_two_devices_of_one_file():
    day = DayPlan.from_dict("2026-09-22", {"entries": [
        entry(device="iPhone Min size"),
        entry(device="iPad"),
    ]})
    assert len(day.entries) == 2


def test_a_day_round_trips_with_its_baseline():
    raw = {
        "entries": [entry(planned=10)],
        "baseline": [entry(planned=30)],
        "baseline_at": "2026-09-22T08:41:12",
    }
    day = DayPlan.from_dict("2026-09-22", raw)
    assert day.baseline_at == "2026-09-22T08:41:12"
    assert [e.planned for e in day.baseline] == [30]
    assert day.to_dict() == raw


def test_a_day_never_frozen_has_no_baseline():
    day = DayPlan.from_dict("2026-09-22", {"entries": [entry()]})
    assert day.baseline is None
    assert "baseline" not in day.to_dict()


def test_an_empty_day_is_what_a_date_nobody_planned_looks_like():
    # The repository answers with this rather than None, so every caller gets a
    # DayPlan and none of them has to ask whether the file had heard of the day.
    day = DayPlan.empty("2026-09-22")
    assert day.date == "2026-09-22"
    assert day.entries == []
    assert day.baseline is None
