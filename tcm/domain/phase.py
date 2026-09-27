"""Phases and the people who test in them.

A phase is a named stretch of work -- "Sprint 12 regression" -- with its own
dates, its own fair day's load and its own day plans. Several may exist; one is
active, and every plan figure in the app is about that one.

A member is a name on the roster. The name is the join: it must match the PIC a
tester writes in the workbooks, which is why a member cannot be renamed -- the
rename would reach the roster and not the spreadsheets.
"""
from dataclasses import dataclass
from typing import Optional

from tcm.domain.plan import DEFAULT_TARGET, PlanSettings


class NotFound(LookupError):
    """An id nothing answers to. The web layer turns it into a 404."""


def member_name(value, source: str = "member") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source}: a member needs a name")
    return value.strip()


@dataclass(frozen=True)
class Member:
    id: int
    name: str

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name}


@dataclass(frozen=True)
class Phase:
    """One phase and who is in it.

    Attributes:
        id: The stored id, or None before it is stored.
        name: Unique among phases.
        phase_start / phase_end: "YYYY-MM-DD", or None for "not set" -- the
            planner fills in a default rather than storing one.
        daily_target: Cases per person per day; flags a heavy day, never plans one.
        members: Member names on this phase's roster.
        created_at: When it was stored.
    """

    id: Optional[int]
    name: str
    phase_start: Optional[str] = None
    phase_end: Optional[str] = None
    daily_target: int = DEFAULT_TARGET
    members: tuple = ()
    created_at: Optional[str] = None

    @property
    def settings(self) -> PlanSettings:
        """The phase as the planner reads it."""
        return PlanSettings(self.phase_start, self.phase_end, self.daily_target)

    @classmethod
    def from_dict(cls, raw, id: Optional[int] = None, source: str = "phase") -> "Phase":
        if not isinstance(raw, dict):
            raise ValueError(f"{source} must be an object")
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{source}: 'name' must be a non-empty string")
        # The date and target rules are PlanSettings' own, so they are written once.
        settings = PlanSettings.from_dict({
            "phase_start": raw.get("phase_start"),
            "phase_end": raw.get("phase_end"),
            "daily_target": raw.get("daily_target", DEFAULT_TARGET),
        }, source)
        members = raw.get("members", [])
        if not isinstance(members, list):
            raise ValueError(f"{source}: 'members' must be a list of names")
        names = []
        for i, m in enumerate(members):
            n = member_name(m, f"{source}.members[{i}]")
            if n in names:
                raise ValueError(f"{source}: {n} is listed twice")
            names.append(n)
        return cls(id=id, name=name.strip(), phase_start=settings.phase_start,
                   phase_end=settings.phase_end, daily_target=settings.daily_target,
                   members=tuple(names))

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "phase_start": self.phase_start,
                "phase_end": self.phase_end, "daily_target": self.daily_target,
                "members": list(self.members), "created_at": self.created_at}
