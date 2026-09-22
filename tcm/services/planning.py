"""The test plan, and how it compares with what actually happened.

Three ideas hold this module together, and each is worth knowing before reading
a function.

**Actual is never computed here.** `daily_rows` in `tcm.services.aggregation`
already groups cases by (file, device, pic, date), which is exactly a plan row's
key with the date put back. So a planned row is *joined* to a daily row rather
than counted afresh, and the figure the planning screen shows cannot drift from
the one the Daily screen shows — they are the same function's output. Anything
new that counts cases belongs in `aggregation.py`, not here.

**The baseline is frozen lazily.** Editing the plan for a day that has not
arrived is planning; editing it on or after the day itself is adjusting. So the
first save made when `today >= date` keeps the pre-edit state as the baseline,
and a day nobody adjusted has none at all — which is correct rather than
missing: nothing diverged, so the plan as it stands is also what was planned.
No timer and no button are involved, because the app only runs when it is open.

**Work nobody planned is still shown.** Every view here adds the rows that
appear in the actuals but not in the plan. A table that listed only planned work
would hide work that was done, which is the one thing a report of a day must not
do.
"""
from collections import defaultdict
from datetime import datetime, date as _date

from tcm.domain.plan import DayPlan, PlanEntry, parse_date
from tcm.domain.status import STATUS
from tcm.services.aggregation import daily_rows, remaining_rows


def _today() -> str:
    return _date.today().isoformat()


def _executed(row: dict) -> int:
    """How many cases of a `daily_rows` row count as work carried out.

    `STATUS.executed`, not the row's `total`: a case left Pending was worked on
    and not finished, and the app's headline figure has been "Executed" rather
    than "Done" everywhere else for that reason.
    """
    return sum(row.get(key, 0) for key in STATUS.executed)


def _actuals(cases, date=None, pic=None) -> dict:
    """`daily_rows` re-keyed by (date, pic, file, device) -> executed count."""
    out = {}
    for row in daily_rows(cases):
        if date is not None and row["date"] != date:
            continue
        if pic is not None and row["pic"] != pic:
            continue
        key = (row["date"], row["pic"], row["file"], row["device"])
        out[key] = out.get(key, 0) + _executed(row)
    return out


class PlanningService:
    """Reads and writes the plan, and reports it against what happened."""

    def __init__(self, repository, today=_today):
        self._repo = repository
        #: Injected so the baseline rule can be tested without waiting a day.
        self._today = today

    @property
    def repository(self):
        """The store this service was built over."""
        return self._repo

    # --- reading and writing the plan --------------------------------------

    def get_day(self, date: str) -> DayPlan:
        return self._repo.day(parse_date(date))

    def save_day(self, date: str, raw_entries) -> DayPlan:
        """Replace one day's rows, freezing a baseline if this is an adjustment.

        The whole day is written at once, the way `PUT /api/config/<name>`
        writes a whole config: a plan is read and rearranged as a block, and
        per-row endpoints would buy nothing while a single file is rewritten
        on every save anyway.

        Nothing is stored unless every row validates — `DayPlan.from_dict`
        raises first, so a refused edit leaves the previous plan intact.
        """
        date = parse_date(date)
        previous = self._repo.day(date)
        day = DayPlan.from_dict(date, {"entries": list(raw_entries or [])})

        if previous.baseline is not None:
            # Already frozen: keep it. A baseline that followed each edit would
            # make every day look exactly on target.
            day.baseline = previous.baseline
            day.baseline_at = previous.baseline_at
        elif self._today() >= date:
            day.baseline = list(previous.entries)
            day.baseline_at = datetime.now().isoformat(timespec="seconds")

        self._repo.put_day(day)
        return day

    def rebaseline(self, date: str) -> DayPlan:
        """Make the plan as it stands the one the day is judged against.

        For the morning the first save was a typo, and for a day whose plan
        legitimately changed before it began.
        """
        day = self._repo.day(parse_date(date))
        day.baseline = list(day.entries)
        day.baseline_at = datetime.now().isoformat(timespec="seconds")
        self._repo.put_day(day)
        return day

    # --- the three cuts ----------------------------------------------------

    def day_view(self, date: str, cases) -> dict:
        """One date, every person: planned against actual, row by row."""
        date = parse_date(date)
        day = self._repo.day(date)
        actuals = _actuals(cases, date=date)
        baseline = {e.key: e.planned for e in (day.baseline or [])}

        rows = []
        seen = set()
        for e in day.entries:
            key = (date, e.pic, e.file, e.device)
            rows.append(self._row(e.pic, e.file, e.device, e.planned,
                                  actuals.get(key, 0), baseline.get(e.key)))
            seen.add(key)

        for (_, pic, file_name, device), actual in actuals.items():
            key = (date, pic, file_name, device)
            if key in seen or not actual:
                continue
            rows.append(self._row(pic, file_name, device, None, actual,
                                  baseline.get((pic, file_name, device))))

        rows.sort(key=lambda r: (r["pic"], r["file"], r["device"]))
        return {
            "date": date,
            "baseline_at": day.baseline_at,
            "has_baseline": day.baseline is not None,
            "rows": rows,
            "planned_total": day.planned_total,
            "actual_total": sum(r["actual"] for r in rows),
            "baseline_total": sum(baseline.values()) if day.baseline is not None else None,
        }

    def person_view(self, pic: str, cases) -> dict:
        """One person, every date they were planned for or worked on."""
        actuals = _actuals(cases, pic=pic)

        rows = []
        seen = set()
        for day in self._repo.days():
            for e in day.entries:
                if e.pic != pic:
                    continue
                key = (day.date, pic, e.file, e.device)
                rows.append({"date": day.date,
                             **self._row(pic, e.file, e.device, e.planned,
                                         actuals.get(key, 0), None)})
                seen.add(key)

        for (date, _, file_name, device), actual in actuals.items():
            if (date, pic, file_name, device) in seen or not actual:
                continue
            rows.append({"date": date,
                         **self._row(pic, file_name, device, None, actual, None)})

        rows.sort(key=lambda r: (r["date"], r["file"], r["device"]))
        return {
            "pic": pic,
            "rows": rows,
            "planned_total": sum(r["planned"] or 0 for r in rows),
            "actual_total": sum(r["actual"] for r in rows),
        }

    def calendar_view(self, start=None, end=None, cases=()) -> dict:
        """Every day in a range, as one line each: how much was planned and done.

        Dates worked but never planned are included, for the reason the other
        two views include unplanned rows — the point of the screen is what
        happened, and a calendar with a blank Thursday somebody tested on would
        be wrong rather than empty.
        """
        start = parse_date(start, "start") if start else None
        end = parse_date(end, "end") if end else None

        def within(date):
            return ((start is None or date >= start)
                    and (end is None or date <= end))

        planned = {}
        people = defaultdict(set)
        # Per person across the whole range, which is the figure Productivity
        # measures a member against. It rides here rather than behind its own
        # endpoint because Productivity reports over every day at once, and a
        # request per member would be one request per row of that table.
        by_pic = defaultdict(int)
        for day in self._repo.days():
            planned[day.date] = day.planned_total
            for e in day.entries:
                people[day.date].add(e.pic)
                if within(day.date):
                    by_pic[e.pic] += e.planned

        actual = defaultdict(int)
        for (date, pic, _, _), done in _actuals(cases).items():
            actual[date] += done
            if done:
                people[date].add(pic)

        dates = sorted(set(planned) | set(actual))
        days = [
            {"date": date,
             "planned": planned.get(date, 0),
             "actual": actual.get(date, 0),
             "people": len(people.get(date, ()))}
            for date in dates if within(date)
        ]
        return {
            "days": days,
            "by_pic": dict(by_pic),
            "planned_total": sum(d["planned"] for d in days),
            "actual_total": sum(d["actual"] for d in days),
        }

    # --- rearranging the day -----------------------------------------------

    def suggest(self, cases, date: str, device_family=None) -> list:
        """Where a freed-up tester could go: blocks with cases nobody has run.

        `remaining_rows` says what is left; this takes off what the day's plan
        has already handed out, so two people are not sent to the same block by
        a screen that could see both. What is given away is named rather than
        just subtracted — a figure that shrank with no explanation is one
        nobody trusts, and adding a second person to a block is a decision
        somebody may still want to make.

        Order is fewest-free first, so finishing a block outright is the easiest
        thing to reach for; a block already given away entirely keeps its place
        in the list but sinks below the ones with work left.
        """
        date = parse_date(date)
        day = self._repo.day(date)

        assigned = defaultdict(list)
        for e in day.entries:
            assigned[(e.file, e.device)].append({"pic": e.pic, "planned": e.planned})

        rows = []
        for row in remaining_rows(cases):
            if device_family and row["device_family"] != device_family:
                continue
            takers = assigned.get((row["file"], row["device"]), [])
            taken = sum(t["planned"] for t in takers)
            rows.append({**row,
                         "assigned": taken,
                         "free": max(0, row["remaining"] - taken),
                         "assigned_to": takers})

        rows.sort(key=lambda r: (r["free"] == 0, r["free"], r["file"], r["device"]))
        return rows

    # --- one row shape, used by all three cuts -----------------------------

    @staticmethod
    def _row(pic, file_name, device, planned, actual, baseline):
        return {
            "pic": pic,
            "file": file_name,
            "device": device,
            "planned": planned,
            "actual": actual,
            # None rather than a negative number when there was no plan: the
            # work was not behind, it was never scheduled.
            "diff": None if planned is None else actual - planned,
            "baseline": baseline,
        }
