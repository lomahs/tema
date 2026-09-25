"""The test plan as one JSON file.

The whole document is rewritten on every save, which is the right trade at this
size: a team's plan is a few hundred rows a sprint, and a file you can open and
read is worth more here than partial writes. `PlanRepository` is where that
stops being a commitment — the day a plan outgrows a file, a `SqlPlanRepository`
answers the same three methods and only `create_app` changes.

The write goes through a `ConfigRepository` rather than through `open`, so the
plan gets the same atomic temp-file-and-replace the editable configs get. A
half-written plan is worse than a config: a config can be fixed from the shipped
copy, and a plan is the only copy there is.

Shape on disk::

    {"version": 1,
     "days": {"2026-09-22": {"entries": [...], "baseline": [...], "baseline_at": ...}},
     "settings": {"phase_start": ..., "phase_end": ..., "daily_target": 30}}

`version` is there so a later schema change can still read today's files.
`settings` is additive -- a file written before it existed reads as the
defaults -- which is why adding it did not bump the version.
"""
import json
import os

from tcm.domain.plan import DayPlan, PlanSettings, parse_date

#: Bumped when the shape above changes in a way a reader has to know about.
SCHEMA_VERSION = 1


class JsonPlanRepository:
    """The plan, kept in one JSON file on the local filesystem."""

    def __init__(self, config_repo, path: str):
        self._repo = config_repo
        self._path = path

    # --- reading -----------------------------------------------------------

    def day(self, date: str) -> DayPlan:
        """One date's plan; an empty one for a date nobody planned."""
        date = parse_date(date)
        raw = self._read()["days"].get(date)
        if raw is None:
            return DayPlan.empty(date)
        return DayPlan.from_dict(date, raw, source=f"{os.path.basename(self._path)}[{date}]")

    def days(self) -> list[DayPlan]:
        """Every planned day, in date order."""
        days = self._read()["days"]
        return [DayPlan.from_dict(date, days[date],
                                  source=f"{os.path.basename(self._path)}[{date}]")
                for date in sorted(days)]

    # --- writing -----------------------------------------------------------

    def put_day(self, day: DayPlan) -> None:
        """Save one day, leaving the rest of the file alone.

        A day with no rows and no baseline is dropped rather than stored: it is
        a day nobody planned, and keeping the key would grow the file by a
        record for every date ever opened. A day emptied *after* being frozen is
        kept — the baseline is the evidence that work was planned and dropped.
        """
        doc = self._read()
        if not day.entries and day.baseline is None:
            doc["days"].pop(day.date, None)
        else:
            doc["days"][day.date] = day.to_dict()
        self._write(doc)

    # --- settings ----------------------------------------------------------

    def settings(self) -> PlanSettings:
        """The phase and the daily target; the defaults when none were saved."""
        return PlanSettings.from_dict(
            self._read()["settings"] or {},
            source=f"{os.path.basename(self._path)}[settings]")

    def put_settings(self, settings: PlanSettings) -> None:
        """Save the settings, leaving every day alone."""
        doc = self._read()
        doc["settings"] = settings.to_dict()
        self._write(doc)

    # --- the file ----------------------------------------------------------

    def _read(self) -> dict:
        """The whole document as `{"days": {...}, "settings": {...} | None}`.

        Both halves always come back, so a save of one cannot drop the other.
        """
        try:
            text = self._repo.read_text(self._path)
        except FileNotFoundError:
            # No plan yet is the normal state, not a failure.
            return {"days": {}, "settings": None}
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as e:
            # Not swallowed: reading a damaged plan as "no plan" would invite
            # the next save to overwrite it and lose the rest for good.
            raise ValueError(f"{self._path} is not valid JSON: {e}") from e
        if not isinstance(raw, dict) or not isinstance(raw.get("days", {}), dict):
            raise ValueError(f"{self._path} is not a plan file")
        settings = raw.get("settings")
        if settings is not None and not isinstance(settings, dict):
            raise ValueError(f"{self._path}: 'settings' must be an object")
        return {"days": raw.get("days", {}), "settings": settings}

    def _write(self, doc: dict) -> None:
        # ~/.test-management holds only the Graph token cache otherwise, so a
        # user who has never signed in has no such folder.
        os.makedirs(os.path.dirname(os.path.abspath(self._path)), exist_ok=True)
        out = {"version": SCHEMA_VERSION, "days": doc["days"]}
        if doc.get("settings"):
            out["settings"] = doc["settings"]
        text = json.dumps(out, indent=2, ensure_ascii=False) + "\n"
        self._repo.write_text(self._path, text)
