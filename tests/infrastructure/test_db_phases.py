"""Phases and the roster in the database."""
import pytest

from tcm.domain.phase import NotFound, Phase
from tcm.domain.plan import DayPlan, PlanEntry
from tcm.domain.ports import PhaseRepository
from tcm.infrastructure.db.bootstrap import open_database
from tcm.infrastructure.db.phases import SqlPhaseRepository
from tcm.infrastructure.db.plans import SqlPlanRepository


@pytest.fixture
def db(tmp_path):
    return open_database(str(tmp_path / "tcm.db"))


@pytest.fixture
def repo(db):
    return SqlPhaseRepository(db)


def test_it_answers_the_port():
    assert issubclass(SqlPhaseRepository, PhaseRepository)


def test_a_new_database_has_phase_1_active(repo):
    [p] = repo.phases()
    assert p.name == "Phase 1" and repo.active_id() == p.id


def test_create_stores_the_phase_and_its_members(repo):
    p = repo.create(Phase.from_dict({"name": "Sprint 12", "phase_start": "2026-09-01",
                                     "members": ["Bo", "An"]}))
    assert p.id and p.created_at
    assert repo.phase(p.id).members == ("An", "Bo")
    assert [m.name for m in repo.members()] == ["An", "Bo"]


def test_a_duplicate_name_is_refused(repo):
    with pytest.raises(ValueError, match="already exists"):
        repo.create(Phase.from_dict({"name": "Phase 1"}))


def test_update_replaces_fields_and_members(repo):
    p = repo.create(Phase.from_dict({"name": "S", "members": ["An"]}))
    repo.update(Phase.from_dict({"name": "S2", "daily_target": 12, "members": ["Bo"]}, id=p.id))
    q = repo.phase(p.id)
    assert (q.name, q.daily_target, q.members) == ("S2", 12, ("Bo",))
    # An stays on the roster: leaving a phase is not leaving the team.
    assert [m.name for m in repo.members()] == ["An", "Bo"]


def test_unknown_ids_are_not_found(repo):
    with pytest.raises(NotFound):
        repo.phase(999)
    with pytest.raises(NotFound):
        repo.update(Phase.from_dict({"name": "X"}, id=999))
    with pytest.raises(NotFound):
        repo.set_active(999)
    with pytest.raises(NotFound):
        repo.delete(999)
    with pytest.raises(NotFound):
        repo.delete_member(999)


def test_the_last_phase_cannot_be_deleted(repo):
    with pytest.raises(ValueError, match="last phase"):
        repo.delete(repo.active_id())


def test_deleting_the_active_phase_moves_active_and_drops_its_plans(db, repo):
    first = repo.active_id()
    second = repo.create(Phase.from_dict({"name": "Sprint 2"}))
    repo.set_active(second.id)
    SqlPlanRepository(db).put_day(DayPlan("2026-09-22", [PlanEntry("An", "A.xlsx", "iPhone", 5)]))
    repo.delete(second.id)
    assert repo.active_id() == first
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM plan_day").fetchone()[0] == 0
    assert SqlPlanRepository(db).days() == []


def test_add_member_is_idempotent(repo):
    a = repo.add_member(" An ")
    assert repo.add_member("An") == a
    assert [m.name for m in repo.members()] == ["An"]


def test_a_member_still_planned_cannot_be_deleted(db, repo):
    SqlPlanRepository(db).put_day(DayPlan("2026-09-22", [PlanEntry("An", "A.xlsx", "iPhone", 5)]))
    [an] = repo.members()
    with pytest.raises(ValueError, match="still planned on 1 day"):
        repo.delete_member(an.id)


def test_deleting_a_member_takes_them_off_every_phase(repo):
    p = repo.create(Phase.from_dict({"name": "S", "members": ["An"]}))
    [an] = repo.members()
    repo.delete_member(an.id)
    assert repo.phase(p.id).members == ()
    assert repo.members() == []
