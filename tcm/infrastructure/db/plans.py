"""The plan for the active phase.

`PlanRepository` was written with this class in mind: a day is a row, so
fetching one is a `WHERE date = ?`, not a load of the whole plan. Which phase is
asked every call rather than fixed at construction, so switching phase changes
what every plan figure reads without rebuilding anything.
"""
from collections import defaultdict

from tcm.domain.plan import DayPlan, PlanEntry, PlanSettings, parse_date
from tcm.infrastructure.db.database import now_iso
from tcm.infrastructure.db.phases import active_phase_id, member_id

_ENTRIES = ("SELECT pe.plan_day_id, pe.is_baseline, m.name AS pic, pe.file, pe.device, "
            "pe.planned FROM plan_entry pe JOIN member m ON m.id = pe.member_id ")


def _build(row, entry_rows) -> DayPlan:
    current = [PlanEntry(r["pic"], r["file"], r["device"], r["planned"])
               for r in entry_rows if not r["is_baseline"]]
    base = [PlanEntry(r["pic"], r["file"], r["device"], r["planned"])
            for r in entry_rows if r["is_baseline"]]
    frozen = row["baseline_at"] is not None
    return DayPlan(date=row["date"], entries=current,
                   baseline=base if frozen else None,
                   baseline_at=row["baseline_at"])


class SqlPlanRepository:
    """The active phase's plan in the SQLite database."""

    def __init__(self, db):
        self._db = db

    def day(self, date: str) -> DayPlan:
        date = parse_date(date)
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT id, date, baseline_at FROM plan_day WHERE phase_id = ? AND date = ?",
                (active_phase_id(conn), date)).fetchone()
            if row is None:
                return DayPlan.empty(date)
            entries = conn.execute(_ENTRIES + "WHERE pe.plan_day_id = ? ORDER BY pe.id",
                                   (row["id"],)).fetchall()
        return _build(row, entries)

    def days(self) -> list:
        with self._db.connect() as conn:
            pid = active_phase_id(conn)
            rows = conn.execute(
                "SELECT id, date, baseline_at FROM plan_day WHERE phase_id = ? ORDER BY date",
                (pid,)).fetchall()
            entries = conn.execute(
                _ENTRIES + "JOIN plan_day pd ON pd.id = pe.plan_day_id "
                "WHERE pd.phase_id = ? ORDER BY pe.id", (pid,)).fetchall()
        by_day = defaultdict(list)
        for e in entries:
            by_day[e["plan_day_id"]].append(e)
        return [_build(r, by_day[r["id"]]) for r in rows]

    def put_day(self, day: DayPlan) -> None:
        """Save one day whole. A day with no rows and no baseline is not stored.

        A day emptied *after* being frozen is kept: the baseline is the evidence
        that work was planned and dropped.
        """
        with self._db.connect() as conn:
            pid = active_phase_id(conn)
            row = conn.execute("SELECT id FROM plan_day WHERE phase_id = ? AND date = ?",
                               (pid, day.date)).fetchone()
            if not day.entries and day.baseline is None:
                if row:
                    conn.execute("DELETE FROM plan_day WHERE id = ?", (row["id"],))
                return
            # Non-NULL baseline_at is what "frozen" means here, so a baseline
            # handed over without a time still gets one.
            at = None if day.baseline is None else (day.baseline_at or now_iso())
            if row:
                day_id = row["id"]
                conn.execute("UPDATE plan_day SET baseline_at = ? WHERE id = ?", (at, day_id))
                conn.execute("DELETE FROM plan_entry WHERE plan_day_id = ?", (day_id,))
            else:
                day_id = conn.execute(
                    "INSERT INTO plan_day (phase_id, date, baseline_at) VALUES (?, ?, ?)",
                    (pid, day.date, at)).lastrowid
            for flag, entries in ((0, day.entries), (1, day.baseline or [])):
                for e in entries:
                    mid = member_id(conn, e.pic)
                    # A plan row names someone, so they are on this phase's roster.
                    conn.execute("INSERT OR IGNORE INTO phase_member (phase_id, member_id) "
                                 "VALUES (?, ?)", (pid, mid))
                    conn.execute(
                        "INSERT INTO plan_entry (plan_day_id, is_baseline, member_id, file, "
                        "device, planned) VALUES (?, ?, ?, ?, ?, ?)",
                        (day_id, flag, mid, e.file, e.device, e.planned))

    def settings(self) -> PlanSettings:
        """The active phase's dates and target."""
        with self._db.connect() as conn:
            r = conn.execute("SELECT phase_start, phase_end, daily_target FROM phase WHERE id = ?",
                             (active_phase_id(conn),)).fetchone()
        return PlanSettings(r["phase_start"], r["phase_end"], r["daily_target"])

    def put_settings(self, settings: PlanSettings) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE phase SET phase_start = ?, phase_end = ?, daily_target = ? WHERE id = ?",
                (settings.phase_start, settings.phase_end, settings.daily_target,
                 active_phase_id(conn)))

    def members(self) -> list:
        """The active phase's roster, by name."""
        with self._db.connect() as conn:
            return [r["name"] for r in conn.execute(
                "SELECT m.name FROM phase_member pm JOIN member m ON m.id = pm.member_id "
                "WHERE pm.phase_id = ? ORDER BY m.name", (active_phase_id(conn),))]
