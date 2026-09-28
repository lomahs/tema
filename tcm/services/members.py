"""The Member tab: each person against the plan, day by day and in total.

Two questions are answered here, and they are measured in different cases on
purpose. **Productivity** is throughput, so it counts `executed`. **Against the
plan** counts `worked` — executed plus the statuses that left the pile without
being run (Cancel with a PIC) — because a plan of 100 that ended 90 OK and 10
Cancel is on plan. The two meet in one identity, which the tests pin: a
member's executed plus their Cancel is their Actual.

**Totals stop at yesterday.** Today is half a day: counted in, it would read
every member as behind by today's plan each morning and drag every rate down.
There is no lower bound — work dated before the phase began is still work, and
still counts toward Actual (the user's call; it leans the delta towards
"ahead", since nobody planned those days).

**Adherence is cumulative per slot, and capped.** For each (file, device) a
member was planned on: the lesser of what they worked there and what they were
planned there, both through yesterday, over their whole plan. Catching up the
next day, or running a slot ahead of its day, is credited; beating the plan is
not — the excess is in the delta, which is the other half of the answer.

Everything is re-keyed from `daily_rows`, never counted afresh, and `_totals`
is the one place the per-member figures are computed: `productivity` and
`totals` both read it, so the two endpoints cannot disagree.

Weeks run Monday to Friday. A weekend has no column (not wanted for now), but
work done on one is still work and still reaches the totals — so a row's cells
fall short of its total by exactly that.
"""
from collections import defaultdict
from datetime import date as _date, timedelta

from tcm.domain.plan import parse_date
from tcm.domain.status import STATUS
from tcm.services.aggregation import daily_rows, productivity_rows

#: What `daily_rows` calls a case with no PIC: a row of its own, never planned.
_NO_PIC = "N/A"


def _shift(iso: str, days: int) -> str:
    return (_date.fromisoformat(iso) + timedelta(days=days)).isoformat()


def _monday(iso: str) -> str:
    return _shift(iso, -_date.fromisoformat(iso).weekday())


def _weekday(iso: str) -> bool:
    return _date.fromisoformat(iso).weekday() < 5


def _ratio(n, d):
    return n / d if d else None


class _Facts:
    """The load and the plan, indexed once per request."""

    def __init__(self, planning, cases):
        self.today = planning.today()
        self.through = _shift(self.today, -1)
        self.worked = defaultdict(int)       # (pic, date) -> worked
        self.executed = defaultdict(int)     # (pic, date) -> executed
        self.worked_slot = defaultdict(int)  # (pic, (file, device), date) -> worked
        for row in daily_rows(cases):
            if not row["worked"]:
                continue
            pic, date = row["pic"], row["date"]
            self.worked[(pic, date)] += row["worked"]
            self.executed[(pic, date)] += row["executed"]
            self.worked_slot[(pic, (row["file"], row["device"]), date)] += row["worked"]

        self.planned = defaultdict(int)      # (pic, date) -> planned
        self.plan_slot = defaultdict(int)    # (pic, (file, device), date) -> planned
        for day in planning.repository.days():
            for e in day.entries:
                self.planned[(e.pic, day.date)] += e.planned
                self.plan_slot[(e.pic, (e.file, e.device), day.date)] += e.planned

        pics = ({p for p, _ in self.worked} | {p for p, _ in self.planned}
                | set(planning.repository.members()))
        named = sorted(pics - {_NO_PIC})
        self.pics = named + ([_NO_PIC] if _NO_PIC in pics else [])

    def past(self, date: str) -> bool:
        return date <= self.through


def _totals(facts) -> dict:
    """Plan against actual through yesterday, per member and for the team."""
    zero = {"planned": 0, "actual": 0, "executed": 0, "unplanned": 0, "kept": 0}
    per = {pic: dict(zero) for pic in facts.pics}

    for (pic, date), n in facts.planned.items():
        if facts.past(date):
            per[pic]["planned"] += n
    for (pic, date), n in facts.worked.items():
        if facts.past(date):
            per[pic]["actual"] += n
            per[pic]["executed"] += facts.executed[(pic, date)]
            if (pic, date) not in facts.planned:
                per[pic]["unplanned"] += n

    plan_by_slot, work_by_slot = defaultdict(int), defaultdict(int)
    for (pic, slot, date), n in facts.plan_slot.items():
        if facts.past(date):
            plan_by_slot[(pic, slot)] += n
    for (pic, slot, date), n in facts.worked_slot.items():
        if facts.past(date):
            work_by_slot[(pic, slot)] += n
    for (pic, slot), n in plan_by_slot.items():
        per[pic]["kept"] += min(n, work_by_slot.get((pic, slot), 0))

    def figures(t):
        planned = t["planned"]
        return {
            "planned": planned, "actual": t["actual"],
            "executed": t["executed"], "cancel": t["actual"] - t["executed"],
            "unplanned": t["unplanned"],
            # No plan is not a plan of zero: nothing to be ahead of or behind.
            "delta": t["actual"] - planned if planned else None,
            "adherence": _ratio(t["kept"], planned),
            "attainment": _ratio(t["actual"], planned),
        }

    team = {k: sum(t[k] for t in per.values()) for k in zero}
    return {
        "members": [{"pic": pic, "aside": pic == _NO_PIC, **figures(per[pic])}
                    for pic in facts.pics],
        "team": figures(team),
    }


class MemberService:
    """Reports each person against the plan the `PlanningService` holds."""

    def __init__(self, planning):
        self._planning = planning

    def _facts(self, cases):
        return _Facts(self._planning, cases)

    @staticmethod
    def _stamp(facts) -> dict:
        # Every response names the day it counts through, so four separate
        # requests can be seen to agree.
        return {"today": facts.today, "through": facts.through}

    # --- /api/member/totals ------------------------------------------------

    def totals(self, cases) -> dict:
        facts = self._facts(cases)
        return {**self._stamp(facts), **_totals(facts)}

    # --- /api/member/productivity ------------------------------------------

    def productivity(self, cases) -> dict:
        """`productivity_rows` through yesterday, with the plan figures beside."""
        facts = self._facts(cases)
        totals = _totals(facts)
        by_pic = {m["pic"]: m for m in totals["members"]}
        failed = [k for k in STATUS.executed if k in set(STATUS.issue)]

        def rate(r):
            if not failed or not r["executed"]:
                return None
            return _ratio(sum(r.get(k, 0) for k in failed), r["executed"])

        rows = productivity_rows(cases, until=facts.through)
        for r in rows:
            plan = by_pic.get(r["pic"], {})
            r["ng_rate"] = rate(r)
            r["planned"] = plan.get("planned", 0)
            r["attainment"] = plan.get("attainment")

        summed = list(STATUS.worked) + ["executed", "worked", "days"]
        team = {k: sum(r.get(k, 0) for r in rows) for k in summed}
        # `days` sums to person-days, which is the denominator a team rate wants.
        team["productivity"] = round(team["executed"] / team["days"], 2) if team["days"] else 0
        team["ng_rate"] = rate(team)
        team["planned"] = totals["team"]["planned"]
        team["attainment"] = totals["team"]["attainment"]
        return {**self._stamp(facts), "rows": rows, "team": team}

    # --- /api/member/weeks -------------------------------------------------

    def weeks(self, cases) -> dict:
        """Every Monday-to-Friday week the phase touches or any work or plan falls in."""
        facts = self._facts(cases)
        settings = self._planning.get_settings(cases)
        start, end = settings["phase_start"], settings["phase_end"]

        mondays = set()
        d = start
        while d <= end:
            if _weekday(d):
                mondays.add(_monday(d))
            d = _shift(d, 1)
        for _, date in list(facts.worked) + list(facts.planned):
            if _weekday(date):
                mondays.add(_monday(date))

        weeks = [{"start": m, "end": _shift(m, 4),
                  "days": [{"date": _shift(m, i), "in_phase": start <= _shift(m, i) <= end}
                           for i in range(5)]}
                 for m in sorted(mondays)]
        this_week = _monday(facts.today)
        before = [i for i, w in enumerate(weeks) if w["start"] <= this_week]
        return {**self._stamp(facts), "weeks": weeks,
                "current": before[-1] if before else 0}

    # --- /api/member/week/<monday> -----------------------------------------

    def week(self, cases, monday: str) -> dict:
        """One week's cells, member by day, and the team's figure for each day."""
        monday = parse_date(monday, "week")
        if _date.fromisoformat(monday).weekday() != 0:
            raise ValueError(f"week must start on a Monday, got {monday!r}")
        facts = self._facts(cases)
        days = [_shift(monday, i) for i in range(5)]

        cells = {}
        for pic in facts.pics:
            by_date = {}
            for date in days:
                c = self._cell(facts, pic, date)
                if c:
                    by_date[date] = c
            if by_date:
                cells[pic] = by_date

        team = {}
        for date in days:
            planned = sum(n for (p, d), n in facts.planned.items() if d == date)
            actual = sum(n for (p, d), n in facts.worked.items() if d == date)
            has_plan = any(d == date for _, d in facts.planned)
            if not planned and not actual:
                continue
            team[date] = {"planned": planned if has_plan else None, "actual": actual,
                          "delta": actual - planned
                          if has_plan and facts.past(date) else None}
        return {**self._stamp(facts), "start": monday, "days": days,
                "cells": cells, "team": team}

    @staticmethod
    def _cell(facts, pic, date):
        has_plan = (pic, date) in facts.planned
        planned = facts.planned[(pic, date)] if has_plan else None
        worked = facts.worked.get((pic, date), 0)
        if not has_plan and not worked:
            return None
        executed = facts.executed.get((pic, date), 0)
        state = ("past" if date < facts.today
                 else "today" if date == facts.today else "future")

        short = []
        if state == "past" and has_plan:
            for (p, slot, d), n in facts.plan_slot.items():
                if p == pic and d == date:
                    done = facts.worked_slot.get((pic, slot, date), 0)
                    if done < n:
                        short.append({"file": slot[0], "device": slot[1],
                                      "planned": n, "actual": done})
            short.sort(key=lambda s: (s["file"], s["device"]))

        return {
            "state": state, "planned": planned,
            "actual": worked if state != "future" or worked else None,
            "executed": executed, "cancel": worked - executed,
            "delta": worked - planned if state == "past" and has_plan else None,
            "short": short,
        }
