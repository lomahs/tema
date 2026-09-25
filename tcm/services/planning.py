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

**The planner counts "worked", not "executed".** `phase_view` and `board_view`
measure the plan against cases that have left the remaining pile
(`STATUS.worked`), because the burndown has to reconcile: what is remaining plus
what was worked is every counted case. `executed` is narrower -- a Cancel with a
PIC is off the pile without anyone passing or failing it -- and stays the
yardstick of `day_view` and `calendar_view`, which Daily and Productivity read.
Both are sums over the same `daily_rows` rows; neither counts cases itself.
"""
import math
from collections import defaultdict
from datetime import datetime, date as _date

from tcm.domain.plan import (DayPlan, PlanEntry, PlanSettings, add_workdays,
                             parse_date, phase_days)
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


def _worked(row: dict) -> int:
    """Cases of a `daily_rows` row that have left the remaining pile."""
    return sum(row.get(key, 0) for key in STATUS.worked)


#: What `daily_rows` calls a case with no PIC. It counts toward every total but
#: is nobody a plan can be written for, so it is never offered as a member.
_NO_PIC = "N/A"

#: How far past the phase end the burndown and the grid will reach, in working
#: days, when the plan or the forecast runs late. Past that the chart would be
#: all overrun and no phase.
_OVERRUN_DAYS = 20

#: Pace windows the forecast may be read over, as the design offers them.
WINDOWS = ("3", "5", "10", "all")


def _nice_max(v: float) -> int:
    """A round axis maximum a little above `v` (1, 1.5, 2, 2.5 ... x 10^n)."""
    p = 10 ** math.floor(math.log10(v))
    for m in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if m * p >= v * 1.04:
            return int(math.ceil(m * p))
    return int(10 * p)


class _Facts:
    """Everything the phase and the board read, indexed once per request.

    Built from `remaining_rows` and `daily_rows` only, so every figure the
    planner shows is one of theirs re-keyed, never a second count.
    """

    def __init__(self, cases, days, today):
        self.today = today
        self.rem = {}             # (file, device) -> remaining
        self.total = 0            # every counted case in the plan
        for r in remaining_rows(cases, keep_finished=True):
            self.rem[(r["file"], r["device"])] = r["remaining"]
            self.total += r["total"]
        # Load order: the files as `remaining_rows` names them, alphabetised,
        # so a slot list reads like the workbook folder.
        self._file_rank = {f: i for i, f in enumerate(sorted({f for f, _ in self.rem}))}

        self.by_slot_date = defaultdict(int)       # ((file, device), date) -> worked
        self.by_pic_slot_date = defaultdict(int)   # (pic, (file, device), date) -> worked
        self.by_date = defaultdict(int)            # date -> worked
        self.undated = 0
        for row in daily_rows(cases):
            n = _worked(row)
            if not n:
                continue
            slot, date = (row["file"], row["device"]), row["date"]
            if not date:
                self.undated += n
                continue
            self.by_slot_date[(slot, date)] += n
            self.by_pic_slot_date[(row["pic"], slot, date)] += n
            self.by_date[date] += n

        self.pics = {c.pic for c in cases if c.pic}
        self.plans = [(d.date, e) for d in days for e in d.entries]

    def remaining(self, slot) -> int:
        return self.rem.get(slot, 0)

    def remaining_at_start(self, slot) -> int:
        """What was left on this slot when today began: now + worked today."""
        return self.rem.get(slot, 0) + self.by_slot_date.get((slot, self.today), 0)

    def order(self, slots):
        """Load order; a slot whose file the load does not have goes last."""
        rank = self._file_rank
        return sorted(slots, key=lambda s: (s[0] not in rank, rank.get(s[0], 0), s[0], s[1]))


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

    # --- the day and the calendar -----------------------------------------

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

    # --- settings ---------------------------------------------------------

    def get_settings(self, cases) -> dict:
        """The stored settings, with a default filled in for what was never set.

        The defaults are computed, not stored, so opening the screen writes
        nothing: the phase starts on the first day anyone tested (today, if
        nobody has) and ends five working days out.
        """
        stored = self._repo.settings()
        today = self._today()
        dated = [c.test_date for c in cases if c.test_date]
        start = stored.phase_start or (min(dated) if dated else today)
        end = stored.phase_end or add_workdays(today, 5)
        if end < start:
            end = add_workdays(start, 5)
        return {"phase_start": start, "phase_end": end,
                "daily_target": stored.daily_target,
                "stored": stored != PlanSettings()}

    def save_settings(self, raw) -> PlanSettings:
        """Validate and store the settings. A refusal stores nothing."""
        settings = PlanSettings.from_dict(raw)
        self._repo.put_settings(settings)
        return settings

    # --- the phase ---------------------------------------------------------

    def phase_view(self, cases, window="5") -> dict:
        """The whole phase: KPIs, the burndown and the day-by-day grid."""
        if window not in WINDOWS:
            raise ValueError(f"window must be one of {', '.join(WINDOWS)}, got {window!r}")
        today = self._today()
        settings = self.get_settings(cases)
        start, end = settings["phase_start"], settings["phase_end"]
        facts = _Facts(cases, self._repo.days(), today)

        days = phase_days(start, end, today)
        left = len([d for d in days if d >= today])
        remaining = sum(facts.rem.values())
        before = facts.undated + sum(n for d, n in facts.by_date.items() if d < start)
        at_start = facts.total - before

        today_plans = [e for d, e in facts.plans if d == today]
        done_today = facts.by_date.get(today, 0)

        past = [d for d in days if d < today]
        win = past if window == "all" else past[-int(window):]
        rate = (sum(facts.by_date.get(d, 0) for d in win) / len(win)) if win else done_today
        rate = round(rate, 2)
        if remaining == 0:
            forecast = today
        elif rate > 0:
            forecast = add_workdays(today, math.ceil(remaining / rate))
        else:
            forecast = None

        plan_finish, covered = self._plan_finish(facts, remaining)
        last_plan = max((d for d, _ in facts.plans), default=None)
        cap = add_workdays(end, _OVERRUN_DAYS)

        return {
            "today": today,
            "settings": settings,
            "phase": {"days": days, "left": left},
            "kpis": {
                "remaining": remaining, "at_start": at_start,
                "planned_today": sum(e.planned for e in today_plans),
                "done_today": done_today,
                "members_today": len({e.pic for e in today_plans}),
                "needed_pace": math.ceil(remaining / left) if left else None,
                "plan_finish": plan_finish,
                "unplanned": max(0, remaining - covered),
                "forecast_finish": forecast, "rate": rate, "window_days": len(win),
            },
            "burndown": self._burndown(facts, start, end, cap, at_start, rate,
                                       [end, forecast, plan_finish, last_plan]),
            "grid": self._grid(facts, start, min(max(end, last_plan or end), cap)),
        }

    @staticmethod
    def _plan_finish(facts, remaining):
        """The day the plan covers every remaining case, and how many it covers.

        Today contributes what its plan still has to run -- planned less what
        that person already worked on that slot today -- and each later day its
        plan, every slot capped at what that slot has left: planning a finished
        slot twice covers nothing.
        """
        today = facts.today
        cap = dict(facts.rem)
        covered = 0

        def take(slot, n):
            nonlocal covered
            t = min(n, cap.get(slot, 0))
            cap[slot] = cap.get(slot, 0) - t
            covered += t

        for date, e in facts.plans:
            if date == today:
                slot = (e.file, e.device)
                done = facts.by_pic_slot_date.get((e.pic, slot, today), 0)
                take(slot, max(0, e.planned - done))
        if remaining == 0 or covered >= remaining:
            return today, covered
        for date, e in sorted(((d, e) for d, e in facts.plans if d > today),
                              key=lambda p: p[0]):
            take((e.file, e.device), e.planned)
            if covered >= remaining:
                return date, covered
        return None, covered

    @staticmethod
    def _burndown(facts, start, end, cap, at_start, rate, ends):
        """Remaining over the phase: as planned, as it went, and as forecast.

        Each series opens with `at_start` -- the point before the first day --
        so `plan` and `actual` are one longer than `axis`. `forecast` starts at
        today's actual and is placed from `forecast_from`, an index into the
        same point list.
        """
        today = facts.today
        axis_end = min(max(d for d in ends if d), cap)
        axis = phase_days(start, axis_end, today)
        planned = defaultdict(int)
        for d, e in facts.plans:
            planned[d] += e.planned

        plan, actual, forecast = [at_start], [at_start], []
        cp = ce = 0
        fv = None
        forecast_from = -1
        for i, d in enumerate(axis):
            cp += planned.get(d, 0)
            plan.append(max(0, at_start - cp))
            if d <= today:
                ce += facts.by_date.get(d, 0)
                actual.append(max(0, at_start - ce))
            if d == today:
                fv = max(0, at_start - ce)
                forecast.append(fv)
                forecast_from = i + 1
            elif d > today and fv is not None and fv > 0 and rate > 0:
                fv = max(0, fv - rate)
                forecast.append(round(fv, 2))
        return {
            "axis": axis, "plan": plan, "actual": actual,
            "forecast": forecast, "forecast_from": forecast_from,
            "today_index": axis.index(today) if today in axis else -1,
            "end_index": max((i for i, d in enumerate(axis) if d <= end), default=-1),
            "y_max": _nice_max(max(1, at_start)),
        }

    @staticmethod
    def _grid(facts, start, cols_end):
        """One row per slot, one column per phase day: planned ahead, worked behind.

        A future cell is flagged `over_remaining` once the slot's plan from
        today through that day exceeds what the slot had left when today began.
        """
        today = facts.today
        cols = phase_days(start, cols_end, today)
        col_set = set(cols)
        plan_sd = defaultdict(lambda: {"n": 0, "pics": []})
        for d, e in facts.plans:
            cell = plan_sd[((e.file, e.device), d)]
            cell["n"] += e.planned
            cell["pics"].append([e.pic, e.planned])

        slots = {s for s, n in facts.rem.items() if n > 0}
        slots |= {s for (s, d) in plan_sd if d in col_set}
        slots |= {s for (s, d) in facts.by_slot_date if d in col_set}

        rows = []
        for slot in facts.order(slots):
            rs, cum, cells = facts.remaining_at_start(slot), 0, {}
            for d in cols:
                p = plan_sd.get((slot, d))
                n = p["n"] if p else 0
                if d >= today:
                    cum += n
                cells[d] = {"planned": n,
                            "worked": facts.by_slot_date.get((slot, d), 0),
                            "over_remaining": d >= today and n > 0 and cum > rs,
                            "pics": p["pics"] if p else []}
            rows.append({"file": slot[0], "device": slot[1],
                         "remaining": facts.remaining(slot),
                         "remaining_at_start": rs, "cells": cells})

        planned_by_date = defaultdict(int)
        for (_, d), p in plan_sd.items():
            if d in col_set:
                planned_by_date[d] += p["n"]
        return {"days": cols, "slots": rows,
                "planned_by_date": dict(planned_by_date),
                "worked_by_date": {d: facts.by_date.get(d, 0) for d in cols}}

    # --- the day board -----------------------------------------------------

    def board_view(self, cases, date: str) -> dict:
        """One day, laid out as slots x members: planned against worked.

        Beside each slot: what it had left when today began, what the plan asks
        of it from today through this day, and by how much that overshoots --
        the figures the editor needs to say whether a day's plan fits.
        """
        date = parse_date(date)
        today = self._today()
        days = self._repo.days()
        facts = _Facts(cases, days, today)
        day = self._repo.day(date)

        planned = {(e.pic, (e.file, e.device)): e.planned for e in day.entries}
        worked = {(pic, slot): n for (pic, slot, d), n in facts.by_pic_slot_date.items()
                  if d == date}
        day_slots = {slot for _, slot in planned}
        slots = facts.order(day_slots | {slot for _, slot in worked})

        slot_rows = []
        for slot in slots:
            rs = facts.remaining_at_start(slot)
            ahead = [(d, e.planned) for d, e in facts.plans
                     if (e.file, e.device) == slot and d >= today]
            need = 0 if date < today else sum(n for d, n in ahead if d <= date)
            slot_rows.append({
                "file": slot[0], "device": slot[1],
                "remaining": facts.remaining(slot), "remaining_at_start": rs,
                "planned_other_days": sum(n for d, n in ahead if d != date),
                "need_through": need, "over_by": max(0, need - rs),
            })

        cells = [{"pic": pic, "file": slot[0], "device": slot[1],
                  "planned": n, "worked": worked.get((pic, slot), 0)}
                 for (pic, slot), n in planned.items()]
        cells += [{"pic": pic, "file": slot[0], "device": slot[1],
                   "planned": 0, "worked": n}
                  for (pic, slot), n in worked.items() if (pic, slot) not in planned]

        load = defaultdict(int)
        for e in day.entries:
            load[e.pic] += e.planned
        members = (facts.pics | {e.pic for _, e in facts.plans}) - {_NO_PIC}
        every_slot = set(facts.rem) | {slot for (slot, _) in facts.by_slot_date}
        available = [{"file": s[0], "device": s[1],
                      "remaining_at_start": facts.remaining_at_start(s)}
                     for s in facts.order(every_slot - day_slots)
                     if facts.remaining_at_start(s) > 0]

        return {
            "date": date, "today": today,
            "daily_target": self._repo.settings().daily_target,
            "entries": [e.to_dict() for e in day.entries],
            "slots": slot_rows, "cells": cells, "load": dict(load),
            "members": sorted(members), "available": available,
        }

    # --- one row shape, used by the day view -------------------------------

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
