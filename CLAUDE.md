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
files (`~$*.xlsx`) are skipped. `prepare/runner.py` follows the same rule for the same reason.

**Two definitions exist so they can't be written twice.** `find_workbooks(folder)` in
`excel_reader` is *the* answer to "every workbook under here" — loading, the prepare endpoints
and the sample generator all resolve a folder through it, so a file one of them acts on is
always one the others can see, lock-file skipping included. `CASE_COLUMNS` in [parser/models.py](parser/models.py)
is *the* `TestCase`→`SheetConfig` mapping; the reader and `prepare/clear.py` both walk rows by
it, and reading a row two different ways is how a case ends up classified two different ways.

**The status taxonomy is data, not code.** [parser/result_status.json](parser/result_status.json)
maps raw Result strings → status keys, and `StatusSet` in [parser/status.py](parser/status.py)
validates it at import time. Exactly one status must set `"empty": true` (blank cells → NYS) and
exactly one `"fallback": true` (unknown values → Other) — the fallback is what makes every case
land in exactly one column, which several tests assert. `needs_reason` lists the
statuses that must carry a Ticket ID or a Note; `/api/summary` reports violators under
`missing_reason`. `"executed": true` marks the statuses that count as work carried out —
`/api/productivity` divides those cases by the days a PIC actually tested. Any number of statuses
may set it (a config with none simply yields a productivity table of zeros).

Each status also carries a `tone` — `success` / `danger` / `warn` / `neutral` / `muted` — which
is the *only* colour input the UI has. Badges, the numbers in the status band and the chart
slices all derive from it, which is what stops the chart palette drifting from the table's the
way a positional colour array once did. The tone names what a status *means*; what it looks
like lives in `tokens.css`. A config that predates the field has its tone inferred from the old
Bootstrap `badge` string, so `badge` and `text` are still emitted but nothing in the UI reads
them. Several statuses may share a tone (OK and NG-OK are both good outcomes); charts separate
them by stepping the shade in taxonomy order.

**Some statuses are not readable off the Result cell.** `"derive": {"from": ..., "when": ...}`
says a status *becomes* another one when something else about the row is true. Out Of Scope is
the shipped case: `対象外` with no PIC was never in the plan, whereas `対象外` with a PIC is a
decision someone made and still owes a reason. So `STATUS.classify(result)` — pure, result-string
only — is no longer the whole story, and **every aggregate calls `STATUS.classify_case(case)`
instead**; `classify` survives for the config and the sample generator. `DERIVE_CONDITIONS` in
`parser/status.py` is the closed set of conditions the JSON may name (`no_pic` today). Derivation
is one step by construction: a derived status may not itself be derived from, may not carry
`match` / `empty` / `fallback`, and two statuses may not claim the same source. Adding a second
condition means one entry in that table, not a new branch in the aggregates.

**`"excluded": true` breaks the total on purpose.** An excluded status keeps its column — the
count has to stay visible — but is left out of `total`, so a case outside the plan cannot inflate
the denominator progress is read against. The invariant is therefore *not* "total equals the sum
of every status column" but the narrower **"total equals the sum of `STATUS.counted`"**; that is
what `_counted_total` in `aggregate.py` computes and what the reconcile tests assert. Two things
follow, and both are enforced rather than left to the config: `needs_reason` may not name an
excluded status (a case outside the plan owes nobody an explanation), and `{"expand": "statuses"}`
expands over `counted`, so an excluded status gets **no report column** — which is what keeps the
published sheet adding up to its own total and its width unchanged. In the UI the column is drawn
with `band--aside`, a dashed rule marking where the sum stops.

**`"review": true` is what the Detail view holds.** Detail is the list of work outstanding, so it
loads *only* those statuses (NG / NG-OK / Pending / Cancel) and drops everything else at
`initDetail`. That is a deliberate restriction, not a default filter — which is why its stat strip
is labelled **"To review"** and not "Total": it counts this screen, and Summary's Total counts the
plan. Two figures both called Total would read as a bug. A status may not be both `excluded` and
`review` — a case outside the plan is not work to review — and the validator refuses it.

Adding or renaming a status means editing only that JSON. Backend, `/api/statuses`, the UI and the
sample generator all read from it — never hard-code status keys in Python or JS.

**Scope groups are data too.** [parser/scope_groups.json](parser/scope_groups.json) says which
Scope strings belong to which Summary table, validated at import by `ScopeSet` in
[parser/scope.py](parser/scope.py) exactly the way `StatusSet` validates the taxonomy. FPT work
and JP work are separate commitments, so Summary draws one table per group rather than one table
adding them together. The `fallback` group is mandatory and always sorts last: a typo'd scope, or
one nobody has configured yet, lands there rather than vanishing, so **the tables always add up to
every case loaded**. `views/summary.js` names no scope itself — it draws a block per group from the
`scopes` list `/api/summary` serves alongside the rows.

**A blank Scope is not an unrecognised scope — it is not a case.** A section heading, a spacer, or
the slack at the end of a generously sized `start_row`–`end_row` block carries no Scope, and
`SCOPES.is_unscoped` in `parser/scope.py` is the one definition of that. The reader drops those
rows in `_cases_for_config` before a `TestCase` exists, so they reach no view, no aggregate and no
published report, and the per-file `cases: n` that `load_files` reports — the number the setup
drawer shows — is already net of them. Filtering later, per view, is what would let the drawer's
count and Summary's total disagree. `SCOPES.classify` stays total and still maps a blank onto the
fallback, so no caller can manufacture a case belonging to no table; it simply never sees one.

`summary_rows(cases, by_scope=False)` is one function serving two granularities. `/api/summary`
passes `by_scope=True` and each row gains a `scope` key; the report publisher does not, so its
sheet keeps one row per (file, device) and the SharePoint workbook needs no new column. They
cannot drift: the scope rows of a file add up to its unscoped row, which `tests/test_aggregate.py`
asserts directly.

**No CSS framework.** The UI is hand-written CSS in two files:
[static/css/tokens.css](static/css/tokens.css) holds every colour, type and spacing token
(light palette on bare `:root`, dark redefined under both `prefers-color-scheme` and
`[data-theme="dark"]`), and [static/css/app.css](static/css/app.css) holds the components.
The organising idea is **the ledger** — this tool sits between two spreadsheets, so the grid
is the structure. There is no `.card` and no `.panel`; the setup drawer and the empty state
are the only boxed surfaces. Tables are ruled, never framed.

**The interface has no accent colour.** Colour on screen always means *status*. Tabs, primary
buttons, selection and focus are rendered as inverted ink blocks, and the device/PIC charts use
a monochrome ink ramp — so a device breakdown can never be misread as a pass/fail one. Do not
introduce a brand or accent hue; it will collide with the five status tones.

**Frontend state ownership.** No framework, no bundler; `templates/index.html` loads
[static/js/main.js](static/js/main.js) as `<script type="module">`. An imported ES binding can't be
reassigned by the importer, so each piece of mutable state lives in exactly one module and is
reached through functions: taxonomy in `taxonomy.js`, cases/filters/page/expansion in
`views/detail.js`, daily rows in `views/daily.js`, per-PIC productivity rows in
`views/productivity.js`, Chart.js instances in `charts.js`, theme in `theme.js`.

`pagination.js` and `groupedTable.js` are self-contained widgets that **must not import any
view module** (circular). `groupedTable.js` takes the caller's rows, grouping keys and its own
`expanded` Set, and reports back through `onToggle`; build group paths with its `groupPath()`
rather than joining labels by hand, because the separator is a NUL.

**Never round-trip a group path through the DOM.** An HTML attribute is not a lossless
channel — the tokenizer rewrites U+0000 to U+FFFD in attribute values, so a path written to
`data-…` and read back off `dataset` no longer matches the one held in `expanded`, and the
chevron silently stops working with no error anywhere. The markup therefore carries only an
integer index (`data-group`) into a render-local `paths` array. Keep it that way: any identity
that must survive a click belongs in a JS array, not in an attribute.

Behavior worth preserving when touching the UI:
- `refreshViews()` in `main.js` must call `setTaxonomy()` before any header/card render.
- **Every** sortable header is now generated — `renderDailyHead`, `renderProductivityHead` and
  `renderDetailHead` each replace their `<th>`s and so each calls `makeSortable` itself. None is
  bound at init any more. Binding one twice sorts twice per click and looks like nothing happened.
  Summary is the exception in shape only: it has no `renderSummaryHead`, because it draws one
  table per scope group and cannot know how many headers it needs until the data arrives —
  `renderSummary` builds heads and bodies together and binds each head as it goes. Its sort state
  is shared across the tables and a click re-renders all of them, or two tables would show two
  different orders at once.
- Sorting a grouped table goes through `sortGrouped`, which orders the *groups* by their
  roll-up and the rows within each group. Sorting by "NG descending" must mean the worst file
  first, not the file that happens to own the worst row.
- Paging counts **groups**, not rows, wherever grouping is on (Daily always; Detail when the
  group-by control is set). A page that split a group would make its roll-up a lie.
- The productivity table sits inside `#dailyView` but ignores the daily filters on purpose —
  it reports over everything loaded, so it re-renders only on sort, never on filter change.
- Every table lives in a `.scroll-x` pane that has `overflow: auto` **and** a `max-height`.
  Both halves matter: the overflow makes the pane — not the viewport — the scrollport for
  the sticky `<thead>` and `<tfoot>`, and the height cap is what gives it something to
  scroll. Drop the cap and the pane grows to fit its content, nothing scrolls inside it, and
  a sticky header with a non-zero `top` gets pushed *down into* the rows instead of pinning.
  Headers therefore stick at `top: 0`, never at a measured viewport offset.
- `showView("detail")` calls `resizeCharts()`, and so does expanding the charts strip —
  Chart.js sizes to a 0×0 container while hidden.
- The Chart.js CDN `<script>` must stay before the module tag. Chart.js resolves colours at
  construction, so `theme.js` fires `onThemeChange` and `charts.js` rebuilds; a chart that is
  not rebuilt keeps the old palette.
- Every `fetch` lives in `api.js`; no view or panel module calls it directly.
- `reportPanel.js` mirrors `sourcePanel.js`: it owns where results *go* and knows nothing
  about the views. `refreshViews()` calls `setReportEnabled(true)` — publishing with nothing
  loaded would clear the day's rows and write none back, which the endpoint also refuses.
- `preparePanel.js` is the third of those panels: it owns *changing the source files* and also
  knows nothing about the views. It stays hidden until a load succeeds, because the file list it
  works from is the loaded source's, and its keep checkboxes are built from `/api/statuses` —
  never a status list written into the JS. Writing there means the workbooks no longer match
  what is loaded, so `onApplied` re-reads the source; `refreshViews()` takes `{close: false}` on
  that path, because pulling the drawer away mid-workflow would lose the user's place.
- `setupDrawer.js` owns chrome only. It opens itself when nothing is loaded and closes on a
  successful load; `sourcePanel.js`, `reportPanel.js` and `preparePanel.js` do not know it exists.
- `views/summary.js` must not import `views/detail.js`. It has no reason to now — the
  missing-reason list that used to jump into Detail has been removed from the screen, along with
  `initSummaryView`, `showCase` and the `onJumpToCase` callback. `/api/summary` still returns
  `missing_reason`; nothing draws it.

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

**`prepare/` is the only code that writes to the source workbooks.** Everything else treats
them as read-only. [prepare/tool_data.py](prepare/tool_data.py) gives a workbook the TOOL_DATA
sheet the reader needs — `parser/tool_data_builder.py` works out the layout from the labels in
[parser/sheet_labels.json](parser/sheet_labels.json), and this writes the result in —
while [prepare/clear.py](prepare/clear.py) empties last round's result cells.
[prepare/workbook.py](prepare/workbook.py) holds the one reader both need, and
[prepare/runner.py](prepare/runner.py) is the layer above: it walks a list of workbooks,
isolates the failures per file the way `load_files` does, and returns plain dicts. The three
`/api/prepare/*` endpoints are `jsonify` wrappers around it — the same arrangement as
`aggregate.py`, and for the same reason. Put new batch behaviour in `runner.py`, not in a route;
what stays in the route is what is genuinely about the request, which is the two guards below.
**The app is the only way in.** These operations once had argparse shells in `tools/`; they
were deleted once the drawer covered them, because two front doors to an irreversible write is
one more than the invariants above can be enforced at. `tools/` now holds only the sample
generator, which makes test data rather than touching anyone's. One consequence worth knowing:
`apply_plan` and `write_tool_data_sheet` still take an `out_path` — write to a copy instead of
overwriting — and no caller passes it any more. It is kept, and tested, as the escape hatch for
an irreversible operation.

Three rules hold across both operations, and each is enforced rather than trusted:

- **Nothing writes on one request.** `apply` defaults to false, so `/api/prepare/tool-data` and
  `/api/prepare/clear` answer with a plan — a detection, or a row count per device block — and
  the UI shows it. A cleared cell is not recoverable from the file, so the second, explicit
  request is the whole safety model.
- **A TOOL_DATA sheet that already exists is diffed, never assumed stale.** Someone may have
  corrected it by eye; detection is a best-effort first pass. `diff_configs` matches blocks on
  `(sheet, device)` and reports changed fields, so "Create TOOL_DATA" becomes "Check TOOL_DATA"
  once a workbook has one — and `preparePanel.js` only offers Apply when something would change.
- **Only the loaded source's files may be touched.** `_requested_files` in `api/routes.py`
  resolves the source through `runner.source_workbooks` and refuses any path not in it, so a
  stray path in a request body cannot reach a workbook the user never chose. A folder is
  re-globbed rather than remembered, so a file dropped in since the last load still appears.

`plan_sheet` classifies the **whole row** via `STATUS.classify_case`, not the Result cell alone.
That is what makes the keep set honest: `対象外` with a PIC is Cancel and `対象外` without one is
Out Of Scope, so keeping Cancel must not decide the fate of rows that were never in the plan.

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
