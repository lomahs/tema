"""Phases and the member roster: the rules above the repository.

The repository enforces what the tables can (unique names, the last phase,
a member still planned); this adds what needs the loaded cases -- which PICs in
the data nobody has put on the roster yet.
"""
from dataclasses import replace

from tcm.domain.phase import Phase, member_name
from tcm.services.planning import _NO_PIC


class PhaseService:
    def __init__(self, repo):
        self._repo = repo

    def overview(self, cases) -> dict:
        """Everything the Phases & members card draws, in one answer."""
        return {
            "phases": [p.to_dict() for p in self._repo.phases()],
            "active_id": self._repo.active_id(),
            "members": [m.to_dict() for m in self._repo.members()],
            "suggestions": self.suggestions(cases),
        }

    def suggestions(self, cases) -> list:
        """PIC names in the data that are not on the roster, sorted."""
        roster = {m.name for m in self._repo.members()}
        found = {c.pic.strip() for c in cases if isinstance(c.pic, str) and c.pic.strip()}
        return sorted(found - roster - {_NO_PIC})

    def create(self, raw) -> Phase:
        phase = self._repo.create(Phase.from_dict(raw))
        if isinstance(raw, dict) and raw.get("activate"):
            self._repo.set_active(phase.id)
        return phase

    def update(self, phase_id: int, raw) -> Phase:
        self._repo.phase(phase_id)                  # NotFound before validating
        return self._repo.update(Phase.from_dict(raw, id=phase_id))

    def delete(self, phase_id: int) -> None:
        self._repo.delete(phase_id)

    def activate(self, phase_id: int) -> None:
        self._repo.set_active(phase_id)

    def add_member(self, name, phase_id=None):
        """Put someone on the roster and, given a phase, on that phase too."""
        member = self._repo.add_member(member_name(name))
        if phase_id is not None:
            phase = self._repo.phase(phase_id)
            if member.name not in phase.members:
                self._repo.update(replace(phase, members=phase.members + (member.name,)))
        return member

    def delete_member(self, member_id: int) -> None:
        self._repo.delete_member(member_id)
