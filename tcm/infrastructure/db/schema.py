"""The schema, as an ordered list of migrations.

`MIGRATIONS[n]` takes a database from version n to n + 1; the version lives in
`PRAGMA user_version`. Never edit a migration that has shipped -- append one.

Rules the v1 tables carry, which the repositories rely on:

- A test case stores the raw cells it was read from, never a status, so an old
  snapshot re-classifies with whatever the taxonomy says today.
- `test_case.pic` is text, not a member id: it is read verbatim out of a
  workbook, while the roster is something the user curates. The two meet by
  name, which is how a plan has always been joined to its actuals.
- `plan_entry.member_id` *is* a foreign key, and `RESTRICT`: a plan never refers
  to nobody, and a member still named by one cannot be deleted.
- Baseline rows are entries with `is_baseline = 1`, and a non-NULL
  `plan_day.baseline_at` is what "frozen" means -- including a frozen baseline
  with no rows at all.
- `snapshot_file.result` is NULL only on a row with `position = -1`: a file a
  case named but no load result described.
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
