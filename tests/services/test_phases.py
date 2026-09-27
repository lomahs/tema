"""The phase service: the rules above the repository."""
import pytest

from tcm.domain.case import TestCase as Case
from tcm.infrastructure.db.bootstrap import open_database
from tcm.infrastructure.db.phases import SqlPhaseRepository
from tcm.services.phases import PhaseService


@pytest.fixture
def svc(tmp_path):
    return PhaseService(SqlPhaseRepository(open_database(str(tmp_path / "tcm.db"))))


def pic(name):
    return Case(file_name="A.xlsx", sheet="S", device="iPhone", row_num=1, pic=name)


def test_suggestions_are_pics_not_on_the_roster(svc):
    svc.add_member("An")
    cases = [pic("An"), pic(" Bo "), pic(""), pic(None), pic("N/A"), pic("Cy"), pic("Bo")]
    assert svc.suggestions(cases) == ["Bo", "Cy"]


def test_create_can_activate(svc):
    p = svc.create({"name": "Sprint 2", "activate": True})
    assert svc.overview([])["active_id"] == p.id
    q = svc.create({"name": "Sprint 3"})
    assert svc.overview([])["active_id"] == p.id != q.id


def test_add_member_can_join_a_phase(svc):
    active = svc.overview([])["active_id"]
    svc.add_member("An", phase_id=active)
    svc.add_member("An", phase_id=active)          # twice is still once
    [phase] = svc.overview([])["phases"]
    assert phase["members"] == ["An"]


def test_overview_shape(svc):
    o = svc.overview([pic("Zed")])
    assert set(o) == {"phases", "active_id", "members", "suggestions"}
    assert o["suggestions"] == ["Zed"] and o["members"] == []


def test_update_validates_before_writing(svc):
    pid = svc.overview([])["active_id"]
    with pytest.raises(ValueError):
        svc.update(pid, {"name": ""})
    assert svc.overview([])["phases"][0]["name"] == "Phase 1"
