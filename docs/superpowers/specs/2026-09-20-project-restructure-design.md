# Project restructure: layered architecture

**Date:** 2026-09-20
**Status:** approved, not yet executed
**Scope:** whole repository — Python, JavaScript, CSS, templates

## Goal

Reorganise the codebase into explicit layers so that continued development —
including an eventual move to multiple users and possibly a database — is a
change inside one directory rather than a change everywhere. Behaviour does not
change. No feature is added, removed or altered.

## Why now

The app works and its invariants are well documented in `CLAUDE.md`, but the
tree no longer reflects them:

- **`parser/` is four unrelated things.** It holds the Excel reader, four domain
  vocabularies (`StatusSet`, `ScopeSet`, `DeviceSet`, `SheetLabels`), and the
  JSON data those vocabularies read. The vocabularies parse nothing; they live
  there because the reader happened to be their first caller. The package also
  shadows the stdlib `parser` name.
- **`api/routes.py` is 506 lines and owns application state.** The `_data`
  store, the `_auth` singleton, the `_login` dict and its lock, `_spawn`,
  `_load()` and `_requested_files()` are services in a route's clothing.
  `CLAUDE.md` already states the intended rule — "routes are `jsonify`
  wrappers" — and these are the places it is not true.
- **The service layer is invisible.** `aggregate.py`, `config_store.py`,
  `prepare/runner.py` and `report/publisher.py` are the services, spread across
  three levels of the tree, so nothing in the file listing says they are a layer.
- **Two JS view modules carry everything.** `views/detail.js` is 1128 lines and
  `views/summary.js` 924, each mixing state, filtering and rendering.
- **`app.css` is 1649 lines in 35 comment-delimited sections**, and
  `templates/index.html` is 612 lines holding seven view sections inline.
- **There is no `pyproject.toml`** — no package metadata, no pytest
  configuration, no declared rootdir.

## Decisions

Taken with the user on 2026-09-20.

| Decision | Choice | Rationale |
|---|---|---|
| Scope | Everything: Python, JS, CSS, templates | User's call; decomposed into four phases below |
| Python depth | Single layered package with concrete dependencies | Layers readable from the file listing, no framework ceremony |
| Ports | Yes — `Protocol` at the I/O boundaries | User's call, overriding a YAGNI recommendation; scoped by the rule below |
| Multi-user | Not implemented; seams placed | Behaviour must stay identical for the move to be verifiable |
| App state | `Workspace` / `IdentityService` objects | Testability: `tests/web/test_api.py` currently resets `routes._data` by hand |
| Sequencing | Land in-flight work, fix red tests, then move | A refactor claiming "behaviour identical" needs a green baseline |

**The rule that bounds the ports:** a port exists where a test already needs a
stand-in, or where a swap is genuinely planned. Nothing else gets one.

## Target structure

Dependencies point strictly inward: `web → services → domain`,
`infrastructure → domain`, and nothing imports `web`.

```
pyproject.toml             NEW — metadata, pytest config, rootdir
config/                    the five JSONs, moved out of parser/ and report/
  result_status.json  scope_groups.json  device_groups.json
  sheet_labels.json   report_layout.json
tcm/
  settings.py              ← config.py            env + paths as a Settings dataclass
  domain/                  no I/O: no flask, pandas, requests or msal
    case.py                ← parser/models.py     TestCase, SheetConfig, CASE_COLUMNS
    status.py              ← parser/status.py     StatusSet, DERIVE_CONDITIONS, TONES
    scope.py               ← parser/scope.py      ScopeSet
    device.py              ← parser/device.py     DeviceSet
    sheet_labels.py        ← parser/sheet_labels.py
    ports.py               NEW — the six Protocols
  services/                orchestration over domain objects; no Flask, no HTTP
    aggregation.py         ← aggregate.py
    workspace.py           NEW — loaded source + cases (was routes._data + _load)
    identity.py            NEW — sign-in + device login (was _auth/_login/_spawn)
    preparation.py         ← prepare/runner.py
    publishing.py          ← report/publisher.py
    settings_store.py      ← config_store.py
  infrastructure/          the only code touching Excel, Graph, disk or the OS
    excel/reader.py        ← parser/excel_reader.py
    excel/detection.py     ← parser/tool_data_builder.py
    excel/tool_data.py     ← prepare/tool_data.py
    excel/clearing.py      ← prepare/clear.py
    excel/workbook.py      ← prepare/workbook.py
    graph/auth.py          ← sharepoint/auth.py
    graph/client.py        ← sharepoint/client.py
    graph/links.py         ← sharepoint/links.py
    graph/workbook.py      ← sharepoint/workbook.py
    report/layout.py       ← report/layout.py
    report/builder.py      ← report/builder.py
    store/memory.py        NEW — InMemoryCaseStore
    config_repo.py         NEW — JSON read/write split out of config_store
    dialog.py              ← api/filedialog.py
  web/
    app.py                 ← app.py    create_app, and the composition root
    blueprints/source.py       /api/load /reload /browse /prepare/files
    blueprints/analytics.py    /api/summary /cases /file /daily /productivity /statuses
    blueprints/prepare.py      /api/prepare/tool-data /clear
    blueprints/settings.py     /api/config, PUT /api/config/<name>
    blueprints/sharepoint.py   /api/sharepoint/*, /api/report/publish
    blueprints/pages.py        "/"
static/css/                tokens.css unchanged; app.css cut six ways, order load-bearing
static/js/views/detail/    state.js filters.js render.js index.js
static/js/views/summary/   state.js buckets.js render.js index.js
templates/views/           one file per view section, included by index.html
tests/                     mirrors tcm/: domain/ services/ infrastructure/ web/
```

### Why the JSONs move to `config/`

They are written at runtime by the Config view. A package directory is the wrong
place to write user data, and a top-level `config/` is where someone editing the
taxonomy by hand would look. `report_layout.json` joins them although it is not
app-editable; that distinction lives in `settings_store.CONFIGS`, which is code,
not in the filesystem.

### The six ports

Each has exactly one implementation today and a named reason to exist.

| Port | Implementation | Reason |
|---|---|---|
| `ReportWorkbook` | `graph.workbook.Workbook` | `tests/services/test_publisher.py:17` `FakeWorkbook` already implements exactly its 8 public methods — this writes down an interface that exists |
| `CaseLoader` | `excel.reader.ExcelCaseLoader` | lets `Workspace` be tested without building `.xlsx` fixtures |
| `CaseStore` | `store.memory.InMemoryCaseStore` | the database seam |
| `ConfigRepository` | `config_repo.JsonFileConfigRepository` | the settings-in-a-database seam; also isolates the atomic-write logic |
| `TokenProvider` | `graph.auth.GraphAuth` | per-user tokens later; fakeable now |
| `FilePicker` | `dialog.NativeDialog` | `tests/infrastructure/test_filedialog.py` already fakes it |

`ReportWorkbook`'s eight methods are `worksheet_names`, `used_range`,
`write_values`, `delete_rows`, `table_at`, `table_rows`, `table_add_rows`,
`table_delete_row`. Widening the port means widening the fake — the rule
`CLAUDE.md` already states, now enforced by a type.

## Phases

### Phase 0 — clear the runway (gates everything)

1. Land the 707 uncommitted insertions on `redesign/ledger-ui` as a commit.
2. One commit fixing the 3 pre-existing failures. They are config drift, not
   regressions — the same three fail at `HEAD`:
   - `tests/test_status.py:180` expects NG-OK's tone to be `warn`;
     `result_status.json` now says `success`.
   - `tests/test_api.py::test_summary_flags_only_cases_that_need_a_reason_and_lack_one`
   - `tests/test_api.py::test_missing_reason_rows_carry_their_status` — `KeyError`,
     a `missing_reason` row-shape change.
3. Gate: `.venv/bin/python -m pytest -q` reads `450 passed`.

### Phase 1 — the layered tree (pure move)

Create `tcm/`, move every module per the table, rewrite the **104 import
statements across 36 files**, move the JSONs to `config/`, add `pyproject.toml`,
mirror `tests/` onto the new layout.

No logic edits. Not a docstring fix, not an obvious tidy. A module that is wrong
stays wrong and gets its own commit afterwards. This is what makes a red test
unambiguously the move's fault.

Move with `git mv`, one layer per commit, in the order domain → infrastructure →
services → web, because each layer imports only inward from layers already moved.

### Phase 2 — ports, `Workspace`, `IdentityService`

1. Write `domain/ports.py`.
2. `Workspace` takes a `CaseLoader` and a `CaseStore`; absorbs `_data` and
   `_load`. Its API: `load_folder`, `load_files`, `reload`, `cases`, `source`,
   `file_results`, `source_workbooks`.
3. `IdentityService` takes a `TokenProvider`; absorbs `_auth`, `_login`,
   `_login_lock`, `_spawn`, `_await_login`. Its API: `status`, `begin_login`,
   `sign_out`, `token`. The background-thread strategy stays injectable so tests
   keep running it inline.
4. Split `routes.py` into the five blueprints. `_requested_files` becomes a
   `Workspace` method plus a thin request guard.
5. `create_app(settings)` becomes the composition root: it builds the concrete
   implementations and attaches them to `app.extensions`.
6. `tests/test_api.py` stops resetting `routes._data`.

### Phase 3 — the two oversized JS views (independent of 1–2)

`views/detail.js` → `views/detail/{state,filters,render,index}.js`.
`views/summary.js` → `views/summary/{state,buckets,render,index}.js`.

Summary gained a `state.js` the original three did not name, for the reason Detail has one:
`groups`, `scopes`, `chosenScopes`, `sort`, `grouping`, `families`, `paging` and the two
callbacks are written by `index.js` and read by both the others, and a `let` cannot be written
through an imported binding. Leaving them in `index.js` would have made `buckets.js` and
`render.js` import it — the cycle the split exists to avoid.

The constraint from `CLAUDE.md` survives exactly: **each piece of mutable state
keeps one owning module and is reached through functions.** `state.js` owns
detail's state; `filters.js` and `render.js` call into it and never hold their
own copy. No view imports another view; the widgets (`pagination.js`,
`groupedTable.js`, `filesTable.js`) import no view or panel module.

### Phase 4 — CSS and templates (independent of everything)

`app.css`'s 35 sections become six files — `base`, `controls`, `tables`, `cards`,
`charts`, `views` — linked from `index.html` **in the exact order they are concatenated
today**, because the cascade depends on it. `tokens.css` is untouched, and no rule text
changes.

**The six are cut at contiguous section boundaries rather than sorted into semantic
buckets, and two of the names changed because of it.** This paragraph originally named
`base`, `layout`, `controls`, `tables`, `cards`, `charts`, which assumed the sections sat
in semantic runs. They do not: the panel grid sits between two card sections, the folded
filter panel between two chart ones, and the narrow-screen media query in the middle rather
than at the end. Bucketing them by subject would therefore have moved rules past others of
equal specificity — the reordering this phase's own constraint forbids. Cutting by line
range instead makes the concatenation byte-exact and the cascade provably unchanged;
`layout` folds into `base`, and `views` holds the tail, which is view- and panel-specific
CSS that fits none of the original six names.

`index.html` keeps the shell and `{% include %}`s one partial per
`<section class="view">`: summary, daily, productivity, detail, file, tools,
config.

## Verification

**Python.** The full suite after every commit. Plus a new test asserting the
layering rule executably: no module under `tcm/domain/` may import `flask`,
`pandas`, `requests` or `msal`, and nothing outside `tcm/web/` may import
`flask`.

**JS, CSS, templates.** No JS test framework exists and none is added. Phases 3
and 4 verify by running the app and exercising all seven views — Summary's three
buckets, Daily's grouping and chart, Productivity, Detail's drill-in from a
status figure, the File drill-in, Tools, and a Config save-and-apply — in both
light and dark themes. Syntax-check a module by copying it to `.mjs` first;
`node --check` silently passes `.js` files.

## Documentation

`CLAUDE.md` is a deliverable of this work, not an afterthought. It names roughly
60 file paths and is the architecture document; it is rewritten as the final
commit of each phase, inside that phase. `README.md`'s Vietnamese structure tree
is updated with it.

## Explicitly out of scope

- **Multi-user, sessions, accounts, database.** Seams are placed; nothing is
  implemented. Each becomes its own spec.
- **The vocabulary-singleton mutation.** `STATUS`, `SCOPES`, `DEVICES` and
  `LABELS` are imported by name into eight modules, and `settings_store.save()`
  mutates them in place via `adopt()` because rebinding would reach no importer.
  With two users, one editing the taxonomy changes what every figure on the
  other's screen means, mid-session. This is real, and it is a *behaviour*
  problem — putting it inside the one phase that must change no behaviour is how
  a restructure becomes unverifiable. It is recorded here so the next spec can
  pick it up.
- **Per-user Graph tokens.** One `GraphAuth` and one 0600 cache file serve the
  whole process today. The `TokenProvider` port is where that gets cut.
- **Any feature, endpoint, figure or pixel.** If the UI looks different, the
  refactor is wrong.
