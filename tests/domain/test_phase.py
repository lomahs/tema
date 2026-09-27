"""What a phase is allowed to say."""
import pytest

from tcm.domain.phase import Member, Phase, member_name
from tcm.domain.plan import DEFAULT_TARGET, PlanSettings


def test_a_minimal_phase_takes_the_defaults():
    p = Phase.from_dict({"name": " Sprint 12 "})
    assert p.name == "Sprint 12"
    assert (p.phase_start, p.phase_end, p.daily_target, p.members) == (None, None, DEFAULT_TARGET, ())
    assert p.settings == PlanSettings()


def test_a_full_phase_round_trips():
    raw = {"name": "Regression", "phase_start": "2026-09-01", "phase_end": "2026-09-30",
           "daily_target": 40, "members": ["An", "Bo"]}
    p = Phase.from_dict(raw, id=3)
    d = p.to_dict()
    assert d["id"] == 3 and d["members"] == ["An", "Bo"]
    assert p.settings == PlanSettings("2026-09-01", "2026-09-30", 40)


@pytest.mark.parametrize("raw, message", [
    ({}, "name"),
    ({"name": "  "}, "name"),
    ({"name": "P", "phase_start": "2026-09-30", "phase_end": "2026-09-01"}, "before it starts"),
    ({"name": "P", "daily_target": 0}, "daily_target"),
    ({"name": "P", "members": "An"}, "members"),
    ({"name": "P", "members": ["An", " An "]}, "twice"),
    ({"name": "P", "members": [""]}, "name"),
])
def test_bad_phases_are_refused_with_a_reason(raw, message):
    with pytest.raises(ValueError, match=message):
        Phase.from_dict(raw)


def test_member_names_are_stripped_and_required():
    assert member_name("  An ") == "An"
    with pytest.raises(ValueError):
        member_name(None)
    assert Member(1, "An").to_dict() == {"id": 1, "name": "An"}
