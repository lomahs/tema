# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Flask web app that reads test cases out of Excel workbooks (`.xlsx`) and aggregates
progress / results into three views (Summary, Daily, Detail). Single-user local tool:
no database, no build step, no auth. README.md is written in Vietnamese and holds the
full Excel-format and sample-generator reference.

## Commands

Use the project venv (Python 3.14) — it holds Flask/pandas/openpyxl:

```bash
.venv/bin/python app.py                      # http://127.0.0.1:5000
.venv/bin/python -m pytest -q                # all tests
.venv/bin/python -m pytest tests/test_api.py::test_reload_reuses_the_remembered_source -q   # one test
.venv/bin/python -m tools.generate_samples --out samples/generated --seed 1  # synthetic .xlsx
RESULT_STATUS_CONFIG=/path/my_status.json .venv/bin/python app.py            # alternate taxonomy
GRAPH_CLIENT_ID=... .venv/bin/python -m tools.publish_report --folder samples/generated --url "<link>"
```

`PORT` and `DEBUG` are env vars (see [config.py](config.py)); `DEBUG` defaults to on.
There is no linter or formatter configured.

## Architecture

Read flow: browser → `/api/load` → [parser/excel_reader.py](parser/excel_reader.py) →
in-memory `_data` dict in [api/routes.py](api/routes.py) → [aggregate.py](aggregate.py) →
the GET endpoints → ES modules under [static/js/](static/js/).

Write flow: `/api/report/publish` → [report/publisher.py](report/publisher.py) →
[sharepoint/workbook.py](sharepoint/workbook.py) → Microsoft Graph. Reading stays local;
Graph is only ever used to write.

**TOOL_DATA is the schema.** Test case sheets have no fixed layout. Each workbook carries a
`TOOL_DATA` sheet whose rows say, per (sheet, device): the row span and the Excel column
letter for each field. One sheet usually has several device blocks, so several TOOL_DATA
rows share a sheet — [load_file](parser/excel_reader.py) groups configs by sheet and parses
each sheet once (`dtype=object`, `header=None`) before slicing per device. Sheets are parsed
positionally by column letter, never by header name.

**Errors are per-file, not fatal.** `load_files` catches per workbook and reports
`{"file", "status", "error"}` so one malformed TOOL_DATA row doesn't sink a batch. Excel lock
files (`~$*.xlsx`) are skipped.

**The status taxonomy is data, not code.** [parser/result_status.json](parser/result_status.json)
maps raw Result strings → status keys, and `StatusSet` in [parser/status.py](parser/status.py)
validates it at import time. Exactly one status must set `"empty": true` (blank cells → NYS) and
exactly one `"fallback": true` (unknown values → Other) — the fallback is what makes each row's
`total` equal the sum of its status columns, which several tests assert. `needs_reason` lists the
statuses that must carry a Ticket ID or a Note; `/api/summary` reports violators under
`missing_reason`. `"executed": true` marks the statuses that count as work carried out —
`/api/productivity` divides those cases by the days a PIC actually tested. Any number of statuses
may set it (a config with none simply yields a productivity table of zeros).

Adding or renaming a status means editing only that JSON. Backend, `/api/statuses`, the UI and the
sample generator all read from it — never hard-code status keys in Python or JS.

**Frontend state ownership.** No framework, no bundler; `templates/index.html` loads
[static/js/main.js](static/js/main.js) as `<script type="module">`. An imported ES binding can't be
reassigned by the importer, so each piece of mutable state lives in exactly one module and is
reached through functions: taxonomy in `taxonomy.js`, cases/filters/page in `views/detail.js`,
daily rows in `views/daily.js`, per-PIC productivity rows in `views/productivity.js`,
Chart.js instances in `charts.js`. `pagination.js` is a
self-contained widget taking `{totalItems, pageSize, currentPage, onPageChange, container}` —
it must not import `views/detail.js` (circular). Both the detail table (50/page, `#pagination`)
and the daily table (10/page, `#dailyPagination`) use it, so each pager needs its own `<nav>`
selector passed in.

Behavior worth preserving when touching the UI:
- `refreshViews()` in `main.js` must call `setTaxonomy()` before any header/card render.
- `makeSortable(".sortable", …)` is bound **once** at init; `.daily-sortable` and
  `.prod-sortable` are rebound per render because `renderDailyHead` / `renderProductivityHead`
  replace the `<th>`s. Duplicating a listener sorts twice and looks like nothing happened.
- The productivity table sits inside `#dailyView` but ignores the daily filters on purpose —
  it reports over everything loaded, so it re-renders only on sort, never on filter change.
- `showView("detail")` calls `resizeCharts()` — Chart.js sizes to a 0×0 container while hidden.
- The Chart.js CDN `<script>` must stay before the module tag.
- Every `fetch` lives in `api.js`; no view or panel module calls it directly.
- `reportPanel.js` mirrors `sourcePanel.js`: it owns where results *go* and knows nothing
  about the views. `refreshViews()` calls `setReportEnabled(true)` — publishing with nothing
  loaded would clear the day's rows and write none back, which the endpoint also refuses.

**Aggregation is shared, not owned by the routes.** [aggregate.py](aggregate.py) holds
`summary_rows` / `daily_rows` / `productivity_rows` / `issue_rows` as plain functions over
`TestCase` lists. The four GET endpoints are `jsonify` wrappers around them, and the report
publisher calls the same functions — so the numbers on screen and the numbers in the
SharePoint report cannot drift. Put new aggregation here, not in a route.

**Graph writes in place, never round-trips the file.** [sharepoint/workbook.py](sharepoint/workbook.py)
edits the report workbook through Graph's Excel workbook API: `usedRange` to find the end,
`range(...)/delete` with `shift: Up` to remove rows, `range(...)` PATCH to write. Downloading
the file, editing it with openpyxl and `PUT /content`-ing it back would destroy charts, pivots
and formatting in a hand-built report — do not switch to that. Its interface is deliberately
seven methods wide because `tests/test_publisher.py` drives the publisher through a stand-in
that implements exactly those; widening it means widening the fake.
`tests/test_publish_integration.py` runs the real client, links and workbook against a fake
Graph service that parses the addresses it is sent, which is what stops the two from drifting.

**`run_date` is the idempotency key.** Every published row carries it, and the publisher
deletes rows already bearing that date before appending. That is the whole reason a failed
publish is safe to retry — there is no rollback, so a half-written file is fixed by running
again. Range mode deletes contiguous blocks bottom-up (deleting shifts rows up); table mode
deletes indices descending (deleting renumbers). `_normalise_date` exists because a
Date-formatted column comes back from Graph as an Excel serial number, not `"2026-09-06"`.

**The report layout is data too.** [report/report_layout.json](report/report_layout.json) says
which sheet and column each value goes to, validated at import by `ReportLayout` the same way
`StatusSet` validates the taxonomy. `{"expand": "statuses"}` widens a sheet by one column per
status in taxonomy order, and `"issue": true` in `result_status.json` decides what reaches the
Issues sheet — so neither status keys nor column positions are ever hard-coded in Python or JS.

**Out of scope by decision:** the module-level `_data` dict in `api/routes.py` stays global
mutable state; it is deliberate for a single-user local tool. The same goes for `_auth` and
the `_login` dict guarded by `_login_lock` — one person is at the keyboard. Device sign-in
runs on a background thread via `_spawn`, which tests replace to run inline.

## Tests

pytest only, Python side only (no JS test framework — verify UI changes by running the app;
`node --check` silently passes on `.js` files, so copy a module to `.mjs` first if you want a
syntax check). No test touches the network: Graph is always a fake transport.
[tests/conftest.py](tests/conftest.py) builds real `.xlsx` fixtures in `tmp_path` via
`config_row()` + `write_workbook()`; use those helpers rather than checking in binaries.
`tests/test_api.py` resets `routes._data` between tests since the store is global.
