"""Phases, the roster, and which phase is active."""
import sqlite3

from tcm.domain.phase import Member, NotFound, Phase, member_name
from tcm.infrastructure.db.database import now_iso

_ACTIVE = "active_phase_id"


def active_phase_id(conn) -> int:
    """The active phase: the stored one if it still exists, else the newest.

    Falling back rather than failing, because "the active phase was deleted"
    has one sensible answer and the planner should not 500 over it.
    """
    row = conn.execute(
        "SELECT p.id FROM app_state s JOIN phase p ON p.id = CAST(s.value AS INTEGER) "
        "WHERE s.key = ?", (_ACTIVE,)).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT id FROM phase ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
    if row is None:
        raise RuntimeError("The database has no phase; open it through open_database")
    return row["id"]


def member_id(conn, name: str) -> int:
    """The id of the member called `name`, adding them to the roster if needed."""
    conn.execute("INSERT OR IGNORE INTO member (name) VALUES (?)", (name,))
    return conn.execute("SELECT id FROM member WHERE name = ?", (name,)).fetchone()["id"]


def _set_members(conn, phase_id: int, names) -> None:
    conn.execute("DELETE FROM phase_member WHERE phase_id = ?", (phase_id,))
    conn.executemany("INSERT INTO phase_member (phase_id, member_id) VALUES (?, ?)",
                     [(phase_id, member_id(conn, n)) for n in names])


class SqlPhaseRepository:
    """Phases and members in the SQLite database."""

    def __init__(self, db, now=now_iso):
        self._db = db
        self._now = now

    # --- phases --------------------------------------------------------------

    def phases(self) -> list:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT * FROM phase ORDER BY created_at, id").fetchall()
            return [self._phase(conn, r) for r in rows]

    def phase(self, phase_id: int) -> Phase:
        with self._db.connect() as conn:
            return self._phase(conn, self._row(conn, phase_id))

    def create(self, phase: Phase) -> Phase:
        try:
            with self._db.connect() as conn:
                cur = conn.execute(
                    "INSERT INTO phase (name, phase_start, phase_end, daily_target, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (phase.name, phase.phase_start, phase.phase_end, phase.daily_target,
                     self._now()))
                new_id = cur.lastrowid
                _set_members(conn, new_id, phase.members)
        except sqlite3.IntegrityError:
            raise ValueError(f"A phase called {phase.name} already exists")
        return self.phase(new_id)

    def update(self, phase: Phase) -> Phase:
        try:
            with self._db.connect() as conn:
                self._row(conn, phase.id)
                conn.execute(
                    "UPDATE phase SET name = ?, phase_start = ?, phase_end = ?, daily_target = ? "
                    "WHERE id = ?",
                    (phase.name, phase.phase_start, phase.phase_end, phase.daily_target, phase.id))
                _set_members(conn, phase.id, phase.members)
        except sqlite3.IntegrityError:
            raise ValueError(f"A phase called {phase.name} already exists")
        return self.phase(phase.id)

    def delete(self, phase_id: int) -> None:
        """Delete a phase and every day planned in it. The last phase stays."""
        with self._db.connect() as conn:
            self._row(conn, phase_id)
            if conn.execute("SELECT COUNT(*) FROM phase").fetchone()[0] <= 1:
                raise ValueError("The last phase cannot be deleted — a plan always belongs to one")
            was_active = active_phase_id(conn) == phase_id
            conn.execute("DELETE FROM phase WHERE id = ?", (phase_id,))
            if was_active:
                conn.execute("DELETE FROM app_state WHERE key = ?", (_ACTIVE,))
                self._store_active(conn, active_phase_id(conn))

    def active_id(self) -> int:
        with self._db.connect() as conn:
            return active_phase_id(conn)

    def set_active(self, phase_id: int) -> None:
        with self._db.connect() as conn:
            self._row(conn, phase_id)
            self._store_active(conn, phase_id)

    # --- members -------------------------------------------------------------

    def members(self) -> list:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT id, name FROM member ORDER BY name").fetchall()
        return [Member(r["id"], r["name"]) for r in rows]

    def add_member(self, name: str) -> Member:
        """Put `name` on the roster; a name already there is simply answered."""
        name = member_name(name)
        with self._db.connect() as conn:
            return Member(member_id(conn, name), name)

    def delete_member(self, member_id_: int) -> None:
        """Take someone off the roster and every phase. Refused while a plan names them."""
        with self._db.connect() as conn:
            row = conn.execute("SELECT name FROM member WHERE id = ?", (member_id_,)).fetchone()
            if row is None:
                raise NotFound(f"No member with id {member_id_}")
            days = conn.execute(
                "SELECT COUNT(DISTINCT plan_day_id) FROM plan_entry WHERE member_id = ?",
                (member_id_,)).fetchone()[0]
            if days:
                raise ValueError(f"{row['name']} is still planned on {days} "
                                 f"day{'' if days == 1 else 's'} — remove those rows first")
            conn.execute("DELETE FROM member WHERE id = ?", (member_id_,))

    # --- helpers -------------------------------------------------------------

    @staticmethod
    def _row(conn, phase_id):
        row = conn.execute("SELECT * FROM phase WHERE id = ?", (phase_id,)).fetchone()
        if row is None:
            raise NotFound(f"No phase with id {phase_id}")
        return row

    @staticmethod
    def _phase(conn, row) -> Phase:
        names = [r["name"] for r in conn.execute(
            "SELECT m.name FROM phase_member pm JOIN member m ON m.id = pm.member_id "
            "WHERE pm.phase_id = ? ORDER BY m.name", (row["id"],))]
        return Phase(id=row["id"], name=row["name"], phase_start=row["phase_start"],
                     phase_end=row["phase_end"], daily_target=row["daily_target"],
                     members=tuple(names), created_at=row["created_at"])

    @staticmethod
    def _store_active(conn, phase_id: int) -> None:
        conn.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)",
                     (_ACTIVE, str(phase_id)))
