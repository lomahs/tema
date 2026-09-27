"""The plan in the database, scoped to the active phase.

The day-level rules are the ones the JSON store had: nobody-planned is an empty
day, an emptied day stops taking up room, a frozen baseline is kept -- even an
empty one.
"""
import pytest

from tcm.domain.phase import Phase
from tcm.domain.plan import DayPlan, PlanEntry, PlanSettings
from tcm.domain.ports import PlanRepository
from tcm.infrastructure.db.bootstrap import open_database
from tcm.infrastructure.db.phases import SqlPhaseRepository
from tcm.infrastructure.db.plans import SqlPlanRepository


@pytest.fixture
def db(tmp_path):
    return open_database(str(tmp_path / "tcm.db"))


@pytest.fixture
def store(db):
    return SqlPlanRepository(db)


def day(date="2026-09-22", entries=(("An", "TC.xlsx", "iPhone", 30),), baseline=None, at=None):
    def mk(rows):
        return [PlanEntry(pic=p, file=f, device=d, planned=n) for p, f, d, n in rows]
    return DayPlan(date=date, entries=mk(entries),
                   baseline=None if baseline is None else mk(baseline), baseline_at=at)


def test_it_answers_the_port():
    assert issubclass(SqlPlanRepository, PlanRepository)


def test_a_day_nobody_planned_is_empty(store):
    assert store.day("2026-09-22").entries == []
    assert store.days() == []


def test_a_day_round_trips(store):
    store.put_day(day())
    assert store.day("2026-09-22") == day()
    assert store.days() == [day()]


def test_a_baseline_round_trips_including_an_empty_one(store):
    store.put_day(day(baseline=[("An", "TC.xlsx", "iPhone", 10)], at="2026-09-22T09:00:00"))
    assert store.day("2026-09-22").baseline == [PlanEntry("An", "TC.xlsx", "iPhone", 10)]
    store.put_day(day("2026-09-23", baseline=[], at="2026-09-23T09:00:00"))
    got = store.day("2026-09-23")
    assert got.baseline == [] and got.baseline_at == "2026-09-23T09:00:00"


def test_an_emptied_day_is_dropped_but_a_frozen_one_is_kept(store):
    store.put_day(day())
    store.put_day(day(entries=()))
    store.put_day(day("2026-09-23", entries=(), baseline=[("An", "TC.xlsx", "iPhone", 5)],
                      at="2026-09-23T09:00:00"))
    assert [d.date for d in store.days()] == ["2026-09-23"]


def test_days_come_back_in_date_order(store):
    store.put_day(day("2026-09-24"))
    store.put_day(day("2026-09-22"))
    assert [d.date for d in store.days()] == ["2026-09-22", "2026-09-24"]


def test_a_new_pic_joins_the_roster_and_the_phase(db, store):
    store.put_day(day(entries=(("Cy", "TC.xlsx", "iPhone", 3),)))
    assert store.members() == ["Cy"]
    assert [m.name for m in SqlPhaseRepository(db).members()] == ["Cy"]


def test_settings_are_the_active_phases(db, store):
    assert store.settings() == PlanSettings()
    store.put_settings(PlanSettings("2026-09-01", "2026-09-30", 40))
    phases = SqlPhaseRepository(db)
    assert phases.phase(phases.active_id()).settings == PlanSettings("2026-09-01", "2026-09-30", 40)


def test_each_phase_has_its_own_plan(db, store):
    phases = SqlPhaseRepository(db)
    first = phases.active_id()
    store.put_day(day())
    second = phases.create(Phase.from_dict({"name": "Sprint 2"}))
    phases.set_active(second.id)
    assert store.days() == []
    store.put_day(day(entries=(("Bo", "X.xlsx", "iPad", 2),)))
    phases.set_active(first)
    assert store.days() == [day()]
