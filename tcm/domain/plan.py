"""What a day's test plan is allowed to say.

A plan row names who tests which file on which device, and how many cases that
is meant to be. That is deliberately the same tuple `daily_rows` groups by, one
level short of the date — which is what lets a planned row be joined to what
actually happened without a second definition of either side.

Unlike `STATUS`, `SCOPES`, `DEVICES` and `LABELS`, this module holds **no
singleton and reads no file at import**. Those four are vocabularies: the app
cannot classify a case without them, so a malformed one is worth refusing to
boot over. A plan is operational data — most days there is none, and "nobody has
planned tomorrow yet" must be an empty table rather than an ImportError.

Validation lives here for the reason it lives in `scope.py`: the endpoint builds
a `DayPlan` from the request body and hands the browser whatever message this
raises, so the rules are written once and an edit made through the UI is checked
by the same code as one made on disk.
"""
from dataclasses import dataclass, field
from datetime import date as _date
from typing import Optional


def parse_date(value, source: str = "date") -> str:
    """Check `value` is an ISO calendar day and give it back unchanged.

    Every date in the app is "YYYY-MM-DD": that is what the Excel reader
    normalises `test_date` to, and a plan is joined to its actuals on exactly
    that string. A date in any other shape would simply never match, which is a
    worse failure than a refusal — the table would be right and empty.
    """
    if not isinstance(value, str):
        raise ValueError(f"{source} must be a string, got {type(value).__name__}")
    try:
        parsed = _date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{source} must be a calendar day as YYYY-MM-DD, got '{value}'")
    # fromisoformat accepts "2026-9-2" on some versions; insist on the padded
    # form, because that is the one test_date is normalised to.
    if parsed.isoformat() != value:
        raise ValueError(f"{source} must be a calendar day as YYYY-MM-DD, got '{value}'")
    return value


def _name(raw: dict, field_name: str, source: str) -> str:
    value = raw.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source}: '{field_name}' must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class PlanEntry:
    """One person's planned work on one device of one file.

    Attributes:
        pic: Who is to run it, matching `TestCase.pic`.
        file: Workbook basename, matching `TestCase.file_name`.
        device: Device name as the workbook's TOOL_DATA writes it — the raw
            name, not the family, because that is what a tester is handed and
            what `daily_rows` reports. The family is derived where it is needed.
        planned: How many cases. Always at least one.
    """

    pic: str
    file: str
    device: str
    planned: int

    @property
    def key(self) -> tuple:
        """What identifies this row within its day, and what actuals join on."""
        return (self.pic, self.file, self.device)

    @classmethod
    def from_dict(cls, raw: dict, source: str = "entry") -> "PlanEntry":
        if not isinstance(raw, dict):
            raise ValueError(f"{source} must be an object")
        planned = raw.get("planned")
        # bool is an int in Python and `True` is not a case count.
        if isinstance(planned, bool) or not isinstance(planned, int) or planned <= 0:
            raise ValueError(f"{source}: 'planned' must be a whole number of cases "
                             f"above zero, got {planned!r}")
        return cls(
            pic=_name(raw, "pic", source),
            file=_name(raw, "file", source),
            device=_name(raw, "device", source),
            planned=planned,
        )

    def to_dict(self) -> dict:
        return {"pic": self.pic, "file": self.file,
                "device": self.device, "planned": self.planned}


def _entries(raw_list, source: str) -> list[PlanEntry]:
    if raw_list is None:
        return []
    if not isinstance(raw_list, list):
        raise ValueError(f"{source} must be a list")
    entries = []
    seen = set()
    for i, raw in enumerate(raw_list):
        e = PlanEntry.from_dict(raw, source=f"{source}[{i}]")
        if e.key in seen:
            raise ValueError(
                f"{source}: duplicate row for {e.pic} / {e.file} / {e.device} — "
                "two such rows are one row with the counts added, and left as "
                "two the actual for that work is counted twice")
        seen.add(e.key)
        entries.append(e)
    return entries


@dataclass
class DayPlan:
    """One date's plan, and what it looked like coming into that date.

    `baseline` is frozen lazily, by `tcm.services.planning`: editing a future
    day is planning, and carries no baseline; the first edit made *on or after*
    the day itself is an adjustment, and that is when the pre-edit state is
    kept. A day nobody adjusted therefore has no baseline at all, which is
    correct — nothing diverged, so `current` is also what was planned.

    Attributes:
        date: The day, as "YYYY-MM-DD".
        entries: The plan as it stands now.
        baseline: The plan as it stood when the day began, or None.
        baseline_at: When `baseline` was frozen, as an ISO timestamp, or None.
    """

    date: str
    entries: list[PlanEntry] = field(default_factory=list)
    baseline: Optional[list[PlanEntry]] = None
    baseline_at: Optional[str] = None

    @property
    def planned_total(self) -> int:
        return sum(e.planned for e in self.entries)

    @classmethod
    def empty(cls, date: str) -> "DayPlan":
        """A date nobody has planned.

        The repository answers with this rather than None, so every caller is
        handed a `DayPlan` and none of them has to ask whether the file had
        heard of the day.
        """
        return cls(date=parse_date(date))

    @classmethod
    def from_dict(cls, date: str, raw: dict, source: str = "plan") -> "DayPlan":
        if not isinstance(raw, dict):
            raise ValueError(f"{source} must be an object")
        baseline = raw.get("baseline")
        return cls(
            date=parse_date(date),
            entries=_entries(raw.get("entries"), f"{source}.entries"),
            baseline=None if baseline is None else _entries(baseline, f"{source}.baseline"),
            baseline_at=raw.get("baseline_at"),
        )

    def to_dict(self) -> dict:
        """Plain dict for JSON. The date is the key it is stored under, not a field."""
        out = {"entries": [e.to_dict() for e in self.entries]}
        if self.baseline is not None:
            out["baseline"] = [e.to_dict() for e in self.baseline]
            out["baseline_at"] = self.baseline_at
        return out
