"""The plan on disk.

The store is deliberately thin: it reads and writes whole days, and every rule
about what a day may say lives in `tcm.domain.plan`. What is tested here is the
file behaviour — a missing file is an empty plan rather than an error, a write
replaces atomically, and a day emptied out stops taking up room.
"""
import json
import os

import pytest

from tcm.domain.plan import DayPlan, PlanEntry
from tcm.infrastructure.config_repo import JsonFileConfigRepository
from tcm.infrastructure.plan.json_store import JsonPlanRepository


@pytest.fixture
def store(tmp_path):
    return JsonPlanRepository(JsonFileConfigRepository(),
                              str(tmp_path / "plan.json"))


def day(date="2026-09-22", entries=(("An", "TC.xlsx", "iPhone", 30),)):
    return DayPlan(date=date, entries=[
        PlanEntry(pic=p, file=f, device=d, planned=n) for p, f, d, n in entries])


def test_a_missing_file_is_an_empty_plan_not_an_error(store):
    # Nobody has planned anything yet is the normal state on day one, and it
    # must reach the browser as an empty table rather than a 500.
    assert store.day("2026-09-22").entries == []
    assert store.days() == []


def test_a_day_that_was_never_planned_comes_back_empty(store):
    store.put_day(day("2026-09-22"))
    assert store.day("2026-09-23").entries == []


def test_a_saved_day_reads_back(store):
    store.put_day(day(entries=(("An", "TC.xlsx", "iPhone", 30),
                               ("Binh", "TC2.xlsx", "iPad", 12))))
    got = store.day("2026-09-22")
    assert [(e.pic, e.file, e.device, e.planned) for e in got.entries] == [
        ("An", "TC.xlsx", "iPhone", 30),
        ("Binh", "TC2.xlsx", "iPad", 12),
    ]


def test_a_baseline_survives_the_round_trip(store):
    d = day()
    d.baseline = [PlanEntry(pic="An", file="Other.xlsx", device="iPhone", planned=50)]
    d.baseline_at = "2026-09-22T08:41:12"
    store.put_day(d)
    got = store.day("2026-09-22")
    assert got.baseline_at == "2026-09-22T08:41:12"
    assert [e.file for e in got.baseline] == ["Other.xlsx"]


def test_saving_one_day_leaves_the_others_alone(store):
    store.put_day(day("2026-09-22"))
    store.put_day(day("2026-09-23", entries=(("Binh", "TC2.xlsx", "iPad", 5),)))
    assert store.day("2026-09-22").entries[0].pic == "An"
    assert store.day("2026-09-23").entries[0].pic == "Binh"


def test_saving_a_day_again_replaces_it(store):
    store.put_day(day())
    store.put_day(day(entries=(("Binh", "TC2.xlsx", "iPad", 5),)))
    assert len(store.day("2026-09-22").entries) == 1
    assert store.day("2026-09-22").entries[0].pic == "Binh"


def test_days_come_back_in_date_order(store):
    for date in ("2026-09-24", "2026-09-22", "2026-09-23"):
        store.put_day(day(date))
    assert [d.date for d in store.days()] == ["2026-09-22", "2026-09-23", "2026-09-24"]


def test_emptying_a_day_removes_it_from_the_file(store, tmp_path):
    # A day planned and then cleared is a day nobody planned. Keeping the key
    # would leave the file growing a record per date ever opened.
    store.put_day(day())
    store.put_day(DayPlan(date="2026-09-22"))
    raw = json.loads((tmp_path / "plan.json").read_text(encoding="utf-8"))
    assert raw["days"] == {}


def test_a_day_emptied_but_frozen_is_kept(store, tmp_path):
    # Deleting every row *is* the adjustment here: the baseline says work was
    # planned, and dropping the day would erase the evidence it was dropped.
    d = DayPlan(date="2026-09-22", baseline=[
        PlanEntry(pic="An", file="TC.xlsx", device="iPhone", planned=30)],
        baseline_at="2026-09-22T08:00:00")
    store.put_day(d)
    raw = json.loads((tmp_path / "plan.json").read_text(encoding="utf-8"))
    assert "2026-09-22" in raw["days"]


def test_the_file_carries_a_schema_version(store, tmp_path):
    store.put_day(day())
    raw = json.loads((tmp_path / "plan.json").read_text(encoding="utf-8"))
    assert raw["version"] == 1


def test_the_file_is_created_with_its_directory(tmp_path):
    # ~/.test-management may not exist: the token cache is the only other thing
    # that lives there, and a user who has never signed in has no such folder.
    path = str(tmp_path / "nested" / "deeper" / "plan.json")
    store = JsonPlanRepository(JsonFileConfigRepository(), path)
    store.put_day(day())
    assert os.path.isfile(path)


def test_a_corrupt_file_says_so_rather_than_reading_as_empty(store, tmp_path):
    # Reading a damaged plan as "no plan" would invite the next save to
    # overwrite it with one row, losing the rest for good.
    (tmp_path / "plan.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="plan.json"):
        store.day("2026-09-22")
