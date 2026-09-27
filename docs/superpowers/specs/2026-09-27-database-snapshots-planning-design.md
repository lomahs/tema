# Database: snapshots and planning

**Date:** 2026-09-27
**Status:** draft, awaiting review
**Branch:** `feature/database` (worktree `.claude/worktrees/database`)
**Scope:** a SQLite database for two things — load snapshots, and the plan
(phases, members, day plans). Projects, the publish log and the config
vocabularies are out of scope for this round.

## Goal

1. **Snapshots.** Save what is loaded, stamped with a date and time, on demand.
   Start the app on the latest one. Browse, open, delete and compare them.
2. **Planning in the database.** The plan moves out of `plan.json` into tables,
   gains **named phases** (many, one active) and a **member roster** chosen per
   phase, seeded from the PIC names found in the data.

## Decisions

Taken with the user on 2026-09-27.

| Decision | Choice | Why |
|---|---|---|
| Scope | Snapshots + planning only | User's call; projects deferred |
| Engine | SQLite, stdlib `sqlite3` | No new dependency. The user has not yet chosen between this and SQLAlchemy, so every table sits behind a port and all SQL lives in `tcm/infrastructure/db/` — a switch rewrites that folder only |
| Snapshot trigger | Manual *Save snapshot* button | User's call; no auto-save |
| Snapshot history | List, open, delete, compare | User's call |
| Phases | Named, many, exactly one active | User's call; replaces the single `PlanSettings` record |
| Members | Global roster; each phase picks its members; unknown PICs in the data offered as suggestions | User's call |
| Existing `plan.json` | Not imported. `JsonPlanRepository`, `settings.PLAN_FILE` and their tests are deleted; a leftover file is ignored | User's call — the existing plan data is not needed |

## Where the database is

`~/.test-management/tcm.db`, overridable with `TCM_DATABASE` (`settings.DATABASE_FILE`).
It sits beside the Graph token cache: it is this machine's operational data,
not the project's shipped config, and a plan in it is the only copy there is.

## Schema

```
member ──< phase_member >── phase ──< plan_day ──< plan_entry >── member
snapshot ──< snapshot_file ──< test_case
app_state (key/value): active_phase_id
```

```sql
CREATE TABLE app_state (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE member (
  id   INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE                 -- matches TestCase.pic verbatim
);

CREATE TABLE phase (
  id           INTEGER PRIMARY KEY,
  name         TEXT NOT NULL UNIQUE,
  phase_start  TEXT,                        -- YYYY-MM-DD or NULL (= default)
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
  baseline_at TEXT,                         -- NULL = never frozen
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

CREATE TABLE snapshot (
  id         INTEGER PRIMARY KEY,
  taken_at   TEXT NOT NULL,                 -- ISO timestamp, seconds
  label      TEXT NOT NULL DEFAULT '',
  source     TEXT,                          -- JSON: {"type", "value"}
  case_count INTEGER NOT NULL,
  file_count INTEGER NOT NULL
);

CREATE TABLE snapshot_file (
  id          INTEGER PRIMARY KEY,
  snapshot_id INTEGER NOT NULL REFERENCES snapshot(id) ON DELETE CASCADE,
  position    INTEGER NOT NULL,             -- keeps load order
  file        TEXT NOT NULL,
  path        TEXT,
  status      TEXT NOT NULL,
  result      TEXT NOT NULL                 -- the whole file_results dict, JSON
);

CREATE TABLE test_case (
  id               INTEGER PRIMARY KEY,
  snapshot_file_id INTEGER NOT NULL REFERENCES snapshot_file(id) ON DELETE CASCADE,
  position         INTEGER NOT NULL,        -- keeps source order
  sheet TEXT NOT NULL, device TEXT NOT NULL, row_num INTEGER NOT NULL,
  case_no TEXT, scope TEXT, result TEXT, test_date TEXT,
  pic TEXT, ticket_id TEXT, note TEXT
);
CREATE INDEX test_case_file ON test_case(snapshot_file_id);
```

Rules the schema carries:

- **A test case stores raw cell values, never a status.** Classification stays
  per request, so an old snapshot re-classifies correctly after a taxonomy edit
  and nothing in the database has to be migrated when the taxonomy changes.
- **`test_case.pic` is text, not a `member` foreign key.** It is read verbatim
  out of a workbook; a roster is something the user curates. The two meet by
  name, which is also how a plan is joined to its actuals today.
- **`plan_entry.member_id` is a foreign key.** Saving a day that names a PIC not
  on the roster adds it to the roster (and to that phase) in the same
  transaction, so a plan never refers to nobody. Deleting a member still named
  by a plan row is refused with a message (`RESTRICT`).
- **Baseline rows are entries with `is_baseline = 1`**, and `plan_day.baseline_at`
  non-NULL means "frozen" — including a frozen baseline with no rows, which is
  what `DayPlan.baseline == []` means today.
- **A day with no rows and no baseline is not stored**, the rule `JsonPlanRepository.put_day`
  already applies.
- `PRAGMA foreign_keys = ON` on every connection; `journal_mode = WAL`.

## Migrations and backup

`PRAGMA user_version` is the schema version. `tcm/infrastructure/db/schema.py`
holds an ordered list of migration scripts; `Database.migrate()` runs the ones
above `user_version`, each in its own transaction. **Before migrating a database
that already exists and has a lower version, it is copied** with SQLite's online
backup API to `tcm.db.v<old>-<timestamp>.bak` beside it. A fresh file needs no
backup.

## First boot

When the database has no phase at all, an empty **"Phase 1"** is created and
made active. From then on there is always at least one phase and exactly one
active phase. `plan.json` is not read: the JSON plan store is removed
(`tcm/infrastructure/plan/`, `settings.PLAN_FILE`,
`tests/infrastructure/test_plan_store.py`), and a file left in
`~/.test-management` is simply ignored.

## Components

### Domain (`tcm/domain/`)

- `phase.py` — `Phase(id, name, phase_start, phase_end, daily_target, members)`
  with `from_dict` validation (name non-empty, dates via `parse_date`, end ≥
  start, target a positive int, members a list of non-empty unique names).
  `Phase.settings` returns the `PlanSettings` the planner already consumes.
- `ports.py` gains:
  - `SnapshotRepository`: `save(snapshot, label) -> dict`, `list() -> list[dict]`,
    `load(id) -> Snapshot`, `delete(id) -> None`, `latest_id() -> Optional[int]`.
  - `PhaseRepository`: `phases()`, `phase(id)`, `create(phase)`, `update(phase)`,
    `delete(id)`, `active_id()`, `set_active(id)`, `members()`, `add_member(name)`,
    `delete_member(id)`.
  - `PlanRepository` gains `members() -> list[str]`: the active phase's roster
    (empty means "no roster").
- `Snapshot` gains `origin: Optional[dict]` — `None` for a live load,
  `{"id", "taken_at", "label"}` for one opened from the database.

### Infrastructure (`tcm/infrastructure/db/`)

- `database.py` — `Database(path)`: `connect()` context manager (commit on
  success, rollback on error), `migrate()`, `backup(dest)`.
- `schema.py` — the migration list.
- `snapshots.py` — `SqlSnapshotRepository(db)`. `save` inserts with
  `executemany` inside one transaction; `load` rebuilds `TestCase`s in stored
  order.
- `phases.py` — `SqlPhaseRepository(db)`.
- `plans.py` — `SqlPlanRepository(db)`: the `PlanRepository` for **the active
  phase**, resolved at call time from `app_state`, so switching phase needs no
  rebuild of anything. `settings()` / `put_settings()` read and write the active
  phase's dates and target.
- `bootstrap.py` — `open_database(path)`: migrate, then create "Phase 1" if
  there is no phase. Called only from `create_app`.

### Services (`tcm/services/`)

- `Workspace(loader, store, snapshots=None)` gains `save_snapshot(label)`,
  `snapshots()`, `open_snapshot(id)`, `delete_snapshot(id)`, `restore_latest()`,
  `compare(base_id, head_id)` and an `origin` property. Opening a snapshot puts
  it in the store exactly as a load would, with its `origin` set; a load or
  reload clears `origin` back to live. Saving with nothing loaded is a 400.
- `aggregation.py` gains `compare_cases(base, head)` — see Compare below. It is
  aggregation, so it lives with the rest.
- `planning.py`: `board_view`'s members become *roster ∪ everyone with a plan
  row that day* when the roster is non-empty, and stay as today otherwise.
- `phases.py` — `PhaseService(repo)`: CRUD, activation, the roster, and
  `suggestions(cases)` = PICs in the loaded cases not on the roster. It refuses
  deleting the last phase; deleting the active one activates the most recently
  created remaining phase.

### Compare

`compare_cases(base, head)` runs both sides through `in_plan` and classifies
with the **current** taxonomy (`STATUS.classify_case`):

- `totals`: per status key, `{base, head, delta}`, plus `total` over
  `STATUS.counted` — the same invariant Summary holds.
- `rows`: per (file, device), per status base/head/delta, sorted by file, device.
- `transitions`: cases matched on (file, sheet, device, row_num); a count per
  (from_status, to_status) where they differ. A case on one side only is
  `from: null` (added) or `to: null` (removed).

### Web

`tcm/web/blueprints/snapshots.py`:

| Route | Does |
|---|---|
| `GET /api/workspace` | What is loaded now: `{loaded, file_count, file_results, source, origin}` — lets the page draw a restored snapshot at startup |
| `GET /api/snapshots` | The history, newest first |
| `POST /api/snapshots` | `{label}` → save the current load; 400 when nothing is loaded |
| `POST /api/snapshots/<id>/open` | Put it in the store; answers like `/api/load` |
| `DELETE /api/snapshots/<id>` | 404 when unknown |
| `GET /api/snapshots/compare?base=&head=` | The compare result; 400/404 on bad ids |

`tcm/web/blueprints/phases.py`:

| Route | Does |
|---|---|
| `GET /api/phases` | `{phases, active_id, members, suggestions}` |
| `POST /api/phases` | Create; `activate: true` also activates it |
| `PUT /api/phases/<id>` | Replace name, dates, target and member list |
| `DELETE /api/phases/<id>` | Refused for the last phase |
| `POST /api/phases/<id>/activate` | Switch the active phase |
| `POST /api/members` / `DELETE /api/members/<id>` | Roster; delete refused while a plan names them |

Every existing `/api/plan/*` endpoint keeps its shape and now means "the active
phase". `PUT /api/plan/settings` edits the active phase's dates and target.

`create_app(workspace=None, identity=None, planning=None, database=None)` opens
the database (unless every service is supplied), builds the SQL repositories,
the workspace, `PlanningService(SqlPlanRepository)` and `PhaseService`, and calls
`workspace.restore_latest()`.

### Front end

- **Tools → Snapshots card** (`static/js/snapshotPanel.js`, a panel in the mould
  of `sourcePanel.js`: knows nothing about the views). A label field and *Save
  snapshot*; a table of snapshots (taken at, label, files, cases) with *Open*
  and *Delete*; Base / Head selects and *Compare*. It reports back through
  `onOpened(loadResult)` and `onCompare(base, head)`, which `main.js` routes.
- **Compare view** (`views/compare.js`, `templates/views/compare.html`): a
  drill-in like File — no nav item, a Back button. Status totals with deltas,
  a (file, device) delta table, and the transition matrix. Deltas carry no
  colour of their own; statuses keep their tones.
- **Rail source card** shows *Live* or *Snapshot · 27 Sep 14:02 · label*.
- **Startup**: `main.js` asks `GET /api/workspace`; if something was restored it
  runs `refreshViews(result)` and opens Summary, otherwise Tools as today.
- **Planning**: the phase bar gains a phase select (switching reloads the
  planner, Daily and Productivity through `onPlanChange`) and shows the phase
  name. A new **Phases & members** card at the bottom (`views/planning/phases.js`,
  a DOM-writing module beside `editor.js`, imported only by `index.js`) lists
  phases (name, dates, target, members, active, delete), a *New phase* row, the
  active phase's member checkboxes, and "Found in data" suggestions each with
  *Add*. No new floating surface.

## Error handling

- Domain `ValueError` → 400 with its message, as everywhere else.
- Unknown snapshot / phase / member id → 404.
- `sqlite3.IntegrityError` from a `RESTRICT` or `UNIQUE` is translated inside the
  repository into a `ValueError` with a sentence a person can act on ("An is
  still planned on 3 days — remove those rows first").
- A database that cannot be opened or migrated fails at startup, like a
  malformed shipped config: running on without the plan would invite a save
  over it.

## Testing

- `tests/conftest.py` gains an autouse fixture pointing `settings.DATABASE_FILE`
  into `tmp_path`, so no test can touch
  `~/.test-management`.
- `tests/infrastructure/test_db_*.py`: migrations, backup and first boot,
  snapshot round trip (order,
  `None`s, file results), phases/members/plans incl. `RESTRICT` and
  auto-add-member.
- `tests/services/`: workspace snapshot flow and origin, `compare_cases`
  (partition, added/removed, `in_plan`), phase service rules, board roster.
- `tests/web/`: every new endpoint; the existing planning service and API tests
  run against the SQL repository (they used `JsonPlanRepository` over a temp file).
- `tests/domain/test_ports.py`: the SQL repositories answer their ports.
- `tests/test_layering.py`: `sqlite3` and `sqlalchemy` join the frameworks the
  domain may not import.

## Out of scope

Projects and a project switcher; a publish log; the config vocabularies in the
database; automatic snapshots and retention; multi-user access; renaming a
member (it would detach them from the PIC in the workbooks).
