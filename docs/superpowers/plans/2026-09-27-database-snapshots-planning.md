# Database: Snapshots and Planning — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist load snapshots and the test plan (named phases, a member roster, day plans) in a SQLite database, restore the newest snapshot at startup, and let the user save / open / delete / compare snapshots and manage phases and members from the UI.

**Architecture:** A new `tcm/infrastructure/db/` package (stdlib `sqlite3`) implements three ports — `SnapshotRepository`, `PhaseRepository`, and the existing `PlanRepository` (now scoped to the active phase). Aggregation stays in memory: a snapshot is copied into `InMemoryCaseStore` when opened. `create_app` is the only place the database is opened. The JSON plan store is deleted.

**Tech Stack:** Python 3.14, Flask, stdlib `sqlite3`, pytest; vanilla ES modules, hand-written CSS.

**Spec:** `docs/superpowers/specs/2026-09-27-database-snapshots-planning-design.md`

## Global Constraints

- No new dependency: stdlib `sqlite3` only. All SQL lives under `tcm/infrastructure/db/`.
- `tcm/domain/` may not import `sqlite3` or `sqlalchemy` (added to `FRAMEWORKS` in `tests/test_layering.py`).
- Database file: `settings.DATABASE_FILE`, default `~/.test-management/tcm.db`, env `TCM_DATABASE`.
- `PRAGMA foreign_keys = ON` on every connection; `journal_mode = WAL`; schema version in `PRAGMA user_version`.
- A test case row stores raw cell values only — never a classified status.
- There is always at least one phase and exactly one active phase.
- `plan.json` is not imported; `tcm/infrastructure/plan/`, `settings.PLAN_FILE` and `tests/infrastructure/test_plan_store.py` are deleted.
- Domain `ValueError` → 400 with its message; unknown id (`LookupError`) → 404.
- Every `fetch` lives in `static/js/api.js`. No accent colour; statuses keep their tones. Only `<dialog>` in the app stays the slot editor.
- Tests never touch `~/.test-management`: an autouse fixture points `DATABASE_FILE` at a temp dir.
- Commits: run git as `/usr/bin/git` (the rtk hook's rewrite is refused inside the worktree). End each message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Run tests with `.venv/bin/python -m pytest`.

## Review Focus

1. **Two workbooks with the same basename in different subfolders** — a snapshot round trip must keep both `file_results` entries and every case (Task 3 test `test_duplicate_basenames_survive_a_round_trip`).
2. **Opening a snapshot, then Reload** — the reload re-reads the snapshot's source and the rail goes back to *Live* (`origin` is None) (Task 5 test `test_reload_after_opening_a_snapshot_goes_live`).
3. **Deleting the active phase that holds plans** — its plans go with it, the active phase moves to the newest remaining one, and the planner does not 500 (Task 4 test `test_deleting_the_active_phase_moves_active_and_drops_its_plans`).
4. **Two snapshots saved in the same second** — list order and "latest" must still be the later one (Task 3 test `test_same_second_snapshots_order_by_id`).
5. **First start with no `~/.test-management` folder** — the database directory is created rather than failing (Task 1 test `test_migrate_creates_the_missing_folder`).

---

## File Structure

| File | Responsibility |
|---|---|
| `tcm/settings.py` | `DATABASE_FILE`; `PLAN_FILE` removed |
| `tcm/infrastructure/db/__init__.py` | package docstring |
| `tcm/infrastructure/db/schema.py` | `MIGRATIONS` list (v1 schema) |
| `tcm/infrastructure/db/database.py` | `Database`: connect, migrate, backup |
| `tcm/infrastructure/db/bootstrap.py` | `open_database(path)`: migrate + ensure a phase |
| `tcm/infrastructure/db/snapshots.py` | `SqlSnapshotRepository` |
| `tcm/infrastructure/db/phases.py` | `SqlPhaseRepository`, `active_phase_id`, `member_id` helpers |
| `tcm/infrastructure/db/plans.py` | `SqlPlanRepository` (active phase) |
| `tcm/domain/phase.py` | `Phase`, `Member`, `member_name`, `NotFound` |
| `tcm/domain/ports.py` | `Snapshot.origin`, `SnapshotRepository`, `PhaseRepository`, `PlanRepository.members` |
| `tcm/services/workspace.py` | snapshot save/open/delete/restore/compare, `state()` |
| `tcm/services/aggregation.py` | `compare_cases` |
| `tcm/services/phases.py` | `PhaseService` |
| `tcm/services/planning.py` | board members from the roster |
| `tcm/web/app.py` | open the DB, wire repositories |
| `tcm/web/blueprints/__init__.py` | `phase_service()` helper |
| `tcm/web/blueprints/snapshots.py` | `/api/workspace`, `/api/snapshots*` |
| `tcm/web/blueprints/phases.py` | `/api/phases*`, `/api/members*` |
| `static/js/api.js` | new fetch helpers |
| `static/js/dom.js` | `formatStamp` |
| `static/js/snapshotPanel.js` | Tools → Snapshots card |
| `static/js/shell.js`, `templates/index.html` | rail *Live / Snapshot* line |
| `static/js/main.js` | startup restore, snapshot + compare routing |
| `static/js/views/compare.js`, `templates/views/compare.html` | Compare drill-in view |
| `static/js/views/planning/phases.js`, `templates/views/planning.html` | Phases & members card, phase select |
| `static/css/views.css` | small additions at the end |
| `CLAUDE.md`, `README.md` | documentation |

---

### Task 1: Database core, migrations and bootstrap

**Files:**
- Create: `tcm/infrastructure/db/__init__.py`, `tcm/infrastructure/db/schema.py`, `tcm/infrastructure/db/database.py`, `tcm/infrastructure/db/bootstrap.py`
- Modify: `tcm/settings.py` (add `DATABASE_FILE` after `PLAN_FILE`), `tests/conftest.py` (autouse fixture), `tests/test_layering.py:18`
- Test: `tests/infrastructure/test_db.py`

**Interfaces:**
- Produces: `Database(path)` with `.path`, `.connect()` (context manager yielding a `sqlite3.Connection` with `row_factory = sqlite3.Row`; commits on success, rolls back on error), `.version() -> int`, `.migrate() -> None`, `.backup(dest: str) -> None`; `MIGRATIONS: list[str]`; `open_database(path: str) -> Database`; `now_iso() -> str` in `database.py`.

- [ ] **Step 1: Settings, conftest fixture, layering**

In `tcm/settings.py`, after the `PLAN_FILE` block add:

```python
# The database: load snapshots and the test plan. Not in config/ for the reason
# the plan never was -- it is this machine's operational data, and the plan in
# it is the only copy there is.
DATABASE_FILE = os.path.expanduser(
    os.environ.get("TCM_DATABASE", "~/.test-management/tcm.db")
)
```

In `tests/conftest.py`, append:

```python
# --- the database ------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_database(tmp_path_factory, monkeypatch):
    """Point the database at a fresh temp file for every test.

    Autouse because `create_app()` with no arguments opens the database, and a
    test that forgot this would write into the user's real ~/.test-management.
    A directory of its own rather than `tmp_path`, so tests that list their
    `tmp_path` never see a stray `tcm.db` beside their workbooks.
    """
    import tcm.settings as app_settings
    path = tmp_path_factory.mktemp("db") / "tcm.db"
    monkeypatch.setattr(app_settings, "DATABASE_FILE", str(path))
    return path
```

In `tests/test_layering.py` line 18 change to:

```python
FRAMEWORKS = {"flask", "pandas", "openpyxl", "requests", "msal", "sqlite3", "sqlalchemy"}
```

- [ ] **Step 2: Write the failing tests** — `tests/infrastructure/test_db.py`

```python
"""The database file: opening, migrating, backing up, and the first phase."""
import sqlite3

import pytest

from tcm.infrastructure.db import database as database_module
from tcm.infrastructure.db.bootstrap import open_database
from tcm.infrastructure.db.database import Database
from tcm.infrastructure.db.schema import MIGRATIONS


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / "tcm.db"))
    d.migrate()
    return d


def tables(db):
    with db.connect() as conn:
        return {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}


def test_a_fresh_file_migrates_to_the_latest_version(db):
    assert db.version() == len(MIGRATIONS)
    assert {"app_state", "member", "phase", "phase_member", "plan_day", "plan_entry",
            "snapshot", "snapshot_file", "test_case"} <= tables(db)


def test_migrate_creates_the_missing_folder(tmp_path):
    d = Database(str(tmp_path / "nested" / "deeper" / "tcm.db"))
    d.migrate()
    assert d.version() == len(MIGRATIONS)


def test_migrating_twice_is_a_no_op_and_backs_nothing_up(db, tmp_path):
    db.migrate()
    assert not list(tmp_path.glob("*.bak"))


def test_an_older_database_is_backed_up_before_migrating(db, tmp_path, monkeypatch):
    monkeypatch.setattr(database_module, "MIGRATIONS",
                        MIGRATIONS + ["CREATE TABLE extra (x INTEGER);"])
    db.migrate()
    backups = list(tmp_path.glob("tcm.db.v1-*.bak"))
    assert len(backups) == 1
    assert db.version() == len(MIGRATIONS) + 1
    # The backup is the database as it was: version 1, no `extra` table.
    old = Database(str(backups[0]))
    assert old.version() == 1
    assert "extra" not in tables(old)


def test_a_failed_migration_changes_nothing(db, monkeypatch):
    monkeypatch.setattr(database_module, "MIGRATIONS",
                        MIGRATIONS + ["CREATE TABLE ok (x); CREATE TABLE ok (x);"])
    with pytest.raises(sqlite3.OperationalError):
        db.migrate()
    assert db.version() == len(MIGRATIONS)
    assert "ok" not in tables(db)


def test_a_newer_database_is_refused(db):
    with db.connect() as conn:
        conn.execute("PRAGMA user_version = 99")
    with pytest.raises(RuntimeError, match="newer"):
        db.migrate()


def test_foreign_keys_are_enforced(db):
    with pytest.raises(sqlite3.IntegrityError):
        with db.connect() as conn:
            conn.execute("INSERT INTO phase_member (phase_id, member_id) VALUES (1, 1)")


def test_open_database_creates_phase_1_once(tmp_path):
    path = str(tmp_path / "tcm.db")
    open_database(path)
    db = open_database(path)
    with db.connect() as conn:
        rows = conn.execute("SELECT id, name FROM phase").fetchall()
        active = conn.execute(
            "SELECT value FROM app_state WHERE key = 'active_phase_id'").fetchone()
    assert [r["name"] for r in rows] == ["Phase 1"]
    assert active["value"] == str(rows[0]["id"])
```

- [ ] **Step 3: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/infrastructure/test_db.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tcm.infrastructure.db'`

- [ ] **Step 4: Implement**

`tcm/infrastructure/db/__init__.py`:

```python
"""The SQLite database: load snapshots and the test plan.

Every line of SQL in the app lives in this package. The engine is stdlib
`sqlite3` for now; the services reach it only through the ports in
`tcm.domain.ports`, so moving to SQLAlchemy or another database rewrites this
folder and `create_app`, and nothing else.
"""
```

`tcm/infrastructure/db/schema.py`:

```python
"""The schema, as an ordered list of migrations.

`MIGRATIONS[n]` takes a database from version n to n + 1; the version lives in
`PRAGMA user_version`. Never edit a migration that has shipped -- append one.
"""

MIGRATIONS = [
    # v1: snapshots, phases, members, plans.
    """
    CREATE TABLE app_state (key TEXT PRIMARY KEY, value TEXT);

    CREATE TABLE member (
        id   INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE
    );

    CREATE TABLE phase (
        id           INTEGER PRIMARY KEY,
        name         TEXT NOT NULL UNIQUE,
        phase_start  TEXT,
        phase_end    TEXT,
        daily_target INTEGER NOT NULL DEFAULT 30 CHECK (daily_target > 0),
        created_at   TEXT NOT NULL
    );

    CREATE TABLE phase_member (
        phase_id  INTEGER NOT NULL REFERENCES phase(id)  ON DELETE CASCADE,
        member_id INTEGER NOT NULL REFERENCES member(id) ON DELETE CASCADE,
        PRIMARY KEY (phase_id, member_id)
    );

    CREATE TABLE plan_day (
        id          INTEGER PRIMARY KEY,
        phase_id    INTEGER NOT NULL REFERENCES phase(id) ON DELETE CASCADE,
        date        TEXT NOT NULL,
        baseline_at TEXT,
        UNIQUE (phase_id, date)
    );

    CREATE TABLE plan_entry (
        id          INTEGER PRIMARY KEY,
        plan_day_id INTEGER NOT NULL REFERENCES plan_day(id) ON DELETE CASCADE,
        is_baseline INTEGER NOT NULL CHECK (is_baseline IN (0, 1)),
        member_id   INTEGER NOT NULL REFERENCES member(id) ON DELETE RESTRICT,
        file        TEXT NOT NULL,
        device      TEXT NOT NULL,
        planned     INTEGER NOT NULL CHECK (planned > 0),
        UNIQUE (plan_day_id, is_baseline, member_id, file, device)
    );
    CREATE INDEX plan_entry_member ON plan_entry(member_id);

    CREATE TABLE snapshot (
        id         INTEGER PRIMARY KEY,
        taken_at   TEXT NOT NULL,
        label      TEXT NOT NULL DEFAULT '',
        source     TEXT,
        case_count INTEGER NOT NULL,
        file_count INTEGER NOT NULL
    );

    CREATE TABLE snapshot_file (
        id          INTEGER PRIMARY KEY,
        snapshot_id INTEGER NOT NULL REFERENCES snapshot(id) ON DELETE CASCADE,
        position    INTEGER NOT NULL,
        file        TEXT NOT NULL,
        path        TEXT,
        status      TEXT NOT NULL,
        result      TEXT
    );
    CREATE INDEX snapshot_file_snapshot ON snapshot_file(snapshot_id);

    CREATE TABLE test_case (
        id               INTEGER PRIMARY KEY,
        snapshot_file_id INTEGER NOT NULL REFERENCES snapshot_file(id) ON DELETE CASCADE,
        position         INTEGER NOT NULL,
        sheet     TEXT NOT NULL,
        device    TEXT NOT NULL,
        row_num   INTEGER NOT NULL,
        case_no   TEXT,
        scope     TEXT,
        result    TEXT,
        test_date TEXT,
        pic       TEXT,
        ticket_id TEXT,
        note      TEXT
    );
    CREATE INDEX test_case_file ON test_case(snapshot_file_id);
    """,
]
```

(`snapshot_file.result` is nullable: a row with `position = -1` is a file a case named but no load result described — see Task 3.)

`tcm/infrastructure/db/database.py`:

```python
"""One SQLite file, opened a connection per unit of work.

A connection per call rather than one shared: Flask's dev server is threaded,
and a `sqlite3.Connection` belongs to the thread that made it. Opening one is
cheap next to anything the app does with it.
"""
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from tcm.infrastructure.db.schema import MIGRATIONS

log = logging.getLogger(__name__)


def now_iso() -> str:
    """The local time to the second, the way every timestamp here is written."""
    return datetime.now().isoformat(timespec="seconds")


class Database:
    """The database file at `path`."""

    def __init__(self, path: str):
        self.path = path

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        # Off by default in SQLite, per connection -- and every cascade and
        # RESTRICT in the schema depends on it.
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def connect(self):
        """A connection that commits when the block succeeds and rolls back when it raises."""
        conn = self._open()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def version(self) -> int:
        with self.connect() as conn:
            return conn.execute("PRAGMA user_version").fetchone()[0]

    def backup(self, dest: str) -> None:
        """Copy the database with SQLite's online backup, safe while it is open."""
        src, dst = self._open(), sqlite3.connect(dest)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()

    def migrate(self) -> None:
        """Bring the schema up to date, backing up a database that already had one.

        Each migration runs in its own transaction together with the version
        bump, so a failure leaves the file at the last version that succeeded.
        """
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        current, target = self.version(), len(MIGRATIONS)
        if current > target:
            raise RuntimeError(
                f"{self.path} is schema version {current}, newer than this app "
                f"understands ({target}) -- was it written by a later version?")
        if current == target:
            return
        if current > 0:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            dest = f"{self.path}.v{current}-{stamp}.bak"
            self.backup(dest)
            log.info("Backed up %s to %s before migrating", self.path, dest)

        conn = self._open()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            for version in range(current, target):
                try:
                    conn.executescript(
                        "BEGIN;\n" + MIGRATIONS[version]
                        + f"\nPRAGMA user_version = {version + 1};\nCOMMIT;")
                except Exception:
                    if conn.in_transaction:
                        conn.rollback()
                    raise
        finally:
            conn.close()
```

`tcm/infrastructure/db/bootstrap.py`:

```python
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
```

- [ ] **Step 5: Run to verify they pass, then the whole suite**

Run: `.venv/bin/python -m pytest tests/infrastructure/test_db.py -q && .venv/bin/python -m pytest -q`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
/usr/bin/git add tcm/infrastructure/db tcm/settings.py tests/conftest.py tests/test_layering.py tests/infrastructure/test_db.py
/usr/bin/git commit -m "Add the SQLite database with migrations and a first phase" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Domain — phases, members, and the new ports

**Files:**
- Create: `tcm/domain/phase.py`
- Modify: `tcm/domain/ports.py`
- Test: `tests/domain/test_phase.py`

**Interfaces:**
- Produces:
  - `class NotFound(LookupError)`
  - `member_name(value, source="member") -> str` (stripped, non-empty, else `ValueError`)
  - `@dataclass(frozen=True) Member(id: int, name: str)` with `to_dict()`
  - `@dataclass(frozen=True) Phase(id: Optional[int], name: str, phase_start=None, phase_end=None, daily_target=DEFAULT_TARGET, members: tuple = (), created_at=None)` with `.settings -> PlanSettings`, `Phase.from_dict(raw, id=None, source="phase")`, `to_dict()`
  - `Snapshot.origin: Optional[dict] = None`
  - `SnapshotRepository` protocol: `save(snapshot, label) -> dict`, `list() -> list[dict]`, `load(snapshot_id) -> Optional[Snapshot]`, `delete(snapshot_id) -> bool`, `latest_id() -> Optional[int]`
  - `PhaseRepository` protocol: `phases()`, `phase(phase_id)`, `create(phase)`, `update(phase)`, `delete(phase_id)`, `active_id()`, `set_active(phase_id)`, `members()`, `add_member(name)`, `delete_member(member_id)`
  - `PlanRepository.members() -> list[str]`

- [ ] **Step 1: Write the failing tests** — `tests/domain/test_phase.py`

```python
"""What a phase is allowed to say."""
import pytest

from tcm.domain.phase import Member, Phase, member_name
from tcm.domain.plan import DEFAULT_TARGET, PlanSettings


def test_a_minimal_phase_takes_the_defaults():
    p = Phase.from_dict({"name": " Sprint 12 "})
    assert p.name == "Sprint 12"
    assert (p.phase_start, p.phase_end, p.daily_target, p.members) == (None, None, DEFAULT_TARGET, ())
    assert p.settings == PlanSettings()


def test_a_full_phase_round_trips():
    raw = {"name": "Regression", "phase_start": "2026-09-01", "phase_end": "2026-09-30",
           "daily_target": 40, "members": ["An", "Bo"]}
    p = Phase.from_dict(raw, id=3)
    d = p.to_dict()
    assert d["id"] == 3 and d["members"] == ["An", "Bo"]
    assert p.settings == PlanSettings("2026-09-01", "2026-09-30", 40)


@pytest.mark.parametrize("raw, message", [
    ({}, "name"),
    ({"name": "  "}, "name"),
    ({"name": "P", "phase_start": "2026-09-30", "phase_end": "2026-09-01"}, "before it starts"),
    ({"name": "P", "daily_target": 0}, "daily_target"),
    ({"name": "P", "members": "An"}, "members"),
    ({"name": "P", "members": ["An", " An "]}, "twice"),
    ({"name": "P", "members": [""]}, "name"),
])
def test_bad_phases_are_refused_with_a_reason(raw, message):
    with pytest.raises(ValueError, match=message):
        Phase.from_dict(raw)


def test_member_names_are_stripped_and_required():
    assert member_name("  An ") == "An"
    with pytest.raises(ValueError):
        member_name(None)
    assert Member(1, "An").to_dict() == {"id": 1, "name": "An"}
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/domain/test_phase.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tcm.domain.phase'`

- [ ] **Step 3: Implement `tcm/domain/phase.py`**

```python
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
        members: Member names on this phase's roster, in the order given.
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
```

- [ ] **Step 4: Extend `tcm/domain/ports.py`**

Add to the `Snapshot` dataclass (after `source`), and to its docstring's Attributes:

```python
    origin: Optional[dict] = None
```
```
        origin: None for a live load; `{"id", "taken_at", "label"}` when the
            cases came out of a stored snapshot.
```

Add `members` to `PlanRepository` (after `put_settings`), and one sentence to its docstring: "`members` is the active phase's roster; an empty list means nobody has made one."

```python
    def members(self) -> list:
        ...
```

Replace the `PlanRepository` docstring's first line with: `"""Where the test plan is kept: the active phase's days and settings."""`

Append two protocols:

```python
@runtime_checkable
class SnapshotRepository(Protocol):
    """Saved loads. A snapshot is the cases and file results as they were read.

    `save` answers the stored snapshot's metadata --
    `{"id", "taken_at", "label", "source", "case_count", "file_count"}` -- which
    is also what each item of `list` is, newest first. `load` answers None for an
    id it does not know, and `delete` False.
    """

    def save(self, snapshot: Snapshot, label: str) -> dict:
        ...

    def list(self) -> list:
        ...

    def load(self, snapshot_id: int) -> Optional[Snapshot]:
        ...

    def delete(self, snapshot_id: int) -> bool:
        ...

    def latest_id(self) -> Optional[int]:
        ...


@runtime_checkable
class PhaseRepository(Protocol):
    """Phases, the member roster, and which phase is active.

    An unknown id raises `tcm.domain.phase.NotFound`; a rule broken -- a
    duplicate name, the last phase, a member still planned -- raises ValueError.
    """

    def phases(self) -> list:
        ...

    def phase(self, phase_id: int):
        ...

    def create(self, phase):
        ...

    def update(self, phase):
        ...

    def delete(self, phase_id: int) -> None:
        ...

    def active_id(self) -> int:
        ...

    def set_active(self, phase_id: int) -> None:
        ...

    def members(self) -> list:
        ...

    def add_member(self, name: str):
        ...

    def delete_member(self, member_id: int) -> None:
        ...
```

Also change the module docstring's "Each has one implementation today." to "Each has one production implementation."

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/domain -q`
Expected: `test_phase.py` PASS; `test_ports.py::test_the_json_plan_repository_is_a_plan_repository` now FAILS (JsonPlanRepository has no `members`). Make it pass by adding to `tcm/infrastructure/plan/json_store.py` (deleted in Task 7, kept green until then):

```python
    def members(self) -> list:
        return []
```

Also add `members()` returning `[]` (or a configured list) to both `FakePlanRepository` classes — `tests/services/test_planning.py` and `tests/web/test_api_planning.py`:

```python
    _members = ()

    def members(self):
        return list(self._members)
```

Run: `.venv/bin/python -m pytest -q` → all PASS.

- [ ] **Step 6: Commit**

```bash
/usr/bin/git add tcm/domain tcm/infrastructure/plan/json_store.py tests/domain/test_phase.py tests/services/test_planning.py tests/web/test_api_planning.py
/usr/bin/git commit -m "Name phases, members and the snapshot and phase ports" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `SqlSnapshotRepository`

**Files:**
- Create: `tcm/infrastructure/db/snapshots.py`
- Test: `tests/infrastructure/test_db_snapshots.py`

**Interfaces:**
- Consumes: `Database`, `now_iso` (Task 1); `Snapshot`, `SnapshotRepository` (Task 2); `TestCase` (`tcm.domain.case`).
- Produces: `SqlSnapshotRepository(db, now=now_iso)` implementing `SnapshotRepository`. Meta dict keys: `id, taken_at, label, source, case_count, file_count`. `load()` sets `origin = {"id", "taken_at", "label"}`.

- [ ] **Step 1: Write the failing tests**

```python
"""Snapshots in the database: what goes in comes back out, in order."""
import pytest

from tcm.domain.case import TestCase
from tcm.domain.ports import Snapshot, SnapshotRepository
from tcm.infrastructure.db.bootstrap import open_database
from tcm.infrastructure.db.snapshots import SqlSnapshotRepository


@pytest.fixture
def db(tmp_path):
    return open_database(str(tmp_path / "tcm.db"))


def clock(*stamps):
    it = iter(stamps)
    return lambda: next(it)


def snap():
    cases = [
        TestCase("A.xlsx", "Login", "iPhone", 4, "TC-1", "FPT", "OK", "2026-09-01", "An", None, None),
        TestCase("A.xlsx", "Login", "iPad", 4, "TC-1", "FPT", None, None, None, None, None),
        TestCase("B.xlsx", "Pay", "iPhone", 9, "TC-9", "JP", "NG", "2026-09-02", "Bo", "BUG-1", "note ✓"),
    ]
    files = [
        {"file": "A.xlsx", "path": "/src/A.xlsx", "status": "ok", "cases": 2},
        {"file": "B.xlsx", "path": "/src/B.xlsx", "status": "ok", "cases": 1},
        {"file": "C.xlsx", "path": "/src/C.xlsx", "status": "error", "error": "bad TOOL_DATA"},
    ]
    return Snapshot(cases=cases, file_results=files, source={"type": "folder", "value": "/src"})


def test_it_answers_the_port():
    assert issubclass(SqlSnapshotRepository, SnapshotRepository)


def test_a_snapshot_round_trips_exactly(db):
    repo = SqlSnapshotRepository(db, now=clock("2026-09-27T14:02:00"))
    meta = repo.save(snap(), " end of day ")
    assert meta == {"id": meta["id"], "taken_at": "2026-09-27T14:02:00", "label": "end of day",
                    "source": {"type": "folder", "value": "/src"},
                    "case_count": 3, "file_count": 3}
    back = repo.load(meta["id"])
    assert back.cases == snap().cases
    assert back.file_results == snap().file_results
    assert back.source == snap().source
    assert back.origin == {"id": meta["id"], "taken_at": "2026-09-27T14:02:00", "label": "end of day"}


def test_duplicate_basenames_survive_a_round_trip(db):
    s = Snapshot(
        cases=[TestCase("TC.xlsx", "S", "iPhone", 1), TestCase("TC.xlsx", "S", "iPhone", 2)],
        file_results=[{"file": "TC.xlsx", "path": "/a/TC.xlsx", "status": "ok"},
                      {"file": "TC.xlsx", "path": "/b/TC.xlsx", "status": "ok"}],
        source={"type": "folder", "value": "/"})
    repo = SqlSnapshotRepository(db)
    back = repo.load(repo.save(s, "")["id"])
    assert back.file_results == s.file_results
    assert back.cases == s.cases


def test_a_case_whose_file_has_no_result_row_still_comes_back(db):
    s = Snapshot(cases=[TestCase("X.xlsx", "S", "iPhone", 1)], file_results=[], source=None)
    repo = SqlSnapshotRepository(db)
    back = repo.load(repo.save(s, "")["id"])
    assert back.cases == s.cases
    assert back.file_results == []


def test_list_is_newest_first_and_latest_is_the_newest(db):
    repo = SqlSnapshotRepository(db, now=clock("2026-09-26T09:00:00", "2026-09-27T09:00:00"))
    first = repo.save(snap(), "one")
    second = repo.save(snap(), "two")
    assert [m["label"] for m in repo.list()] == ["two", "one"]
    assert repo.latest_id() == second["id"] != first["id"]


def test_same_second_snapshots_order_by_id(db):
    repo = SqlSnapshotRepository(db, now=lambda: "2026-09-27T09:00:00")
    repo.save(snap(), "one")
    later = repo.save(snap(), "two")
    assert repo.list()[0]["label"] == "two"
    assert repo.latest_id() == later["id"]


def test_delete_removes_every_row_it_owned(db):
    repo = SqlSnapshotRepository(db)
    sid = repo.save(snap(), "")["id"]
    assert repo.delete(sid) is True
    assert repo.load(sid) is None
    assert repo.delete(sid) is False
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM test_case").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM snapshot_file").fetchone()[0] == 0


def test_an_empty_database_has_no_latest(db):
    assert SqlSnapshotRepository(db).latest_id() is None
    assert SqlSnapshotRepository(db).list() == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/infrastructure/test_db_snapshots.py -q`
Expected: FAIL — `No module named 'tcm.infrastructure.db.snapshots'`

- [ ] **Step 3: Implement `tcm/infrastructure/db/snapshots.py`**

```python
"""Snapshots: a load, kept.

A test case is stored as the raw cells it was read from and never as a status,
so an old snapshot re-classifies with whatever the taxonomy says today.

Cases hang off the file they came from. A case names its file by basename only,
so when two subfolders both hold a `TC.xlsx` the cases go under the first of
them -- they come back with the same `file_name` either way, which is all a
`TestCase` records. A case naming a file no load result describes gets a row
with `position = -1`, which `load` does not report as a file result.
"""
import json
from typing import Optional

from tcm.domain.case import TestCase
from tcm.domain.ports import Snapshot
from tcm.infrastructure.db.database import now_iso

_CASE_FIELDS = ("sheet", "device", "row_num", "case_no", "scope", "result",
                "test_date", "pic", "ticket_id", "note")


def _meta(row) -> dict:
    return {"id": row["id"], "taken_at": row["taken_at"], "label": row["label"],
            "source": json.loads(row["source"]) if row["source"] else None,
            "case_count": row["case_count"], "file_count": row["file_count"]}


class SqlSnapshotRepository:
    """Snapshots in the SQLite database."""

    def __init__(self, db, now=now_iso):
        self._db = db
        self._now = now

    def save(self, snapshot: Snapshot, label: str = "") -> dict:
        label = (label or "").strip()
        with self._db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO snapshot (taken_at, label, source, case_count, file_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (self._now(), label,
                 json.dumps(snapshot.source, ensure_ascii=False) if snapshot.source else None,
                 len(snapshot.cases), len(snapshot.file_results)))
            sid = cur.lastrowid

            file_ids = {}
            for pos, fr in enumerate(snapshot.file_results):
                c = conn.execute(
                    "INSERT INTO snapshot_file (snapshot_id, position, file, path, status, result) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (sid, pos, fr.get("file") or "", fr.get("path"), fr.get("status") or "",
                     json.dumps(fr, ensure_ascii=False)))
                file_ids.setdefault(fr.get("file"), c.lastrowid)
            for case in snapshot.cases:
                if case.file_name not in file_ids:
                    c = conn.execute(
                        "INSERT INTO snapshot_file (snapshot_id, position, file, status) "
                        "VALUES (?, -1, ?, '')", (sid, case.file_name))
                    file_ids[case.file_name] = c.lastrowid

            conn.executemany(
                "INSERT INTO test_case (snapshot_file_id, position, " + ", ".join(_CASE_FIELDS)
                + ") VALUES (?, ?" + ", ?" * len(_CASE_FIELDS) + ")",
                ((file_ids[c.file_name], i, *(getattr(c, f) for f in _CASE_FIELDS))
                 for i, c in enumerate(snapshot.cases)))
            row = conn.execute("SELECT * FROM snapshot WHERE id = ?", (sid,)).fetchone()
        return _meta(row)

    def list(self) -> list:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM snapshot ORDER BY taken_at DESC, id DESC").fetchall()
        return [_meta(r) for r in rows]

    def load(self, snapshot_id: int) -> Optional[Snapshot]:
        with self._db.connect() as conn:
            row = conn.execute("SELECT * FROM snapshot WHERE id = ?", (snapshot_id,)).fetchone()
            if row is None:
                return None
            files = conn.execute(
                "SELECT id, position, file, result FROM snapshot_file "
                "WHERE snapshot_id = ? ORDER BY position, id", (snapshot_id,)).fetchall()
            cases = conn.execute(
                "SELECT tc.* FROM test_case tc JOIN snapshot_file f ON f.id = tc.snapshot_file_id "
                "WHERE f.snapshot_id = ? ORDER BY tc.position", (snapshot_id,)).fetchall()
        names = {f["id"]: f["file"] for f in files}
        meta = _meta(row)
        return Snapshot(
            cases=[TestCase(file_name=names[r["snapshot_file_id"]],
                            **{f: r[f] for f in _CASE_FIELDS}) for r in cases],
            file_results=[json.loads(f["result"]) for f in files if f["position"] >= 0],
            source=meta["source"],
            origin={"id": meta["id"], "taken_at": meta["taken_at"], "label": meta["label"]},
        )

    def delete(self, snapshot_id: int) -> bool:
        with self._db.connect() as conn:
            return conn.execute("DELETE FROM snapshot WHERE id = ?",
                                (snapshot_id,)).rowcount > 0

    def latest_id(self) -> Optional[int]:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT id FROM snapshot ORDER BY taken_at DESC, id DESC LIMIT 1").fetchone()
        return row["id"] if row else None
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/infrastructure/test_db_snapshots.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
/usr/bin/git add tcm/infrastructure/db/snapshots.py tests/infrastructure/test_db_snapshots.py
/usr/bin/git commit -m "Keep snapshots of a load in the database" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: `SqlPhaseRepository` and `SqlPlanRepository`

**Files:**
- Create: `tcm/infrastructure/db/phases.py`, `tcm/infrastructure/db/plans.py`
- Test: `tests/infrastructure/test_db_phases.py`, `tests/infrastructure/test_db_plans.py`

**Interfaces:**
- Consumes: `Database`, `now_iso`, `open_database` (Task 1); `Phase`, `Member`, `NotFound`, `member_name`, `PhaseRepository`, `PlanRepository` (Task 2); `DayPlan`, `PlanEntry`, `PlanSettings`, `parse_date` (`tcm.domain.plan`).
- Produces:
  - `active_phase_id(conn) -> int` and `member_id(conn, name) -> int` (module functions in `phases.py`)
  - `SqlPhaseRepository(db, now=now_iso)`: `phases() -> list[Phase]` (oldest first), `phase(id) -> Phase` (raises `NotFound`), `create(Phase) -> Phase`, `update(Phase) -> Phase`, `delete(id)`, `active_id() -> int`, `set_active(id)`, `members() -> list[Member]` (by name), `add_member(name) -> Member` (idempotent), `delete_member(id)`
  - `SqlPlanRepository(db)`: `day`, `days`, `put_day`, `settings`, `put_settings`, `members() -> list[str]` — all for the active phase

- [ ] **Step 1: Write the failing phase tests** — `tests/infrastructure/test_db_phases.py`

```python
"""Phases and the roster in the database."""
import pytest

from tcm.domain.phase import NotFound, Phase
from tcm.domain.plan import DayPlan, PlanEntry
from tcm.domain.ports import PhaseRepository
from tcm.infrastructure.db.bootstrap import open_database
from tcm.infrastructure.db.phases import SqlPhaseRepository
from tcm.infrastructure.db.plans import SqlPlanRepository


@pytest.fixture
def db(tmp_path):
    return open_database(str(tmp_path / "tcm.db"))


@pytest.fixture
def repo(db):
    return SqlPhaseRepository(db)


def test_it_answers_the_port():
    assert issubclass(SqlPhaseRepository, PhaseRepository)


def test_a_new_database_has_phase_1_active(repo):
    [p] = repo.phases()
    assert p.name == "Phase 1" and repo.active_id() == p.id


def test_create_stores_the_phase_and_its_members(repo):
    p = repo.create(Phase.from_dict({"name": "Sprint 12", "phase_start": "2026-09-01",
                                     "members": ["Bo", "An"]}))
    assert p.id and p.created_at
    assert repo.phase(p.id).members == ("An", "Bo")
    assert [m.name for m in repo.members()] == ["An", "Bo"]


def test_a_duplicate_name_is_refused(repo):
    with pytest.raises(ValueError, match="already exists"):
        repo.create(Phase.from_dict({"name": "Phase 1"}))


def test_update_replaces_fields_and_members(repo):
    p = repo.create(Phase.from_dict({"name": "S", "members": ["An"]}))
    repo.update(Phase.from_dict({"name": "S2", "daily_target": 12, "members": ["Bo"]}, id=p.id))
    q = repo.phase(p.id)
    assert (q.name, q.daily_target, q.members) == ("S2", 12, ("Bo",))
    # An stays on the roster: leaving a phase is not leaving the team.
    assert [m.name for m in repo.members()] == ["An", "Bo"]


def test_unknown_ids_are_not_found(repo):
    with pytest.raises(NotFound):
        repo.phase(999)
    with pytest.raises(NotFound):
        repo.update(Phase.from_dict({"name": "X"}, id=999))
    with pytest.raises(NotFound):
        repo.set_active(999)
    with pytest.raises(NotFound):
        repo.delete(999)
    with pytest.raises(NotFound):
        repo.delete_member(999)


def test_the_last_phase_cannot_be_deleted(repo):
    with pytest.raises(ValueError, match="last phase"):
        repo.delete(repo.active_id())


def test_deleting_the_active_phase_moves_active_and_drops_its_plans(db, repo):
    first = repo.active_id()
    second = repo.create(Phase.from_dict({"name": "Sprint 2"}))
    repo.set_active(second.id)
    SqlPlanRepository(db).put_day(DayPlan("2026-09-22", [PlanEntry("An", "A.xlsx", "iPhone", 5)]))
    repo.delete(second.id)
    assert repo.active_id() == first
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM plan_day").fetchone()[0] == 0
    assert SqlPlanRepository(db).days() == []


def test_add_member_is_idempotent(repo):
    a = repo.add_member(" An ")
    assert repo.add_member("An") == a
    assert [m.name for m in repo.members()] == ["An"]


def test_a_member_still_planned_cannot_be_deleted(db, repo):
    SqlPlanRepository(db).put_day(DayPlan("2026-09-22", [PlanEntry("An", "A.xlsx", "iPhone", 5)]))
    [an] = repo.members()
    with pytest.raises(ValueError, match="still planned on 1 day"):
        repo.delete_member(an.id)


def test_deleting_a_member_takes_them_off_every_phase(repo):
    p = repo.create(Phase.from_dict({"name": "S", "members": ["An"]}))
    [an] = repo.members()
    repo.delete_member(an.id)
    assert repo.phase(p.id).members == ()
    assert repo.members() == []
```

- [ ] **Step 2: Write the failing plan tests** — `tests/infrastructure/test_db_plans.py`

```python
"""The plan in the database, scoped to the active phase.

The day-level rules are the ones the JSON store had: nobody-planned is an empty
day, an emptied day stops taking up room, a frozen baseline is kept -- even an
empty one.
"""
import pytest

from tcm.domain.phase import Phase
from tcm.domain.plan import DayPlan, PlanEntry, PlanSettings
from tcm.domain.ports import PlanRepository
from tcm.infrastructure.db.bootstrap import open_database
from tcm.infrastructure.db.phases import SqlPhaseRepository
from tcm.infrastructure.db.plans import SqlPlanRepository


@pytest.fixture
def db(tmp_path):
    return open_database(str(tmp_path / "tcm.db"))


@pytest.fixture
def store(db):
    return SqlPlanRepository(db)


def day(date="2026-09-22", entries=(("An", "TC.xlsx", "iPhone", 30),), baseline=None, at=None):
    mk = lambda rows: [PlanEntry(pic=p, file=f, device=d, planned=n) for p, f, d, n in rows]
    return DayPlan(date=date, entries=mk(entries),
                   baseline=None if baseline is None else mk(baseline), baseline_at=at)


def test_it_answers_the_port():
    assert issubclass(SqlPlanRepository, PlanRepository)


def test_a_day_nobody_planned_is_empty(store):
    assert store.day("2026-09-22").entries == []
    assert store.days() == []


def test_a_day_round_trips(store):
    store.put_day(day())
    assert store.day("2026-09-22") == day()
    assert store.days() == [day()]


def test_a_baseline_round_trips_including_an_empty_one(store):
    store.put_day(day(baseline=[("An", "TC.xlsx", "iPhone", 10)], at="2026-09-22T09:00:00"))
    assert store.day("2026-09-22").baseline == [PlanEntry("An", "TC.xlsx", "iPhone", 10)]
    store.put_day(day("2026-09-23", baseline=[], at="2026-09-23T09:00:00"))
    got = store.day("2026-09-23")
    assert got.baseline == [] and got.baseline_at == "2026-09-23T09:00:00"


def test_an_emptied_day_is_dropped_but_a_frozen_one_is_kept(db, store):
    store.put_day(day())
    store.put_day(day(entries=()))
    store.put_day(day("2026-09-23", entries=(), baseline=[("An", "TC.xlsx", "iPhone", 5)],
                      at="2026-09-23T09:00:00"))
    assert [d.date for d in store.days()] == ["2026-09-23"]


def test_days_come_back_in_date_order(store):
    store.put_day(day("2026-09-24"))
    store.put_day(day("2026-09-22"))
    assert [d.date for d in store.days()] == ["2026-09-22", "2026-09-24"]


def test_a_new_pic_joins_the_roster_and_the_phase(db, store):
    store.put_day(day(entries=(("Cy", "TC.xlsx", "iPhone", 3),)))
    assert store.members() == ["Cy"]
    assert [m.name for m in SqlPhaseRepository(db).members()] == ["Cy"]


def test_settings_are_the_active_phases(db, store):
    assert store.settings() == PlanSettings()
    store.put_settings(PlanSettings("2026-09-01", "2026-09-30", 40))
    phases = SqlPhaseRepository(db)
    assert phases.phase(phases.active_id()).settings == PlanSettings("2026-09-01", "2026-09-30", 40)


def test_each_phase_has_its_own_plan(db, store):
    phases = SqlPhaseRepository(db)
    first = phases.active_id()
    store.put_day(day())
    second = phases.create(Phase.from_dict({"name": "Sprint 2"}))
    phases.set_active(second.id)
    assert store.days() == []
    store.put_day(day(entries=(("Bo", "X.xlsx", "iPad", 2),)))
    phases.set_active(first)
    assert store.days() == [day()]
```

- [ ] **Step 3: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/infrastructure/test_db_phases.py tests/infrastructure/test_db_plans.py -q`
Expected: FAIL — `No module named 'tcm.infrastructure.db.phases'`

- [ ] **Step 4: Implement `tcm/infrastructure/db/phases.py`**

```python
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
                _set_members(conn, cur.lastrowid, phase.members)
                new_id = cur.lastrowid
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
        name = member_name(name)
        with self._db.connect() as conn:
            return Member(member_id(conn, name), name)

    def delete_member(self, member_id_: int) -> None:
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
```

- [ ] **Step 5: Implement `tcm/infrastructure/db/plans.py`**

```python
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
        """Save one day whole. A day with no rows and no baseline is not stored."""
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
        with self._db.connect() as conn:
            return [r["name"] for r in conn.execute(
                "SELECT m.name FROM phase_member pm JOIN member m ON m.id = pm.member_id "
                "WHERE pm.phase_id = ? ORDER BY m.name", (active_phase_id(conn),))]
```

Note: `baseline` entries may repeat a (pic, file, device) that is also in `entries`; the UNIQUE constraint includes `is_baseline`, so that is allowed.

- [ ] **Step 6: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/infrastructure/test_db_phases.py tests/infrastructure/test_db_plans.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
/usr/bin/git add tcm/infrastructure/db/phases.py tcm/infrastructure/db/plans.py tests/infrastructure/test_db_phases.py tests/infrastructure/test_db_plans.py
/usr/bin/git commit -m "Keep phases, the roster and the plan in the database" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Workspace snapshots and `compare_cases`

**Files:**
- Modify: `tcm/services/workspace.py`, `tcm/services/aggregation.py` (append `compare_cases`)
- Test: `tests/services/test_workspace.py` (append), `tests/services/test_compare.py` (new)

**Interfaces:**
- Consumes: `SnapshotRepository` (Task 2), `SqlSnapshotRepository` (Task 3, tests only).
- Produces:
  - `Workspace(loader, store, snapshots=None)`; `.origin`; `.state() -> dict` = `{loaded, file_count, file_results, source, origin}`; `.save_snapshot(label) -> (dict, int)`; `.snapshots() -> list`; `.open_snapshot(id) -> (dict, int)` (body = `state()`); `.delete_snapshot(id) -> (dict, int)`; `.restore_latest() -> bool`; `.compare(base_id, head_id) -> (dict, int)`.
  - `compare_cases(base, head) -> {"totals": {key: {base, head, delta}}, "total": {base, head, delta}, "rows": [{file, device, base: counts+total, head: counts+total, delta: counts+total}], "transitions": [{from, to, count}], "unchanged": int}`
  - compare body: `{"base": origin, "head": origin, **compare_cases(...)}`

- [ ] **Step 1: Write the failing workspace tests** — append to `tests/services/test_workspace.py`

```python
# --- snapshots ---------------------------------------------------------------

from tcm.infrastructure.db.bootstrap import open_database
from tcm.infrastructure.db.snapshots import SqlSnapshotRepository


@pytest.fixture
def snap_ws(tmp_path):
    folder = str(tmp_path)
    cases = [models.TestCase(file_name="A.xlsx", sheet="S", device="iPhone", row_num=1,
                             scope="FPT", result="OK")]
    files = [{"file": "A.xlsx", "path": folder + "/A.xlsx", "status": "ok"}]
    loader = FakeLoader(by_folder={os.path.abspath(folder): (cases, files)})
    repo = SqlSnapshotRepository(open_database(str(tmp_path / "db" / "tcm.db")))
    return Workspace(loader, InMemoryCaseStore(), repo), folder, loader


def test_saving_with_nothing_loaded_is_refused(snap_ws):
    ws, _, _ = snap_ws
    body, status = ws.save_snapshot("x")
    assert status == 400 and "Nothing is loaded" in body["error"]


def test_a_saved_snapshot_is_restored_by_a_fresh_workspace(snap_ws):
    ws, folder, loader = snap_ws
    ws.load_folder(folder)
    meta, status = ws.save_snapshot("day 1")
    assert status == 201 and meta["case_count"] == 1
    fresh = Workspace(loader, InMemoryCaseStore(), ws._snapshots)
    assert fresh.restore_latest() is True
    assert len(fresh.cases) == 1
    assert fresh.origin["id"] == meta["id"]
    assert fresh.state()["origin"]["label"] == "day 1"


def test_a_live_load_has_no_origin(snap_ws):
    ws, folder, _ = snap_ws
    ws.load_folder(folder)
    assert ws.origin is None and ws.state()["loaded"] == 1


def test_reload_after_opening_a_snapshot_goes_live(snap_ws):
    ws, folder, loader = snap_ws
    ws.load_folder(folder)
    sid = ws.save_snapshot("")[0]["id"]
    body, status = ws.open_snapshot(sid)
    assert status == 200 and body["origin"]["id"] == sid
    ws.reload()
    assert ws.origin is None
    assert loader.calls[-1] == ("folder", os.path.abspath(folder))


def test_unknown_snapshots_are_404(snap_ws):
    ws, _, _ = snap_ws
    assert ws.open_snapshot(99)[1] == 404
    assert ws.delete_snapshot(99)[1] == 404
    assert ws.compare(1, 99)[1] == 404


def test_without_a_snapshot_store_nothing_is_restored():
    ws = Workspace(FakeLoader(), InMemoryCaseStore())
    assert ws.restore_latest() is False
    assert ws.snapshots() == []
    assert ws.save_snapshot("")[1] == 400
```

- [ ] **Step 2: Write the failing compare tests** — `tests/services/test_compare.py`

```python
"""compare_cases: what changed between two loads."""
from tcm.domain.case import TestCase
from tcm.domain.status import STATUS
from tcm.services.aggregation import compare_cases


def case(row, result, scope="FPT", file="A.xlsx", device="iPhone", pic="An"):
    return TestCase(file_name=file, sheet="S", device=device, row_num=row,
                    scope=scope, result=result, pic=pic)


def key_of(result):
    return STATUS.classify_case(case(1, result))


def test_moves_are_counted_and_everything_is_accounted_for(fixed_scopes):
    base = [case(1, None), case(2, None), case(3, "OK")]
    head = [case(1, "OK"), case(2, None), case(4, "NG")]
    out = compare_cases(base, head)
    moves = {(t["from"], t["to"]): t["count"] for t in out["transitions"]}
    assert moves == {(key_of(None), key_of("OK")): 1,     # row 1 ran
                     (key_of("OK"), None): 1,             # row 3 removed
                     (None, key_of("NG")): 1}             # row 4 added
    assert out["unchanged"] == 1                          # row 2
    assert sum(moves.values()) + out["unchanged"] == 4    # rows 1-4, once each


def test_totals_and_rows_carry_deltas(fixed_scopes):
    out = compare_cases([case(1, None)], [case(1, "OK"), case(2, "OK", device="iPad")])
    ok = key_of("OK")
    assert out["totals"][ok] == {"base": 0, "head": 2, "delta": 2}
    assert out["total"]["delta"] == 1
    [ipad] = [r for r in out["rows"] if r["device"] == "iPad"]
    assert ipad["base"]["total"] == 0 and ipad["head"][ok] == 1 and ipad["delta"][ok] == 1


def test_work_outside_the_plan_is_not_compared(fixed_scopes):
    # JP is excluded in FIXED_SCOPES.
    out = compare_cases([case(1, None, scope="JP")], [case(1, "OK", scope="JP")])
    assert out["transitions"] == [] and out["rows"] == [] and out["total"]["head"] == 0
```

- [ ] **Step 3: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/services/test_workspace.py tests/services/test_compare.py -q`
Expected: FAIL — `Workspace() takes 3 positional arguments` / `cannot import name 'compare_cases'`

- [ ] **Step 4: Implement `compare_cases`** — append to `tcm/services/aggregation.py`

```python
def compare_cases(base, head):
    """What changed between two loads, classified with today's taxonomy.

    Both sides run through `in_plan`, so the figures are the ones Summary's
    Total would have shown for each. Cases are matched on (file, sheet, device,
    row): a case on one side only is added (`from: None`) or removed
    (`to: None`). Every matched key is either a transition or unchanged, so the
    two add up to every case either side holds.
    """
    base, head = in_plan(base), in_plan(head)

    def with_total(counts):
        return {**counts, "total": _counted_total(counts)}

    def diff(b, h):
        return {k: h[k] - b[k] for k in b}

    totals_b, totals_h = STATUS.zero_counts(), STATUS.zero_counts()
    per_row = defaultdict(lambda: (STATUS.zero_counts(), STATUS.zero_counts()))
    status_of = ({}, {})
    for side, cases, totals in ((0, base, totals_b), (1, head, totals_h)):
        for c in cases:
            key = STATUS.classify_case(c)
            totals[key] += 1
            per_row[(c.file_name, c.device)][side][key] += 1
            status_of[side][(c.file_name, c.sheet, c.device, c.row_num)] = key

    rows = []
    for (file_name, device), (b, h) in sorted(per_row.items()):
        b, h = with_total(b), with_total(h)
        rows.append({"file": file_name, "device": device,
                     "base": b, "head": h, "delta": diff(b, h)})

    moves, unchanged = Counter(), 0
    for key in status_of[0].keys() | status_of[1].keys():
        was, now = status_of[0].get(key), status_of[1].get(key)
        if was == now:
            unchanged += 1
        else:
            moves[(was, now)] += 1

    tb, th = _counted_total(totals_b), _counted_total(totals_h)
    return {
        "totals": {k: {"base": totals_b[k], "head": totals_h[k],
                       "delta": totals_h[k] - totals_b[k]} for k in STATUS.keys},
        "total": {"base": tb, "head": th, "delta": th - tb},
        "rows": rows,
        "transitions": [{"from": f, "to": t, "count": n} for (f, t), n in
                        sorted(moves.items(), key=lambda kv: (-kv[1], str(kv[0])))],
        "unchanged": unchanged,
    }
```

- [ ] **Step 5: Implement the workspace changes** in `tcm/services/workspace.py`

Change the imports and constructor, add the methods below, and set `origin=None` in `_remember`:

```python
from tcm.domain.ports import CaseLoader, CaseStore, Snapshot, SnapshotRepository
from tcm.services.aggregation import compare_cases

_NO_STORE = {"error": "Snapshots are not available: no database is configured."}


class Workspace:
    """One loaded source and its cases, and the snapshots kept of them."""

    def __init__(self, loader: CaseLoader, store: CaseStore,
                 snapshots: SnapshotRepository = None):
        self._loader = loader
        self._store = store
        self._snapshots = snapshots

    @property
    def origin(self):
        """None for a live load; the snapshot's `{id, taken_at, label}` otherwise."""
        return self._store.get().origin

    def state(self) -> dict:
        """What is loaded now, in the shape a load answers with, plus where it came from."""
        snap = self._store.get()
        return {"loaded": len(snap.cases), "file_count": len(snap.file_results),
                "file_results": snap.file_results, "source": snap.source,
                "origin": snap.origin}

    # --- snapshots -----------------------------------------------------------

    def save_snapshot(self, label: str = ""):
        if self._snapshots is None:
            return _NO_STORE, 400
        snap = self._store.get()
        if snap.source is None and not snap.file_results:
            return {"error": "Nothing is loaded — load test cases before saving a snapshot."}, 400
        return self._snapshots.save(snap, label), 201

    def snapshots(self) -> list:
        return self._snapshots.list() if self._snapshots else []

    def open_snapshot(self, snapshot_id: int):
        if self._snapshots is None:
            return _NO_STORE, 400
        snap = self._snapshots.load(snapshot_id)
        if snap is None:
            return {"error": f"No snapshot with id {snapshot_id}"}, 404
        self._store.put(snap)
        return self.state(), 200

    def delete_snapshot(self, snapshot_id: int):
        if self._snapshots is None:
            return _NO_STORE, 400
        if not self._snapshots.delete(snapshot_id):
            return {"error": f"No snapshot with id {snapshot_id}"}, 404
        return {"deleted": snapshot_id}, 200

    def restore_latest(self) -> bool:
        """Put the newest snapshot in the store. False when there is none."""
        if self._snapshots is None:
            return False
        sid = self._snapshots.latest_id()
        if sid is None:
            return False
        self._store.put(self._snapshots.load(sid))
        return True

    def compare(self, base_id: int, head_id: int):
        if self._snapshots is None:
            return _NO_STORE, 400
        base, head = self._snapshots.load(base_id), self._snapshots.load(head_id)
        missing = [i for i, s in ((base_id, base), (head_id, head)) if s is None]
        if missing:
            return {"error": f"No snapshot with id {missing[0]}"}, 404
        return {"base": base.origin, "head": head.origin,
                **compare_cases(base.cases, head.cases)}, 200
```

Keep the existing `cases` / `file_results` / `source` properties and loading methods unchanged. Update the module docstring with one paragraph: "A snapshot opened from the database goes into the same store a load does, with `origin` set; a load or reload clears it, which is what makes Reload the way back to live data."

- [ ] **Step 6: Run to verify they pass, then the whole suite**

Run: `.venv/bin/python -m pytest tests/services -q && .venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
/usr/bin/git add tcm/services/workspace.py tcm/services/aggregation.py tests/services/test_workspace.py tests/services/test_compare.py
/usr/bin/git commit -m "Save, open, restore and compare snapshots in the workspace" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: `PhaseService` and the board's roster

**Files:**
- Create: `tcm/services/phases.py`
- Modify: `tcm/services/planning.py:541-542` (members in `board_view`)
- Test: `tests/services/test_phases.py` (new), `tests/services/test_planning.py` (append)

**Interfaces:**
- Consumes: `SqlPhaseRepository` (tests), `Phase`, `member_name`, `NotFound` (Task 2), `_NO_PIC` (`tcm.services.planning`).
- Produces: `PhaseService(repo)` with `overview(cases) -> {"phases": [dict], "active_id": int, "members": [dict], "suggestions": [str]}`, `suggestions(cases) -> list[str]`, `create(raw) -> Phase`, `update(phase_id, raw) -> Phase`, `delete(phase_id)`, `activate(phase_id)`, `add_member(name, phase_id=None) -> Member`, `delete_member(member_id)`.

- [ ] **Step 1: Write the failing tests** — `tests/services/test_phases.py`

```python
"""The phase service: the rules above the repository."""
import pytest

from tcm.domain.case import TestCase
from tcm.infrastructure.db.bootstrap import open_database
from tcm.infrastructure.db.phases import SqlPhaseRepository
from tcm.services.phases import PhaseService


@pytest.fixture
def svc(tmp_path):
    return PhaseService(SqlPhaseRepository(open_database(str(tmp_path / "tcm.db"))))


def pic(name):
    return TestCase(file_name="A.xlsx", sheet="S", device="iPhone", row_num=1, pic=name)


def test_suggestions_are_pics_not_on_the_roster(svc):
    svc.add_member("An")
    cases = [pic("An"), pic(" Bo "), pic(""), pic(None), pic("N/A"), pic("Cy"), pic("Bo")]
    assert svc.suggestions(cases) == ["Bo", "Cy"]


def test_create_can_activate(svc):
    p = svc.create({"name": "Sprint 2", "activate": True})
    assert svc.overview([])["active_id"] == p.id
    q = svc.create({"name": "Sprint 3"})
    assert svc.overview([])["active_id"] == p.id != q.id


def test_add_member_can_join_a_phase(svc):
    active = svc.overview([])["active_id"]
    svc.add_member("An", phase_id=active)
    svc.add_member("An", phase_id=active)          # twice is still once
    [phase] = svc.overview([])["phases"]
    assert phase["members"] == ["An"]


def test_overview_shape(svc):
    o = svc.overview([pic("Zed")])
    assert set(o) == {"phases", "active_id", "members", "suggestions"}
    assert o["suggestions"] == ["Zed"] and o["members"] == []


def test_update_validates_before_writing(svc):
    pid = svc.overview([])["active_id"]
    with pytest.raises(ValueError):
        svc.update(pid, {"name": ""})
    assert svc.overview([])["phases"][0]["name"] == "Phase 1"
```

Append to `tests/services/test_planning.py`:

```python
# --- the board's members ---------------------------------------------------

def test_the_board_offers_the_roster_when_there_is_one():
    repo = FakePlanRepository({"2026-09-22": DayPlan.from_dict(
        "2026-09-22", {"entries": [entry(pic="Cy")]})})
    repo._members = ("An", "Bo")
    svc = PlanningService(repo, today=lambda: "2026-09-22")
    board = svc.board_view([case(pic="Zed", result="OK", test_date="2026-09-22")], "2026-09-22")
    # The roster, plus whoever the day's plan names -- not every PIC in the data.
    assert board["members"] == ["An", "Bo", "Cy"]


def test_without_a_roster_the_board_offers_everyone_as_before():
    svc = service()
    board = svc.board_view([case(pic="Zed", result="OK", test_date="2026-09-22")], "2026-09-22")
    assert board["members"] == ["Zed"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/services/test_phases.py tests/services/test_planning.py -q`
Expected: FAIL — `No module named 'tcm.services.phases'`; roster test fails with `['An', 'Bo', 'Cy', 'Zed']` or similar.

- [ ] **Step 3: Implement `tcm/services/phases.py`**

```python
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
        member = self._repo.add_member(member_name(name))
        if phase_id is not None:
            phase = self._repo.phase(phase_id)
            if member.name not in phase.members:
                self._repo.update(replace(phase, members=phase.members + (member.name,)))
        return member

    def delete_member(self, member_id: int) -> None:
        self._repo.delete_member(member_id)
```

- [ ] **Step 4: Change `board_view`'s members** in `tcm/services/planning.py` (the line `members = (facts.pics | {e.pic for _, e in facts.plans}) - {_NO_PIC}`):

```python
        # A phase with a roster offers the roster, plus anyone this day's plan
        # already names; without one, everyone the data or the plan knows of,
        # as before the roster existed.
        roster = set(self._repo.members())
        if roster:
            members = (roster | {e.pic for e in day.entries}) - {_NO_PIC}
        else:
            members = (facts.pics | {e.pic for _, e in facts.plans}) - {_NO_PIC}
```

- [ ] **Step 5: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/services -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
/usr/bin/git add tcm/services/phases.py tcm/services/planning.py tests/services/test_phases.py tests/services/test_planning.py
/usr/bin/git commit -m "Add the phase service and draw the board from the roster" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Web — wire the database, the new endpoints, delete the JSON store

**Files:**
- Create: `tcm/web/blueprints/snapshots.py`, `tcm/web/blueprints/phases.py`
- Modify: `tcm/web/app.py`, `tcm/web/blueprints/__init__.py`, `tcm/settings.py` (delete `PLAN_FILE` block), `tests/domain/test_ports.py`
- Delete: `tcm/infrastructure/plan/` (whole package), `tests/infrastructure/test_plan_store.py`
- Test: `tests/web/test_api_snapshots.py`, `tests/web/test_api_phases.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `create_app(workspace=None, identity=None, planning=None, phases=None, database=None)`; `phase_service()` blueprint helper; routes per the spec's tables. Every `/api/phases*` and `/api/members*` mutation answers with `PhaseService.overview(cases)` (201 on create).

- [ ] **Step 1: Write the failing API tests** — `tests/web/test_api_snapshots.py`

```python
"""`/api/workspace` and `/api/snapshots` — keeping a load, and starting on it."""
import pytest

import tcm.settings as app_settings
from tcm.web.app import create_app
from tests.conftest import config_row, write_workbook


def make_client():
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


@pytest.fixture
def source(tmp_path):
    folder = tmp_path / "src"
    folder.mkdir()
    write_workbook(folder / "TC.xlsx", [config_row("Login", "iPhone", 4, 5)], {"Login": {
        (4, "A"): "TC-1", (4, "B"): "FPT", (4, "C"): "OK", (4, "D"): "2026-08-05", (4, "E"): "lee",
        (5, "A"): "TC-2", (5, "B"): "FPT",
    }})
    return str(folder)


def test_nothing_loaded_and_nothing_saved(isolated_database):
    c = make_client()
    assert c.get("/api/workspace").get_json()["loaded"] == 0
    assert c.get("/api/snapshots").get_json() == {"snapshots": [], "origin": None}
    assert c.post("/api/snapshots", json={}).status_code == 400


def test_a_restart_starts_on_the_latest_snapshot(source):
    c = make_client()
    c.post("/api/load", json={"folder": source})
    saved = c.post("/api/snapshots", json={"label": "day 1"})
    assert saved.status_code == 201
    sid = saved.get_json()["id"]

    again = make_client()                         # same database file
    state = again.get("/api/workspace").get_json()
    assert state["loaded"] == 2 and state["origin"]["id"] == sid
    assert again.get("/api/summary").status_code == 200


def test_open_delete_and_compare(source):
    c = make_client()
    c.post("/api/load", json={"folder": source})
    a = c.post("/api/snapshots", json={"label": "a"}).get_json()["id"]
    b = c.post("/api/snapshots", json={"label": "b"}).get_json()["id"]

    opened = c.post(f"/api/snapshots/{a}/open")
    assert opened.status_code == 200 and opened.get_json()["origin"]["label"] == "a"

    cmp = c.get(f"/api/snapshots/compare?base={a}&head={b}").get_json()
    assert cmp["base"]["id"] == a and cmp["head"]["id"] == b
    assert cmp["transitions"] == [] and cmp["unchanged"] == 2

    assert c.get("/api/snapshots/compare?base=x").status_code == 400
    assert c.delete(f"/api/snapshots/{b}").status_code == 200
    assert c.get(f"/api/snapshots/compare?base={a}&head={b}").status_code == 404
    assert c.post(f"/api/snapshots/{b}/open").status_code == 404
    assert [s["label"] for s in c.get("/api/snapshots").get_json()["snapshots"]] == ["a"]


def test_a_label_must_be_text(source):
    c = make_client()
    c.post("/api/load", json={"folder": source})
    assert c.post("/api/snapshots", json={"label": 5}).status_code == 400
```

`tests/web/test_api_phases.py`:

```python
"""`/api/phases` and `/api/members`, and the plan following the active phase."""
import pytest

from tcm.web.app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def entry(pic="An", planned=5):
    return {"pic": pic, "file": "TC.xlsx", "device": "iPhone", "planned": planned}


def test_a_fresh_database_has_phase_1(client):
    body = client.get("/api/phases").get_json()
    assert [p["name"] for p in body["phases"]] == ["Phase 1"]
    assert body["active_id"] == body["phases"][0]["id"]


def test_create_update_activate_delete(client):
    res = client.post("/api/phases", json={"name": "Sprint 2", "members": ["An"]})
    assert res.status_code == 201
    new = [p for p in res.get_json()["phases"] if p["name"] == "Sprint 2"][0]

    res = client.put(f"/api/phases/{new['id']}", json={"name": "Sprint 2b", "daily_target": 9,
                                                       "members": ["An", "Bo"]})
    assert res.status_code == 200
    assert client.post(f"/api/phases/{new['id']}/activate").get_json()["active_id"] == new["id"]
    assert client.delete(f"/api/phases/{new['id']}").status_code == 200
    assert client.delete(f"/api/phases/{new['id']}").status_code == 404


def test_rules_come_back_as_400s(client):
    only = client.get("/api/phases").get_json()["active_id"]
    assert client.delete(f"/api/phases/{only}").status_code == 400
    assert client.post("/api/phases", json={"name": ""}).status_code == 400
    assert client.post("/api/phases", json={"name": "Phase 1"}).status_code == 400
    assert client.put("/api/phases/999", json={"name": "X"}).status_code == 404


def test_members(client):
    active = client.get("/api/phases").get_json()["active_id"]
    body = client.post("/api/members", json={"name": "An", "phase_id": active}).get_json()
    [an] = body["members"]
    assert body["phases"][0]["members"] == ["An"]
    client.put(f"/api/plan/2026-09-30", json={"entries": [entry("An")]})
    res = client.delete(f"/api/members/{an['id']}")
    assert res.status_code == 400 and "still planned" in res.get_json()["error"]
    assert client.delete("/api/members/999").status_code == 404
    assert client.post("/api/members", json={}).status_code == 400


def test_the_plan_follows_the_active_phase(client):
    first = client.get("/api/phases").get_json()["active_id"]
    client.put("/api/plan/2026-09-30", json={"entries": [entry(planned=7)]})
    client.put("/api/plan/settings", json={"phase_start": "2026-09-01",
                                           "phase_end": "2026-09-30", "daily_target": 11})
    body = client.post("/api/phases", json={"name": "Sprint 2", "activate": True}).get_json()
    assert body["active_id"] != first
    assert client.get("/api/plan/2026-09-30").get_json()["planned_total"] == 0
    client.post(f"/api/phases/{first}/activate")
    assert client.get("/api/plan/2026-09-30").get_json()["planned_total"] == 7
    [p1] = [p for p in client.get("/api/phases").get_json()["phases"] if p["id"] == first]
    assert (p1["phase_start"], p1["daily_target"]) == ("2026-09-01", 11)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/web/test_api_snapshots.py tests/web/test_api_phases.py -q`
Expected: FAIL — 404s for the new routes.

- [ ] **Step 3: Blueprint helper** — append to `tcm/web/blueprints/__init__.py`:

```python
def phase_service():
    """The PhaseService this app was built with.

    Not `phases()`: importing the `phases` blueprint module binds that name on
    this package, and would silently replace a helper called the same.
    """
    return current_app.extensions["phases"]
```

- [ ] **Step 4: `tcm/web/blueprints/snapshots.py`**

```python
"""Snapshots: keeping a load, opening it again, and comparing two.

`jsonify` wrappers around `Workspace`. `/api/workspace` lives here because it
exists for the snapshot a restart restores: the page asks it what is already
loaded before deciding whether to open on Tools.
"""
from flask import Blueprint, jsonify, request

from tcm.web.blueprints import workspace

bp = Blueprint("snapshots", __name__)


@bp.route("/api/workspace")
def get_workspace():
    """GET /api/workspace — what is loaded now, and whether it came from a snapshot."""
    return jsonify(workspace().state())


@bp.route("/api/snapshots")
def list_snapshots():
    """GET /api/snapshots — every snapshot, newest first, and the one on screen."""
    return jsonify({"snapshots": workspace().snapshots(), "origin": workspace().origin})


@bp.route("/api/snapshots", methods=["POST"])
def save_snapshot():
    """POST /api/snapshots — `{"label": "..."}`; keep what is loaded now."""
    label = (request.get_json(silent=True) or {}).get("label", "")
    if not isinstance(label, str):
        return jsonify({"error": "'label' must be text"}), 400
    result, status = workspace().save_snapshot(label)
    return jsonify(result), status


@bp.route("/api/snapshots/compare")
def compare_snapshots():
    """GET /api/snapshots/compare?base=<id>&head=<id> — what changed from base to head."""
    base = request.args.get("base", type=int)
    head = request.args.get("head", type=int)
    if base is None or head is None:
        return jsonify({"error": "Provide 'base' and 'head' snapshot ids"}), 400
    result, status = workspace().compare(base, head)
    return jsonify(result), status


@bp.route("/api/snapshots/<int:snapshot_id>/open", methods=["POST"])
def open_snapshot(snapshot_id):
    """POST /api/snapshots/<id>/open — put a snapshot on screen, as a load would."""
    result, status = workspace().open_snapshot(snapshot_id)
    return jsonify(result), status


@bp.route("/api/snapshots/<int:snapshot_id>", methods=["DELETE"])
def delete_snapshot(snapshot_id):
    """DELETE /api/snapshots/<id>."""
    result, status = workspace().delete_snapshot(snapshot_id)
    return jsonify(result), status
```

- [ ] **Step 5: `tcm/web/blueprints/phases.py`**

```python
"""Phases and the member roster.

Every write answers with the whole overview, so the card that made it redraws
from one response. A broken rule is the domain's ValueError, a 400 carrying its
message; an id nothing answers to is a 404.
"""
from flask import Blueprint, jsonify, request

from tcm.web.blueprints import phase_service, workspace

bp = Blueprint("phases", __name__)


def _overview(status=200):
    return jsonify(phase_service().overview(workspace().cases)), status


def _run(action, status=200):
    try:
        action()
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return _overview(status)


def _body():
    return request.get_json(silent=True) or {}


@bp.route("/api/phases")
def list_phases():
    """GET /api/phases — `{phases, active_id, members, suggestions}`."""
    return _overview()


@bp.route("/api/phases", methods=["POST"])
def create_phase():
    """POST /api/phases — `{name, phase_start?, phase_end?, daily_target?, members?, activate?}`."""
    return _run(lambda: phase_service().create(_body()), 201)


@bp.route("/api/phases/<int:phase_id>", methods=["PUT"])
def update_phase(phase_id):
    """PUT /api/phases/<id> — replace name, dates, target and members."""
    return _run(lambda: phase_service().update(phase_id, _body()))


@bp.route("/api/phases/<int:phase_id>", methods=["DELETE"])
def delete_phase(phase_id):
    """DELETE /api/phases/<id> — its plans go with it; the last phase stays."""
    return _run(lambda: phase_service().delete(phase_id))


@bp.route("/api/phases/<int:phase_id>/activate", methods=["POST"])
def activate_phase(phase_id):
    """POST /api/phases/<id>/activate — every plan figure now reads this phase."""
    return _run(lambda: phase_service().activate(phase_id))


@bp.route("/api/members", methods=["POST"])
def add_member():
    """POST /api/members — `{name, phase_id?}`; `phase_id` also puts them on that phase."""
    body = _body()
    return _run(lambda: phase_service().add_member(body.get("name"), body.get("phase_id")), 201)


@bp.route("/api/members/<int:member_id>", methods=["DELETE"])
def delete_member(member_id):
    """DELETE /api/members/<id> — refused while a plan row names them."""
    return _run(lambda: phase_service().delete_member(member_id))
```

- [ ] **Step 6: `tcm/web/app.py`** — replace the plan-file imports and wiring:

```python
from tcm.infrastructure.db.bootstrap import open_database
from tcm.infrastructure.db.phases import SqlPhaseRepository
from tcm.infrastructure.db.plans import SqlPlanRepository
from tcm.infrastructure.db.snapshots import SqlSnapshotRepository
from tcm.services.phases import PhaseService
from tcm.web.blueprints import analytics, pages, phases as phases_bp, plan, prepare, sharepoint, snapshots, source
```

(remove the `JsonPlanRepository` and `JsonFileConfigRepository` imports.)

```python
def create_app(workspace=None, identity=None, planning=None, phases=None, database=None):
    """Build the app.

    Args:
        workspace: A `Workspace`, or None to build the shipped one over the
            Excel reader, an in-memory store and the database's snapshots --
            and to start it on the newest snapshot.
        identity: An `IdentityService`, or None to build one over Graph.
        planning: A `PlanningService`, or None to build one over the database.
        phases: A `PhaseService`, or None to build one over the database.
        database: An open `Database`, or None to open `settings.DATABASE_FILE`
            when any of the three above needs it.

    All are arguments so a test can build an app over fakes without patching a
    module; nothing in the app changes them after construction.
    """
    app = Flask(...)  # unchanged

    if database is None and (workspace is None or planning is None or phases is None):
        # Opened here and nowhere else. A database that cannot be opened or
        # migrated stops the app, like a malformed shipped config: running on
        # without the plan would invite a save over it.
        database = open_database(settings.DATABASE_FILE)

    if workspace is None:
        workspace = Workspace(ExcelCaseLoader(), InMemoryCaseStore(),
                              SqlSnapshotRepository(database))
        workspace.restore_latest()
    app.extensions["workspace"] = workspace
    app.extensions["identity"] = identity or IdentityService(GraphAuth(...))  # unchanged
    app.extensions["planning"] = planning or PlanningService(SqlPlanRepository(database))
    app.extensions["phases"] = phases or PhaseService(SqlPhaseRepository(database))

    for module in (source, snapshots, analytics, plan, phases_bp, prepare, settings_bp,
                   sharepoint, pages):
        app.register_blueprint(module.bp)
    return app
```

- [ ] **Step 7: Delete the JSON store**

```bash
/usr/bin/git rm -r -q tcm/infrastructure/plan tests/infrastructure/test_plan_store.py
```

Delete the `PLAN_FILE` block (comment + assignment) from `tcm/settings.py`. In `tests/domain/test_ports.py` replace the last test with:

```python
def test_the_sql_repositories_answer_their_ports():
    from tcm.infrastructure.db.phases import SqlPhaseRepository
    from tcm.infrastructure.db.plans import SqlPlanRepository
    from tcm.infrastructure.db.snapshots import SqlSnapshotRepository
    assert issubclass(SqlPlanRepository, ports.PlanRepository)
    assert issubclass(SqlPhaseRepository, ports.PhaseRepository)
    assert issubclass(SqlSnapshotRepository, ports.SnapshotRepository)
```

Check nothing else names the removed code: `grep -rn "PLAN_FILE\|json_store\|JsonPlanRepository" tcm tests` → no output.

- [ ] **Step 8: Run everything**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
/usr/bin/git add -A tcm tests
/usr/bin/git commit -m "Serve snapshots and phases, and keep the plan in the database" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Front end — API helpers, Snapshots card, rail origin, startup restore

**Files:**
- Modify: `static/js/api.js` (append), `static/js/dom.js` (append `formatStamp`), `static/js/shell.js` (`setSourceSummary`), `templates/index.html` (rail line), `templates/views/tools.html` (new card), `static/js/main.js`, `static/css/views.css` (append)
- Create: `static/js/snapshotPanel.js`

**Interfaces:**
- Consumes: Task 7 endpoints.
- Produces (api.js): `getWorkspace()`, `getSnapshots()`, `postSnapshot(label)`, `postOpenSnapshot(id)`, `deleteSnapshot(id)`, `getSnapshotCompare(base, head)`, `getPhases()`, `postPhase(body)`, `putPhase(id, body)`, `deletePhase(id)`, `postActivatePhase(id)`, `postMember(name, phaseId)`, `deleteMember(id)` — each `Promise<{ok, json}>`. (dom.js) `formatStamp(iso) -> string`. (snapshotPanel.js) `initSnapshotPanel({onOpened, onCompare})`, `refreshSnapshots()`, `setSnapshotSaveEnabled(on)`.

- [ ] **Step 1: api.js helpers** — append, following the file's JSDoc style:

```js
/** A JSON request helper for the endpoints below; never throws on a 4xx. */
async function call(url, method = "GET", body) {
    const init = { method };
    if (body !== undefined) {
        init.headers = { "Content-Type": "application/json" };
        init.body = JSON.stringify(body);
    }
    const res = await fetch(url, init);
    return { ok: res.ok, json: await res.json() };
}

/**
 * What is loaded now — including a snapshot the server restored at startup.
 * @returns {Promise<ApiResponse>} `{loaded, file_count, file_results, source, origin}`.
 */
export const getWorkspace = () => call("/api/workspace");

/** @returns {Promise<ApiResponse>} `{snapshots: [{id, taken_at, label, source, case_count, file_count}], origin}`. */
export const getSnapshots = () => call("/api/snapshots");

/** Keep what is loaded now. @param {string} label */
export const postSnapshot = (label) => call("/api/snapshots", "POST", { label });

/** Put a snapshot on screen. Answers like {@link getWorkspace}. @param {number} id */
export const postOpenSnapshot = (id) => call(`/api/snapshots/${id}/open`, "POST");

/** @param {number} id */
export const deleteSnapshot = (id) => call(`/api/snapshots/${id}`, "DELETE");

/**
 * What changed from `base` to `head`.
 * @returns {Promise<ApiResponse>} `{base, head, totals, total, rows, transitions, unchanged}`.
 */
export const getSnapshotCompare = (base, head) =>
    call(`/api/snapshots/compare?base=${encodeURIComponent(base)}&head=${encodeURIComponent(head)}`);

/** @returns {Promise<ApiResponse>} `{phases, active_id, members, suggestions}`; every write below answers the same. */
export const getPhases = () => call("/api/phases");
export const postPhase = (body) => call("/api/phases", "POST", body);
export const putPhase = (id, body) => call(`/api/phases/${id}`, "PUT", body);
export const deletePhase = (id) => call(`/api/phases/${id}`, "DELETE");
export const postActivatePhase = (id) => call(`/api/phases/${id}/activate`, "POST");
/** @param {string} name @param {?number} phaseId also put them on this phase */
export const postMember = (name, phaseId = null) =>
    call("/api/members", "POST", { name, phase_id: phaseId });
export const deleteMember = (id) => call(`/api/members/${id}`, "DELETE");
```

- [ ] **Step 2: `formatStamp`** — append to `static/js/dom.js`:

```js
/**
 * An ISO timestamp as "27 Sep 2026 14:02", the way snapshots are named on screen.
 * @param {?string} iso
 * @returns {string}
 */
export function formatStamp(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    const date = d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
    const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
    return `${date} ${time}`;
}
```

- [ ] **Step 3: Rail line** — in `templates/index.html`, inside the first `.rail-card` of `#sourceCard`, after `#sourceSummary`:

```html
                    <span class="rail-sub" id="sourceOrigin"></span>
```

In `static/js/shell.js` import `formatStamp` (`import { $, $$, formatStamp } from "./dom.js";` — keep whatever it already imports) and extend `setSourceSummary`, updating its JSDoc to mention `origin`:

```js
    const o = json.origin;
    $("#sourceOrigin").textContent = o
        ? `Snapshot · ${formatStamp(o.taken_at)}${o.label ? ` · ${o.label}` : ""}`
        : "Live";
```

- [ ] **Step 4: Tools card** — in `templates/views/tools.html`, between the source card and the report card:

```html
            <!-- Snapshots: what was loaded, kept with the time it was kept. The
                 app starts on the newest one. Nothing here writes to a workbook;
                 `snapshotPanel.js` owns it and knows nothing about the views. -->
            <section class="card" id="snapshotSection">
                <div class="card-head">
                    <h2>Snapshots</h2>
                    <p>A snapshot keeps what is loaded now, so it can be opened or compared
                       later. The app starts on the newest one. Reload returns to live data.</p>
                </div>
                <div class="stack">
                    <div class="row">
                        <div class="field" style="flex:1">
                            <label for="snapshotLabel">Label (optional)</label>
                            <input type="text" id="snapshotLabel" class="input" maxlength="120"
                                   placeholder="End of day 3">
                        </div>
                        <button id="btnSnapshotSave" type="button" class="btn" disabled
                                title="Load test cases first">Save snapshot</button>
                    </div>
                    <div class="status-line" id="snapshotStatus"></div>
                    <p class="empty-note" id="snapshotEmpty">No snapshots yet.</p>
                    <div class="scroll-x scroll-x--rows" id="snapshotTableWrap" hidden>
                        <table class="ledger">
                            <thead><tr>
                                <th>Taken</th><th>Label</th><th class="num">Files</th>
                                <th class="num">Cases</th><th>Actions</th>
                            </tr></thead>
                            <tbody id="snapshotBody"></tbody>
                        </table>
                    </div>
                    <div class="row" id="snapshotCompareRow" hidden>
                        <div class="field">
                            <label for="snapshotBase">Compare</label>
                            <select id="snapshotBase" class="select"></select>
                        </div>
                        <div class="field">
                            <label for="snapshotHead">with</label>
                            <select id="snapshotHead" class="select"></select>
                        </div>
                        <button id="btnSnapshotCompare" type="button" class="btn">Compare</button>
                    </div>
                </div>
            </section>
```

- [ ] **Step 5: `static/js/snapshotPanel.js`**

```js
/**
 * Tools → Snapshots: keep what is loaded, open it again, compare two.
 *
 * A panel in the mould of `sourcePanel.js`: it owns its card and knows nothing
 * about the views. Opening one and comparing two are reported back through the
 * hooks `main.js` installs, because redrawing the app and changing view are
 * `main.js`'s business. Rows address a snapshot by index into `list`, never
 * through an attribute.
 */
import { $, esc, formatStamp } from "./dom.js";
import { deleteSnapshot, getSnapshots, postOpenSnapshot, postSnapshot } from "./api.js";

/** @type {Array<{id:number, taken_at:string, label:string, case_count:number, file_count:number}>} newest first */
let list = [];
/** @type {?{id:number}} the snapshot on screen, or null for live data */
let origin = null;
let hooks = { onOpened: () => {}, onCompare: () => {} };

const status = (text, isError = false) => {
    const el = $("#snapshotStatus");
    el.textContent = text;
    el.classList.toggle("is-error", isError);
};

const nameOf = (s) => `${formatStamp(s.taken_at)}${s.label ? ` · ${s.label}` : ""}`;

function render() {
    $("#snapshotEmpty").hidden = list.length > 0;
    $("#snapshotTableWrap").hidden = list.length === 0;
    $("#snapshotBody").innerHTML = list.map((s, i) => `
        <tr${origin && origin.id === s.id ? ' class="is-current"' : ""}>
            <td class="mono">${esc(formatStamp(s.taken_at))}</td>
            <td>${esc(s.label)}${origin && origin.id === s.id ? ' <span class="chip">On screen</span>' : ""}</td>
            <td class="num">${s.file_count.toLocaleString()}</td>
            <td class="num">${s.case_count.toLocaleString()}</td>
            <td class="actions">
                <button type="button" class="btn btn-sm" data-act="open" data-index="${i}">Open</button>
                <button type="button" class="btn btn-sm btn-quiet" data-act="delete" data-index="${i}">Delete</button>
            </td>
        </tr>`).join("");

    const options = list.map((s, i) => `<option value="${i}">${esc(nameOf(s))}</option>`).join("");
    $("#snapshotCompareRow").hidden = list.length < 2;
    $("#snapshotBase").innerHTML = options;
    $("#snapshotHead").innerHTML = options;
    // Oldest-but-one against newest is the usual question: "since last time".
    if (list.length >= 2) {
        $("#snapshotBase").value = "1";
        $("#snapshotHead").value = "0";
    }
}

/** Re-read the history and redraw. Call after anything that changes it. */
export async function refreshSnapshots() {
    const { ok, json } = await getSnapshots();
    if (!ok) { status(json.error || "Could not read the snapshots.", true); return; }
    list = json.snapshots;
    origin = json.origin;
    render();
}

/** Saving needs something loaded. */
export function setSnapshotSaveEnabled(on) {
    const btn = $("#btnSnapshotSave");
    btn.disabled = !on;
    btn.title = on ? "" : "Load test cases first";
}

/**
 * Wire the card. Call once, at startup.
 * @param {{onOpened: (state: Object) => void, onCompare: (base: number, head: number) => void}} opts
 */
export function initSnapshotPanel(opts) {
    hooks = { ...hooks, ...opts };

    $("#btnSnapshotSave").addEventListener("click", async () => {
        const { ok, json } = await postSnapshot($("#snapshotLabel").value);
        if (!ok) { status(json.error, true); return; }
        $("#snapshotLabel").value = "";
        status(`Saved ${json.case_count.toLocaleString()} cases as ${nameOf(json)}.`);
        await refreshSnapshots();
    });

    $("#snapshotBody").addEventListener("click", async (ev) => {
        const btn = ev.target.closest("[data-act]");
        if (!btn) return;
        const s = list[Number(btn.dataset.index)];
        if (!s) return;
        if (btn.dataset.act === "open") {
            const { ok, json } = await postOpenSnapshot(s.id);
            if (!ok) { status(json.error, true); return; }
            status(`Opened ${nameOf(s)}.`);
            await hooks.onOpened(json);
            await refreshSnapshots();
        } else if (btn.dataset.act === "delete") {
            if (!window.confirm(`Delete the snapshot ${nameOf(s)}? This cannot be undone.`)) return;
            const { ok, json } = await deleteSnapshot(s.id);
            if (!ok) { status(json.error, true); return; }
            status(`Deleted ${nameOf(s)}.`);
            await refreshSnapshots();
        }
    });

    $("#btnSnapshotCompare").addEventListener("click", () => {
        const base = list[Number($("#snapshotBase").value)];
        const head = list[Number($("#snapshotHead").value)];
        if (!base || !head) return;
        if (base.id === head.id) { status("Pick two different snapshots to compare.", true); return; }
        hooks.onCompare(base.id, head.id);
    });

    refreshSnapshots();
}
```

- [ ] **Step 6: main.js wiring**

- Import: `import { getWorkspace } from "./api.js";` (merge into the existing api import) and `import { initSnapshotPanel, refreshSnapshots, setSnapshotSaveEnabled } from "./snapshotPanel.js";`
- In `refreshViews`, after `setReportEnabled(true);` add:

```js
    // There is something to keep now, and the history's "on screen" marker
    // may have moved — a load goes live, an open names a snapshot.
    setSnapshotSaveEnabled(true);
    await refreshSnapshots();
```

- After `initPreparePanel(...)` add:

```js
// Opening a snapshot is a load by another name: redraw everything, and stay on
// Tools, where the reader pressed Open. Comparing is navigation, so it comes
// back here like a file name does (`openCompare` is added in Task 9; until then
// pass `() => {}`).
initSnapshotPanel({
    onOpened: (state) => refreshViews(state, { show: false }),
    onCompare: (base, head) => openCompare(base, head),
});
```

- Replace the final `showView("tools");` and its comment with:

```js
/**
 * Open on whatever the server already holds.
 *
 * The server starts on the newest snapshot, so a restart lands on the data the
 * reader last kept rather than on an empty app. With nothing kept it is Tools,
 * the empty state, as before.
 */
async function start() {
    const { ok, json } = await getWorkspace();
    if (ok && json.loaded) await refreshViews(json);
    else showView("tools");
}
start();
```

- [ ] **Step 7: CSS** — append to the end of `static/css/views.css`, under a new section comment:

```css
/* --- snapshots ---------------------------------------------------------------
   The Tools card's table: the row on screen is marked with ink, never a hue. */
.ledger tr.is-current td { background: var(--paper-sunk, var(--surface-2)); }
.ledger td.actions { white-space: nowrap; }
```

Before writing, check `static/css/tokens.css` for the sunk-surface token actually defined (`grep -n "sunk\|surface" static/css/tokens.css`) and use it directly instead of the fallback chain. Check `.chip` and `.btn-sm` exist (`grep -n "\.chip\b\|\.btn-sm" static/css/*.css`); if `.btn-sm` does not exist, drop that class from the markup rather than inventing a size.

- [ ] **Step 8: Verify**

Run: `.venv/bin/python -m pytest -q` → PASS (test_app's stylesheet order and template tests still hold).
Syntax-check the new/changed modules: `for f in static/js/snapshotPanel.js static/js/main.js static/js/api.js static/js/dom.js static/js/shell.js; do cp $f /tmp/claude-check.mjs && node --check /tmp/claude-check.mjs || echo "FAIL $f"; done` (use the scratchpad dir instead of /tmp).
Run the app (`TCM_DATABASE=<scratchpad>/tcm.db .venv/bin/python app.py`), load `samples/`, save a snapshot, restart the server, reload the page → it opens on Summary with the rail saying *Snapshot · … *. Press Reload in Tools → rail says *Live*.

- [ ] **Step 9: Commit**

```bash
/usr/bin/git add static templates
/usr/bin/git commit -m "Add the Snapshots card and start the page on the restored snapshot" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Front end — Compare view

**Files:**
- Create: `static/js/views/compare.js`, `templates/views/compare.html`
- Modify: `templates/index.html` (include after `views/file.html`), `static/js/main.js` (`VIEWS.compare`, `openCompare`), `static/css/views.css` (append)

**Interfaces:**
- Consumes: `getSnapshotCompare` (Task 8), `getStatuses` from `static/js/api.js` (the `/api/statuses` fetch — confirm its name with `grep -n "api/statuses" static/js/api.js`), `setTaxonomy`, `getStatuses`, `getCountedStatuses`, `toneFor` from `taxonomy.js`, `formatStamp`.
- Produces: `initCompareView({onBack})`, `showCompare(json, {backTo})`.

- [ ] **Step 1: Template** — `templates/views/compare.html`

```html
        <!-- ==================== Compare ====================
             Two snapshots side by side: the drill-in behind Tools' Compare
             button. Like File it has no nav item and draws its own Back. Both
             sides are classified with the taxonomy as it is now, over the scope
             groups in the plan. Filled by views/compare.js. -->
        <section class="view" id="compareView" hidden>
            <div class="file-bar">
                <button class="btn btn-quiet" id="btnCompareBack">&lsaquo; Back</button>
                <span class="compare-sides" id="compareSides"></span>
            </div>

            <section class="card card--table">
                <div class="card-head card-head--row"><h2>Totals</h2></div>
                <div class="scroll-x"><table class="ledger" id="compareTotals"></table></div>
            </section>

            <section class="card card--table">
                <div class="card-head card-head--row">
                    <h2>What moved</h2>
                    <span class="card-note" id="compareUnchanged"></span>
                </div>
                <div class="scroll-x scroll-x--rows"><table class="ledger" id="compareMoves"></table></div>
            </section>

            <section class="card card--table">
                <div class="card-head card-head--row"><h2>By file and device</h2></div>
                <div class="scroll-x scroll-x--rows"><table class="ledger" id="compareRows"></table></div>
            </section>
        </section>
```

Add `{% include "views/compare.html" %}` at column 0 after the `views/file.html` include in `templates/index.html`.

- [ ] **Step 2: `static/js/views/compare.js`**

```js
/**
 * Compare view: what changed between two snapshots.
 *
 * A drill-in like File: no nav item, a Back button, and `main.js` owns getting
 * here. Every figure is the server's (`compare_cases`); this module arranges
 * them. A delta carries no colour of its own — colour means status, so the
 * status names keep their tones and the numbers are ink with a sign.
 */
import { $, esc, formatStamp } from "../dom.js";
import { getCountedStatuses, getStatuses, toneFor } from "../taxonomy.js";

const num = (n) => Number(n || 0).toLocaleString();
const signed = (n) => (n > 0 ? `+${num(n)}` : n < 0 ? `−${num(-n)}` : "0");
const nameOf = (o) => (o ? `${formatStamp(o.taken_at)}${o.label ? ` · ${o.label}` : ""}` : "");

function badge(key) {
    if (key == null) return '<span class="muted">—</span>';
    const s = getStatuses().find((x) => x.key === key);
    return `<span class="badge" data-tone="${esc(toneFor(key))}">${esc(s ? s.label : key)}</span>`;
}

function renderTotals(json) {
    const statuses = getStatuses();
    const head = `<thead><tr><th></th>${statuses.map((s) =>
        `<th class="num">${badge(s.key)}</th>`).join("")}<th class="num">Total</th></tr></thead>`;
    const line = (label, pick, fmt = num) => `<tr><th scope="row">${label}</th>${statuses.map((s) =>
        `<td class="num">${fmt(pick(json.totals[s.key]))}</td>`).join("")}
        <td class="num">${fmt(pick(json.total))}</td></tr>`;
    $("#compareTotals").innerHTML = head + "<tbody>"
        + line("Base", (t) => t.base) + line("Head", (t) => t.head)
        + line("Change", (t) => t.delta, signed) + "</tbody>";
}

function renderMoves(json) {
    $("#compareUnchanged").textContent = `${num(json.unchanged)} cases unchanged`;
    $("#compareMoves").innerHTML = `<thead><tr><th>From</th><th>To</th><th class="num">Cases</th></tr></thead>
        <tbody>${json.transitions.length ? json.transitions.map((t) => `<tr>
            <td>${t.from == null ? '<span class="muted">Added</span>' : badge(t.from)}</td>
            <td>${t.to == null ? '<span class="muted">Removed</span>' : badge(t.to)}</td>
            <td class="num">${num(t.count)}</td></tr>`).join("")
        : '<tr><td colspan="3" class="empty-note">Nothing moved.</td></tr>'}</tbody>`;
}

function renderRows(json) {
    const counted = getCountedStatuses();
    // Rows where nothing changed are noise here; the totals already count them.
    const rows = json.rows.filter((r) => Object.values(r.delta).some((d) => d !== 0));
    $("#compareRows").innerHTML = `<thead><tr><th>File</th><th>Device</th>
        <th class="num">Base</th><th class="num">Head</th><th class="num">Change</th>
        ${counted.map((s) => `<th class="num">${badge(s.key)}</th>`).join("")}</tr></thead>
        <tbody>${rows.length ? rows.map((r) => `<tr>
            <td>${esc(r.file)}</td><td>${esc(r.device)}</td>
            <td class="num">${num(r.base.total)}</td><td class="num">${num(r.head.total)}</td>
            <td class="num">${signed(r.delta.total)}</td>
            ${counted.map((s) => `<td class="num">${r.delta[s.key] ? signed(r.delta[s.key]) : ""}</td>`).join("")}
        </tr>`).join("")
        : `<tr><td colspan="${5 + counted.length}" class="empty-note">No file changed.</td></tr>`}</tbody>`;
}

/**
 * Draw one comparison.
 * @param {Object} json `/api/snapshots/compare`'s answer.
 * @param {{backTo: string}} opts The view Back returns to, for its label.
 */
export function showCompare(json, { backTo }) {
    $("#btnCompareBack").textContent = `‹ ${backTo}`;
    $("#compareSides").textContent = `${nameOf(json.base)} → ${nameOf(json.head)}`;
    renderTotals(json);
    renderMoves(json);
    renderRows(json);
}

/** Wire the Back button. Call once, at startup. @param {{onBack: () => void}} opts */
export function initCompareView({ onBack }) {
    $("#btnCompareBack").addEventListener("click", onBack);
}
```

Confirm `getCountedStatuses` returns `Status[]` objects with `.key` (`sed -n 170,200p static/js/taxonomy.js`); if it returns keys, map accordingly.

- [ ] **Step 3: main.js**

Add to `VIEWS` after `file`:

```js
    compare: {
        // A drill-in like File, reached from Tools' Snapshots card.
        title: "Compare",
        sub: () => "What changed between two snapshots. Both are classified with the "
                 + "taxonomy as it is now, over the scope groups in the plan.",
    },
```

Imports: `getSnapshotCompare` and the `/api/statuses` helper (aliased, e.g. `getStatuses as fetchStatuses`) from `./api.js`; `initCompareView, showCompare` from `./views/compare.js`. Add:

```js
/**
 * Open the Compare view on two snapshots.
 *
 * The taxonomy is only set by a load, and comparing needs none — so it is
 * fetched here when nothing has set it yet, or the view would have no columns.
 */
async function openCompare(base, head) {
    const { ok, json } = await getSnapshotCompare(base, head);
    if (!ok) return;
    if (!getStatuses().length) {
        const t = await fetchStatuses();
        if (t.ok) setTaxonomy(t.json);
    }
    showCompare(json, { backTo: titleOf("tools") });
    showView("compare");
}
```

(`getStatuses` here is taxonomy.js's; import it alongside `setTaxonomy`. Check what `fetchAll` passes to `setTaxonomy` — if it is `/api/statuses`' body unchanged, pass `t.json` as above; otherwise mirror what `fetchAll` does.)

Wire: `initCompareView({ onBack: () => showView("tools") });` next to `initFileView(...)`, and make sure `initSnapshotPanel`'s `onCompare` calls `openCompare`.

- [ ] **Step 4: CSS** — append to the snapshots section in `static/css/views.css`:

```css
.compare-sides { font-family: var(--font-mono); color: var(--ink-2, inherit); margin-left: var(--s-3, 12px); }
```

(check `tokens.css` for the secondary-ink and spacing token names and use the real ones.)

- [ ] **Step 5: Verify**

Run: `.venv/bin/python -m pytest -q` → PASS. Syntax-check `static/js/views/compare.js` and `static/js/main.js` as in Task 8. In the running app: save two snapshots with a result edited in a workbook between them (or clear results via Tools between them), press Compare → totals, moves and file rows are drawn; Back returns to Tools.

- [ ] **Step 6: Commit**

```bash
/usr/bin/git add static templates
/usr/bin/git commit -m "Add the Compare view for two snapshots" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Front end — phase select and the Phases & members card

**Files:**
- Create: `static/js/views/planning/phases.js`
- Modify: `templates/views/planning.html`, `static/js/views/planning/state.js` (`data.phases`), `static/js/views/planning/render.js` (`renderPhase` select), `static/js/views/planning/index.js`, `static/css/views.css` (append)

**Interfaces:**
- Consumes: `getPhases`, `postPhase`, `putPhase`, `deletePhase`, `postActivatePhase`, `postMember`, `deleteMember` (Task 8); `getPlanCalendar`, `setPlanCalendar` (existing).
- Produces: `phases.js` exports `renderPhases()` and `bindPhases({onChanged})`; `index.js` gains `loadPhases()` and `afterPlanChange()`.

- [ ] **Step 1: State** — in `static/js/views/planning/state.js`, extend `data`:

```js
/** The last responses: `phase` from /api/plan/phase, `board` from /api/plan/board/<date>,
 *  `phases` from /api/phases. */
export const data = { phase: null, board: null, phases: null };
```

- [ ] **Step 2: Template** — in `templates/views/planning.html`, after `#planGrid`'s section and before `#planTip`:

```html
            <!-- Phases and who is in them. The active phase is the one every
                 plan figure in the app reads. Filled by views/planning/phases.js. -->
            <section class="card" id="planPhases">
                <div class="card-head card-head--row"><h2>Phases &amp; members</h2></div>
                <p class="empty-note is-error" id="planPhasesError" hidden></p>
                <div class="scroll-x"><table class="ledger" id="planPhaseTable"></table></div>
                <div class="row plan-phase-new">
                    <input type="text" class="input" id="planNewPhaseName" placeholder="New phase name">
                    <button type="button" class="btn" data-act="create-phase">Add phase</button>
                </div>
                <h3 class="plan-members-head" id="planMembersHead">Members</h3>
                <div class="checks" id="planMembers"></div>
                <div class="row">
                    <input type="text" class="input" id="planNewMember" placeholder="Add a member by name">
                    <button type="button" class="btn" data-act="add-member">Add</button>
                </div>
                <div class="plan-suggestions" id="planSuggestions"></div>
            </section>
```

- [ ] **Step 3: `static/js/views/planning/phases.js`**

```js
/**
 * The Phases & members card: which phases exist, which is active, who is in it.
 *
 * Writes its own DOM, like `editor.js`, and is imported only by `index.js`.
 * Every write answers with the whole overview, which this adopts and redraws;
 * anything that changes what the planner reads (switching or editing the active
 * phase) is reported through `onChanged`, because reloading the planner, Daily
 * and Productivity is `index.js`'s job. Rows address a phase or member by index
 * into `data.phases`, never through an attribute holding a name.
 */
import { $, esc } from "../../dom.js";
import {
    deleteMember, deletePhase, postActivatePhase, postMember, postPhase, putPhase,
} from "../../api.js";
import { data } from "./state.js";

let hooks = { onChanged: async () => {} };

const active = () => data.phases.phases.find((p) => p.id === data.phases.active_id);

function error(text) {
    const el = $("#planPhasesError");
    el.textContent = text || "";
    el.hidden = !text;
}

/** Adopt a write's answer. `changed` says the planner's figures moved. */
async function adopt(res, changed) {
    if (!res.ok) { error(res.json.error); renderPhases(); return; }
    error("");
    data.phases = res.json;
    renderPhases();
    if (changed) await hooks.onChanged();
}

export function renderPhases() {
    const o = data.phases;
    if (!o) return;
    $("#planPhaseTable").innerHTML = `<thead><tr>
            <th>Name</th><th>Start</th><th>End</th><th class="num">Target</th>
            <th class="num">Members</th><th></th></tr></thead>
        <tbody>${o.phases.map((p, i) => `<tr data-index="${i}"${p.id === o.active_id ? ' class="is-current"' : ""}>
            <td><input class="input" data-field="name" value="${esc(p.name)}" aria-label="Phase name"></td>
            <td><input type="date" class="input input-mono" data-field="phase_start" value="${esc(p.phase_start || "")}" aria-label="Start"></td>
            <td><input type="date" class="input input-mono" data-field="phase_end" value="${esc(p.phase_end || "")}" aria-label="End"></td>
            <td class="num"><input type="number" min="1" class="input input-mono" data-field="daily_target" value="${esc(p.daily_target)}" aria-label="Target per member per day"></td>
            <td class="num">${p.members.length}</td>
            <td class="actions">
                ${p.id === o.active_id ? '<span class="chip">Active</span>'
                  : '<button type="button" class="btn" data-act="activate">Make active</button>'}
                <button type="button" class="btn btn-quiet" data-act="delete-phase"
                        ${o.phases.length === 1 ? "disabled title=\"The last phase cannot be deleted\"" : ""}>Delete</button>
            </td></tr>`).join("")}</tbody>`;

    const a = active();
    $("#planMembersHead").textContent = a ? `Members of ${a.name}` : "Members";
    const inPhase = new Set(a ? a.members : []);
    $("#planMembers").innerHTML = o.members.length ? o.members.map((m, i) => `
        <label class="check">
            <input type="checkbox" data-member="${i}"${inPhase.has(m.name) ? " checked" : ""}>
            <span>${esc(m.name)}</span>
            <button type="button" class="btn btn-quiet" data-act="delete-member" data-member="${i}"
                    aria-label="Remove ${esc(m.name)} from the roster">×</button>
        </label>`).join("")
        : '<p class="empty-note">Nobody on the roster yet. Add people below, or from the names found in the data.</p>';

    $("#planSuggestions").innerHTML = o.suggestions.length ? `
        <span class="label">Found in the data</span>
        ${o.suggestions.map((n, i) => `<button type="button" class="btn" data-act="suggest" data-suggest="${i}">+ ${esc(n)}</button>`).join("")}
        <button type="button" class="btn btn-quiet" data-act="suggest-all">Add all</button>` : "";
}

function phaseBody(row) {
    const p = data.phases.phases[Number(row.dataset.index)];
    const field = (f) => row.querySelector(`[data-field="${f}"]`).value;
    return [p, {
        name: field("name"),
        phase_start: field("phase_start") || null,
        phase_end: field("phase_end") || null,
        daily_target: Number(field("daily_target")),
        members: p.members,
    }];
}

/** Wire the card. Call once. @param {{onChanged: () => Promise<void>}} opts */
export function bindPhases(opts) {
    hooks = { ...hooks, ...opts };
    const card = $("#planPhases");

    // Editing a phase row saves on change, the way the phase bar does.
    card.addEventListener("change", async (ev) => {
        const row = ev.target.closest("#planPhaseTable tr[data-index]");
        if (row && ev.target.dataset.field) {
            const [p, body] = phaseBody(row);
            await adopt(await putPhase(p.id, body), p.id === data.phases.active_id);
            return;
        }
        const box = ev.target.closest("input[data-member]");
        if (box) {
            const a = active();
            const name = data.phases.members[Number(box.dataset.member)].name;
            const members = box.checked ? [...a.members, name] : a.members.filter((n) => n !== name);
            const { id, created_at, ...rest } = a;
            await adopt(await putPhase(id, { ...rest, members }), true);
        }
    });

    card.addEventListener("click", async (ev) => {
        const el = ev.target.closest("[data-act]");
        if (!el) return;
        const o = data.phases;
        const row = el.closest("tr[data-index]");
        const phase = row ? o.phases[Number(row.dataset.index)] : null;
        switch (el.dataset.act) {
        case "activate":
            await adopt(await postActivatePhase(phase.id), true);
            break;
        case "delete-phase":
            if (!window.confirm(`Delete ${phase.name} and every day planned in it? This cannot be undone.`)) return;
            await adopt(await deletePhase(phase.id), phase.id === o.active_id);
            break;
        case "create-phase": {
            const name = $("#planNewPhaseName").value;
            const res = await postPhase({ name });
            if (res.ok) $("#planNewPhaseName").value = "";
            await adopt(res, false);
            break;
        }
        case "add-member": {
            const res = await postMember($("#planNewMember").value, o.active_id);
            if (res.ok) $("#planNewMember").value = "";
            await adopt(res, true);
            break;
        }
        case "delete-member": {
            ev.preventDefault();         // inside a <label>: do not toggle the box
            const m = o.members[Number(el.dataset.member)];
            if (!window.confirm(`Remove ${m.name} from the roster?`)) return;
            await adopt(await deleteMember(m.id), true);
            break;
        }
        case "suggest":
            await adopt(await postMember(o.suggestions[Number(el.dataset.suggest)], o.active_id), true);
            break;
        case "suggest-all": {
            let res = null;
            for (const name of o.suggestions) {
                res = await postMember(name, o.active_id);
                if (!res.ok) break;
            }
            if (res) await adopt(res, true);
            break;
        }
        default: break;
        }
    });
}
```

- [ ] **Step 4: The phase select in the phase bar** — in `renderPhase()` (`static/js/views/planning/render.js`), prepend to the template (reading `data.phases`):

```js
    const o = data.phases;
    const select = o ? `
        <label class="inline-field">Phase
            <select class="select" data-act="phase-select" aria-label="Active phase">
                ${o.phases.map((ph) => `<option value="${ph.id}"${ph.id === o.active_id ? " selected" : ""}>${esc(ph.name)}</option>`).join("")}
            </select>
        </label>` : "";
```

and change the first label's text from `Phase` to `From` (the select now carries the word "Phase"). Emit `${select}` first inside `#planPhase`'s `innerHTML`.

- [ ] **Step 5: index.js**

Imports: `getPhases, postActivatePhase` from `../../api.js`; `bindPhases, renderPhases` from `./phases.js`.

Add:

```js
async function loadPhases() {
    const res = await getPhases();
    if (!res.ok) return;
    data.phases = res.json;
    renderPhases();
}

/**
 * Everything that reads the plan, redrawn: the planner itself, and — through
 * `plan.js` — Daily's plan line and Productivity's attainment.
 */
async function afterPlanChange() {
    await loadPhases();
    await reloadAll();
    const cal = await getPlanCalendar();
    if (cal.ok) setPlanCalendar(cal.json);
}
```

- In `saveDay`, replace the tail (`await reloadAll(); const cal = ...; if (cal.ok) ...`) with `await afterPlanChange();` — saving can add a member to the roster, so the card must redraw too.
- In `loadPhase`, call `renderPhase()` after `data.phases` is available: make `reloadAll` run `await loadPhases();` first.
- In `bindPhase`'s `change` listener, before the `[data-setting]` lookup:

```js
        if (ev.target.matches('[data-act="phase-select"]')) {
            const res = await postActivatePhase(Number(ev.target.value));
            if (!res.ok) { showError("#planPhaseError", res.json.error); renderPhase(); return; }
            await afterPlanChange();
            return;
        }
```

- After a successful settings save in the same listener, replace `await reloadAll();` with `await afterPlanChange();` (the card shows the dates too).
- In `initPlanningView()` add `bindPhases({ onChanged: afterPlanChange });`. In `initPlanning()` make sure `loadPhases()` runs (via `reloadAll`).

- [ ] **Step 6: CSS** — append to `static/css/views.css` (planning section end, or the snapshots section — use whichever the file header says holds planning):

```css
#planPhases .plan-phase-new,
#planPhases .row { margin-top: var(--s-3, 12px); }
.plan-members-head { margin: var(--s-4, 16px) 0 var(--s-2, 8px); font-size: var(--fs-sm, 13px); }
.plan-suggestions { display: flex; flex-wrap: wrap; gap: var(--s-2, 8px); align-items: center; margin-top: var(--s-3, 12px); }
#planPhaseTable .input { min-width: 0; width: 100%; }
```

Replace the fallback values with the real token names from `tokens.css`.

- [ ] **Step 7: Verify**

Run: `.venv/bin/python -m pytest -q` → PASS. Syntax-check the changed planning modules. In the running app: Planning shows the phase select; create "Sprint 2", make it active → the Day plan and burndown empty, Daily's plan line changes; switch back → the old plan returns. Tick/untick members; add a suggested PIC; try deleting a member who has plan rows → the error line explains why.

- [ ] **Step 8: Commit**

```bash
/usr/bin/git add static templates
/usr/bin/git commit -m "Choose the active phase and manage members from Planning" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Documentation and final verification

**Files:**
- Modify: `CLAUDE.md`, `README.md`

- [ ] **Step 1: CLAUDE.md**

- **Overview/Commands:** add `TCM_DATABASE=/path/tcm.db` to the env var list; note the database at `~/.test-management/tcm.db`.
- **Architecture:** add "Snapshot flow: `/api/snapshots` → `Workspace` → `SqlSnapshotRepository` → SQLite; a restart restores the newest into the in-memory store."
- **Layering:** `sqlite3`/`sqlalchemy` join the forbidden frameworks for `tcm/domain/`.
- **Ports:** "seven ports" → nine, adding `SnapshotRepository` and `PhaseRepository`, and the rule's justification: the engine choice (stdlib vs SQLAlchemy) is still open, which is the planned swap.
- **Composition root:** `create_app` now also opens the database and calls `restore_latest()`; *Calling `create_app()` touches `$HOME`* — it now also creates/migrates `~/.test-management/tcm.db`; tests are isolated by the autouse `isolated_database` fixture.
- **Planning → Storage paragraph:** replace the `plan.json` paragraph: plan lives in `plan_day`/`plan_entry` under the active phase; phases and the roster; `SqlPlanRepository` resolves the active phase per call; member FK and auto-add; `plan.json` was not migrated.
- **New "Snapshots" section:** raw cells stored, classification per request; origin/Live; Reload goes live; compare over `in_plan` with today's taxonomy and the (file, sheet, device, row) key; migrations + backup.
- **Frontend:** `snapshotPanel.js` in the panels list; Compare as the second drill-in view (update "File is the one view with no nav item" → File and Compare); `views/planning/phases.js` in the planning layering sentence; `data.phases` in planning state.

- [ ] **Step 2: README.md** — in the Vietnamese tree, replace the `plan/json_store.py` line with a `db/` block:

```
│   │   ├── db/                  # SQLite: snapshot, phase, member, kế hoạch (~/.test-management/tcm.db)
```

and add a short section (Vietnamese) "Cơ sở dữ liệu": location, `TCM_DATABASE`, snapshots (lưu / mở / xoá / so sánh; khởi động sẽ mở snapshot mới nhất), phases & members, and that `plan.json` is no longer used.

- [ ] **Step 3: Full verification**

Run: `.venv/bin/python -m pytest -q` → all PASS.
Run: `grep -rn "PLAN_FILE\|plan\.json\|JsonPlanRepository" tcm tests static templates CLAUDE.md README.md` → only the deliberate "not migrated / no longer used" mentions.
Run the app against a scratch database and walk the flows from Tasks 8–10 once more end to end.

- [ ] **Step 4: Commit**

```bash
/usr/bin/git add CLAUDE.md README.md
/usr/bin/git commit -m "Document the database, snapshots and phases" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
