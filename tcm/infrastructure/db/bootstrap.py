"""Opening the database the app runs on."""
from tcm.domain.plan import DEFAULT_TARGET
from tcm.infrastructure.db.database import Database, now_iso


def open_database(path: str) -> Database:
    """Migrate the file at `path` and make sure a phase exists.

    A plan always belongs to a phase, so a database with none would leave the
    planner nowhere to write. The first start therefore creates "Phase 1" and
    makes it active.
    """
    db = Database(path)
    db.migrate()
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM phase LIMIT 1").fetchone() is None:
            cur = conn.execute(
                "INSERT INTO phase (name, daily_target, created_at) VALUES (?, ?, ?)",
                ("Phase 1", DEFAULT_TARGET, now_iso()))
            conn.execute(
                "INSERT OR REPLACE INTO app_state (key, value) VALUES ('active_phase_id', ?)",
                (str(cur.lastrowid),))
    return db
