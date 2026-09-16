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

**`"review": true` is what the Review view holds.** Review (still `#detailView` / `views/detail.js`
in the code) is the list of work outstanding, so it loads *only* those statuses (NG / NG-OK /
Pending / Cancel) and drops everything else at `initDetail`. That is a deliberate restriction, not
a default filter — which is why its stat strip is labelled **"To review"** and not "Total": it
counts this screen, and Summary's Total counts the plan. Two figures both called Total would read as a bug. A status may not be both `excluded` and
`review` — a case outside the plan is not work to review — and the validator refuses it.

Adding or renaming a status means editing only that JSON. Backend, `/api/statuses`, the UI and the
sample generator all read from it — never hard-code status keys in Python or JS.

**Those JSON files are editable from the app, and an edit applies without a restart.**
[config_store.py](config_store.py) is the one place that writes them — `config.py` says *where*
each file is, this says how to check an edit, how to write it, and how to make it take effect.
`/api/config` and `PUT /api/config/<name>` are `jsonify` wrappers around its two functions, the
same arrangement as `aggregate.py` and `prepare/runner.py`. Four things about it are load-bearing:

- **Validation is not written twice.** An edit is checked by building a throwaway instance through
  the config class's own `from_dict`, so every invariant above holds for an edit made from the
  browser without a second copy of the rules to drift from the first. The 400 carries the config
  class's own message, because it names the invariant that broke.
- **Nothing is written until it validates, and the write is atomic.** A half-written
  `result_status.json` does not make the taxonomy wrong, it stops the app booting —
  `_load_default` raises at import. So the text goes to a temp file beside the target and
  `os.replace` swaps it in.
- **`adopt` is why one save reaches everything.** `STATUS`, `SCOPES`, `DEVICES` and `LABELS`
  are imported *by name* into eight modules, and rebinding the name in `parser.status` would
  reach none of them.
  So each class has an `adopt(other)` that copies the validated state onto `self`: the singleton
  stays the singleton and its contents change. `SheetLabels` is no longer a frozen dataclass for
  this reason — config you can edit at runtime is not frozen. No source re-read is needed, because
  `classify_case` and `SCOPES.classify` both run per request.
- **Saving the taxonomy rebuilds `LAYOUT`.** `{"expand": "statuses"}` is materialised into columns
  when the report layout is *built*, which happens once at import — so without that step a
  taxonomy edit would leave the publisher writing the column set the old taxonomy had.

`report/report_layout.json` is deliberately **not** editable from the app: its columns are the
geometry of someone's report workbook rather than a vocabulary. It is only ever rebuilt.

**Scope groups are data too.** [parser/scope_groups.json](parser/scope_groups.json) says which
Scope strings belong to which Summary table, validated at import by `ScopeSet` in
[parser/scope.py](parser/scope.py) exactly the way `StatusSet` validates the taxonomy. FPT work
and JP work are separate commitments, so Summary draws one table per group rather than one table
adding them together. The `fallback` group is mandatory and always sorts last: a typo'd scope, or
one nobody has configured yet, lands there rather than vanishing, so **the tables always add up to
every case loaded**. `views/summary.js` names no scope itself — it draws a block per group from the
`scopes` list `/api/summary` serves alongside the rows.

**`"excluded": true` on a scope group is the same word, and the same idea, as it is on a status:
work that is reported but not committed to.** It keeps its Summary table — the count has to stay
visible, so the card is drawn in full and marked `chip--aside`, the dashed rule that means "the
sum stops here" — and it leaves *every figure that adds groups together*: the KPI strip, Daily,
Productivity, Review and the published report. `in_plan(cases)` in [aggregate.py](aggregate.py)
is the one definition of "counts toward the total", and `SCOPES.counted` / `SCOPES.is_counted`
the one definition of which groups do. Three things follow, and each is enforced rather than
trusted:

- **`summary_rows` does not filter, and must not start.** It is the only aggregate whose output
  is drawn per group, so filtering it would delete the table instead of the figure. The report
  publisher passes `in_plan(cases)` at the call site instead; `daily_rows`, `productivity_rows`
  and `issue_rows` apply it themselves, because a figure is all they produce. That also keeps
  the invariant `tests/test_aggregate.py` asserts — a file's scope rows add up to its unscoped
  row — true of whatever list `summary_rows` is handed.
- **Review drops those cases too**, which is the direct reading of the rule that a status may
  not be both `excluded` and `review`: a case outside the plan is not work to review. `/api/data`
  is where that happens. For the same reason `/api/summary` filters `missing_reason` — the KPI is
  a *link* into Review, and a count of rows the destination cannot show would send the reader to
  an empty table. That is why `missing_reason` rows now carry `scope`, as `issue_rows` always did.
- **The fallback group may not be excluded.** It is where a typo'd or unconfigured scope lands, so
  excluding it would let a mistake drop out of every figure in the app without saying so — the
  precise silence the fallback exists to prevent. It is also what guarantees at least one group
  always counts.

**Device families are data too, and they are the one config with no fallback.**
[parser/device_groups.json](parser/device_groups.json) says which device names Summary's
"By device type" rows add together — `iPhone Min size` and `iPhone Max size` are two device
blocks in a workbook but one handset to anyone reading the totals — validated at import by
`DeviceSet` in [parser/device.py](parser/device.py) the way `ScopeSet` validates the scopes.
Two things differ from `ScopeSet`, and both follow from what a device name is. **Matching is by
substring**, because a device name is written freehand and carries the model, the size and
sometimes the OS version, so nobody will enumerate the spellings; order therefore decides, and
a token that *contains* an earlier one is refused rather than shipped as a rule that can never
fire (`Phone` above `iPhone` is a typo — `iPad mini` above `iPad` is not, and is allowed).
**There is no fallback family**: a device no family claims is its own family, keyed and
labelled by its own name, so the merged table names every device it did not merge and still
adds up to exactly what Split shows. A catch-all would put an Android and a Windows box on one
row and call the result a device. `summary_rows` attaches `device_family` to **every** row,
beside `device` and regardless of `by_scope`, so the screen and the published report read one
classification; the merge itself is client-side, in `combineByFamily`.

**A blank Scope is not an unrecognised scope — it is not a case.** A section heading, a spacer, or
the slack at the end of a generously sized `start_row`–`end_row` block carries no Scope, and
`SCOPES.is_unscoped` in `parser/scope.py` is the one definition of that. The reader drops those
rows in `_cases_for_config` before a `TestCase` exists, so they reach no view, no aggregate and no
published report, and the per-file `cases: n` that `load_files` reports — the number the Tools
view shows — is already net of them. Filtering later, per view, is what would let that
count and Summary's total disagree. `SCOPES.classify` stays total and still maps a blank onto the
fallback, so no caller can manufacture a case belonging to no table; it simply never sees one.

**`file_rows(cases, file_name)` is Summary cut one level finer, and the only aggregate that
keeps work outside the plan.** It groups one workbook by (sheet, scope, device), which is
`summary_rows(by_scope=True)` with the sheet added, so a file's sheet rows add up to its
Summary rows — `tests/test_aggregate.py` asserts it directly, the same property that pins the
scope rows to the unscoped one. Two things differ from every other aggregate, and both follow
from the page being *about one workbook* rather than about progress: it does not run through
`in_plan`, because the file page draws a Scope column and a Scope filter and a filter whose
only option is FPT is not one; and its sheets stay in the order the workbook names them rather
than sorted, the way `issue_rows` keeps source order, so the table reads alongside the file's
own tabs. It returns that file's cases too, each carrying the `status` it classified as and
the `scope_group` it belongs to — `scope_group` rides along for the reason `device_family`
does, so the page filters its rows and its cases through one vocabulary instead of two.
`/api/file?name=<basename>` is the `jsonify` wrapper; the name is a query parameter because
workbook names carry spaces and Japanese, and a name nothing loaded answers to is a 404. It is
deliberately **not** part of `fetchAll`: fetched on demand, its cost is the one file clicked
rather than every case of every workbook on every load.

`summary_rows(cases, by_scope=False)` is one function serving two granularities. `/api/summary`
passes `by_scope=True` and each row gains a `scope` key; the report publisher does not, so its
sheet keeps one row per (file, device) and the SharePoint workbook needs no new column. They
cannot drift: the scope rows of a file add up to its unscoped row, which `tests/test_aggregate.py`
asserts directly.

**No CSS framework.** The UI is hand-written CSS in two files:
[static/css/tokens.css](static/css/tokens.css) holds every colour, type and spacing token
(light palette on bare `:root`, dark redefined under both `prefers-color-scheme` and
`[data-theme="dark"]`), and [static/css/app.css](static/css/app.css) holds the components.
The organising idea is still **the ledger** — this tool sits between two spreadsheets, so the
grid is the structure. Rows are ruled and cells are square: a curve inside a run of figures is
noise.

**Curvature is a scale, and it means distance from the data.** `--r-sm` (6px) for inputs and
small in-cell buttons, `--r-md` (7px) for buttons and rail nav items, `--r-lg` (10px) for cards
and table panes, `--r-full` for badges and result toggles — things whose whole job is to be
pressed, or read as a token. Reaching for a literal `border-radius` instead of a token is what
makes an interface look assembled rather than designed. Two consequences worth knowing, because
each reverses an earlier rule:

- **Tables are now framed.** Each `.scroll-x` is a rounded, hairline-bordered pane, and its
  `overflow` clips the sticky `<thead>`/`<tfoot>` into the corners. The pane is
  `width: max-content` capped at `100%` — the ledger still hugs its columns, so a full-width
  pane would leave the border floating right of the last column on a narrow table, while the
  cap is what still makes it scroll once the status band outgrows the screen.
- **Boxed surfaces exist.** The Tools panels, the stat cards, the filter well, the chart tiles
  and the Summary overview are all framed. The distinction the scale draws is that a summary
  *of* the data may have a frame and the rows themselves may not.

Framing is a hairline, not a shadow. `--shadow-1/2/3` survive as a scale but almost nothing uses
them now: with no floating surface left in the app — the drawer became the Tools view — a border
is what marks an edge. The shadow colour is a literal rather than a mix of `--ink`, because
`--ink` inverts in dark mode and a light shadow is not a shadow.

**The type stack is IBM Plex Sans + Noto Sans JP, and that pairing is the one compromise in it.**
The status labels are bilingual ("Pending (保留)"), so Latin and CJK sit inside one string and must
agree on x-height and weight. Plex has no CJK. Plex Sans JP would be the in-family companion, but
Noto Sans JP is what agrees with the Noto already in the stack — so it is a pairing, not a family,
and that is what it gives up. **Counts are set in Plex Mono**: `.num` carries `--font-mono` with
`tabular-nums`. That reverses an earlier decision, deliberately — the design uses the mono face
throughout to mark what is a figure, and at these row densities the distinction does real work,
telling you which columns you can compare down the page and which you can only read. `--font-mono`
also still carries what is genuinely code: case numbers, paths, Excel column letters.

**The interface has no accent colour.** Colour on screen always means *status*. Nav selection,
primary buttons, selection and focus are rendered as inverted ink blocks (inside the rail, as
`--rail-hover` blocks — the ground there is already ink), and the device/PIC charts use a
monochrome ink ramp, so a device breakdown can never be misread as a pass/fail one. Do not
introduce a brand or accent hue; it will collide with the five status tones. **The design canvas
this palette came from has one** — a green primary, `#1F6F5C`, a few degrees from OK's own
`#2E7D5B` — and it was deliberately not adopted. That is the collision this rule exists to
prevent, and it is the one place the implementation departs from the canvas on purpose.

The one exception is `.btn-danger` on the prepare panel's Apply: the only control in the app that
destroys something a file cannot give back, and the only one allowed to carry a status colour.

**Frontend state ownership.** No framework, no bundler; `templates/index.html` loads
[static/js/main.js](static/js/main.js) as `<script type="module">`. An imported ES binding can't be
reassigned by the importer, so each piece of mutable state lives in exactly one module and is
reached through functions: taxonomy in `taxonomy.js`, cases/filters/page/expansion in
`views/detail.js`, daily rows in `views/daily.js`, per-PIC productivity rows in
`views/productivity.js`, Chart.js instances in `charts.js`, theme in `theme.js`,
the daily target in `target.js`, the working copy of each config file in `views/config.js`.

**`target.js` holds the one number nobody reads out of a workbook.** Cases per person per day —
the yardstick the Daily chart's plan line, the daily log's Plan and Attain columns and
Productivity's attainment bar are all derived from. It has no endpoint, no aggregate and writes
nothing: Productivity owns the *input*, `target.js` owns the *value*, and Daily redraws through
`onTargetChange`. It is kept in `localStorage` (the design canvas keeps it in component state,
which forgets it on reload — a standing figure retyped every morning is how it ends up wrong).
`planFor(members)` returns 0 when nobody worked, so a day with no named PIC has no plan rather
than a plan of zero it can never meet.

**The shell is a rail and seven views, one of which is not in the rail.** `shell.js` owns the dark sidebar — nav, the loaded-source
card, the two counts it carries, and the page heading — and nothing else; it does not know what a
view contains, so `main.js` hands it an `onNavigate` callback and it reports clicks back through
that. `main.js` owns `VIEWS`, which is the single list of what exists: Summary, Daily,
Productivity, Review, File, Tools and Config. Adding a view means adding an entry there and a
`<section class="view" id="<name>View">`, and nothing else.

**File is the one view with no nav item.** It is a drill-in: it reports on a workbook you
picked, so it is entered by clicking a file name and left through the Back button it draws
itself, and nothing in the rail is lit while it shows. That is also why its `title` is a
function rather than a string — the heading is the workbook — and why `main.js`, which owns
navigation, holds the open file name and the view to go back to rather than `views/file.js`
holding them. Two places name a file: Summary's File cells and the Tools table. Neither
imports the file view; each reports the name back through a callback (`onOpenFile`, and
`filesTable`'s existing `onAction` with an `"open"` action), the same rule that keeps
`views/detail.js` out of `views/summary.js`. `ALWAYS_ENABLED` in `shell.js` is the
other half of that list: Tools and Config answer something with nothing loaded, so they are never
disabled, and the four data views are.

`pagination.js`, `groupedTable.js` and `filesTable.js` are self-contained widgets that
**must not import any view or panel module** (circular). `groupedTable.js` takes the caller's rows, grouping keys and its own
`expanded` Set, and reports back through `onToggle`. Its `renderValues(row, index, depth)` gets
the nesting level — `index` is -1 on a group row, `depth` is 0 on the outermost — which is what
lets Daily put Plan, Attain, Members and Cumulative on the date rows and leave them blank on the
device and PIC rows beneath. A plan for one device of one file is not a figure anyone set.
Build group paths with its `groupPath()`; build group paths with its `groupPath()`
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
- **Productivity is its own view, not a second table under Daily.** It reports over everything
  loaded and never answered to Daily's filters; sitting beneath them implied that it did. It
  re-renders only on sort, never on filter change.
- **`.scroll-x--rows` caps a pane at about ten rows** (`--rows`, plus two steps of slack for the
  header and totals row). That is what makes "Show all" a reasonable offer: every row renders and
  the *pane* scrolls, rather than the page growing to three thousand rows. It is also why a card
  keeps its footprint as you page — one that changed height on every Next would move everything
  under it. Summary's and Review's tables both use it.
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
  knows nothing about the views. Its controls stay hidden until a load succeeds, because the file
  list they work from is the loaded source's, and its keep checkboxes are built from
  `/api/statuses` — never a status list written into the JS. They are rebuilt on every
  `refreshPrepare`, not once at init, because the Config view can rename or remove a status while
  the app runs; `readKeep` filters the remembered set against the taxonomy as it stands now, so a
  key that no longer exists cannot be sent to an endpoint that would refuse it. Writing to the
  workbooks means they no longer match what is loaded, so `onApplied` re-reads the source;
  `refreshViews()` takes `{show: false}` on that path, because throwing the user onto Summary
  mid-workflow would lose their place.
- **One list of workbooks is one table, and `filesTable.js` is it.** `sourcePanel` knows what each
  file contributed to the load; `preparePanel` knows its TOOL_DATA state and what may be done to
  it. They used to say that in two tables, one under the other, listing the same files twice. So
  the table is a self-contained widget in the mould of `pagination.js` and `groupedTable.js` — it
  **imports no panel module**, both panels feed it (`setLoadResults` / `setPrepareFiles`), and it
  reports a pressed row button back through `onAction`, which `main.js` routes to
  `runFileAction`. That is what let the two Tools cards merge without either panel learning the
  other exists. The two halves arrive one round trip apart and are joined **on the path, not the
  file name**: `find_workbooks` is recursive, so two subfolders may each hold a `TC.xlsx` — which
  is why `load_files` reports `path` alongside `file`. A row addresses its workbook by index into
  a render-local array, never through a `data-` attribute.
- **Tools is where those panels live, and it is a view like any other.** It was a drawer
  pulled over the app; making it a view removed the scrim, the focus trap, the escape key and the
  open/closed state that all the panels had to be kept in step with. It is also the empty state:
  the app opens on Tools, because with nothing loaded it is the only screen that can answer
  anything. `sourcePanel.js`, `reportPanel.js` and `preparePanel.js` still know nothing about it,
  or about each other.
- **Config is a view, not a fifth Tools card**, because all four files are editable whether or
  not anything is loaded. `views/config.js` follows the panels' rule and knows nothing about the
  other views: saving the taxonomy changes what every figure on screen *means*, so `main.js` owns
  that consequence through `onSaved` and redraws with `{show: false}` — which is why it now holds
  the last load result. Three things about the form itself:
  - **It names no vocabulary of its own.** Tones, derive conditions and the sheet-label field
    names all arrive in `/api/config`'s `vocabulary`, the same rule that keeps status keys out of
    the JS. A form offering a tone the validator refuses is worse than no form.
  - **It edits the file, not a model of the file.** Each row holds the raw object it was drawn
    from and mutates only the fields it owns, so the legacy `badge` and `text` keys survive a save
    instead of being silently dropped. Dirtiness is `JSON.stringify` against the last known
    on-disk text, so reordering counts as a change — which it is.
  - **`empty` and `fallback` are one pick each for the whole taxonomy**, so they are two selects
    under the table rather than two columns of radios: as columns they were eight controls of
    which one mattered, and they cost the Derives-from column its place on screen.
- **Summary is laid out as the design canvas draws it**: five KPI cards, a grid of panels
  (result breakdown, today's progress, what owes a reason), then one card per scope group. Each
  card carries the design's chrome — Device and File selects, a three-state Rows toggle, an
  Executed progress column, condition chips and a Prev/Next/Show-all footer. **The one control
  the design has and this does not is the Scope select**, because the scope is the heading of the
  card you are already reading; collapsing FPT and JP into one filtered table is the thing the
  scope-group rule forbids. The filters are shared across cards for the reason the sort is —
  "iPad only" should mean the same thing in both — and paging is not, because a page number only
  means something inside one table. **Rows cycles Split → By device type → Combined**, and none
  of the three changes a total — only how many rows carry it. `combine()` sums every device of a
  file; `combineByFamily()` sums the ones sharing a `device_family` and titles the row from the
  `device_families` list `/api/summary` serves, so the view names no device of its own — the same
  rule that keeps status keys out of the JS. Both report how many devices they summed: a Device
  cell reading "iPad" on a row that also counts an iPhone would be a lie, and "iPhone" standing
  for two blocks is true but worth knowing.
- **Daily leads with a CSS bar chart, not Chart.js.** Executed per day against a dashed plan
  line, drawn as divs: it repaints on every filter change and every theme change, and a canvas
  that resolves its colours at construction is what `charts.js` exists to work around. Unlike the
  design's, it answers to the filters above it — a chart contradicting the table beneath it is
  worse than a chart with a narrower question. Cumulative is computed in date order regardless of
  how the table is sorted, because a running total that reversed with the sort would not be one.
- **Review's stat cards are controls.** Each filters the table to its own status and the first
  clears that filter; clicking the pressed one clears it too, so the row is also the way back out.
  They count over `conditioned` — every filter applied *except* the status choice — not over
  `filtered`: a card is the way to pick a status, so its figure has to say how many there are to
  pick. A "To review" card dropping to 256 the moment NG is chosen would be counting the choice it
  is offering to change. `Files` is the exception and counts what is on screen. The Result toggles
  inside the folded filter panel edit the same `chosenStatuses` set one at a time — the cards are
  the single pick, the toggles the combination the cards cannot express.
- `views/summary.js` must not import `views/detail.js`. The missing-reason list that used to
  jump into Detail took `showCase` and the `onJumpToCase` callback with it when it went.
  **`missing_reason` reaches the screen as the "Missing reason" KPI figure**, which is a link:
  the list of those rows was drawn as an at-risk panel and has since been removed, because
  Review can show them properly. Both navigating cards ("To review" and "Missing reason") go
  through `setJumpHandler`, a callback `main.js` installs — `main.js` owns the views, so a card
  that navigates is not a reason to put the import back. A card may also name a *filter*
  (`data-filter`), which `main.js` translates into a call on whichever module owns that view's
  state — `showMissingReason()` in `views/detail.js`.
- **`lacksReason(d)` in `taxonomy.js` is the one definition of "owes a reason and has
  none"**: `requiresReason(status) && !ticket_id && !note`. It paints the Ticket ID and Note
  cells red *and* drives the Missing reason filter, and it is the browser-side twin of what
  `/api/summary` computes for `missing_reason`. It lives with the taxonomy it reads because
  Review and the file page both ask it, and two copies is how they would come to disagree. Which statuses oblige an explanation stays the
  taxonomy's business (`needs_reason`), never named in the JS. The filter is a **condition, not a
  status choice** — it narrows within whatever results are chosen, so it lives beside the Result
  toggles and is applied to `conditioned`, which is why the status cards keep counting correctly
  underneath it. One consequence worth knowing: Review's figure can be smaller than the KPI's,
  because `needs_reason` may name a status that is not a `review` one, and such a case is not in
  that view at all.
- **`renderPageFooter` in `pagination.js` is the footer Summary and Review share.** Count on the
  left, `Prev · n / m · Next` and a Show-all on the right. Two footers that drifted would be two
  different answers to "is this all of it", so the markup and the paging arithmetic live in the
  widget, not in either view. It imports no view module, like everything else in that file.
- **`views/summaryOverview.js` owns the strip above the tables**, and owns none of
  `summary.js`'s state. It is drawn from `renderSummary` rather than from `render()`, because
  it reports over every row regardless of order — re-sorting a table must not redraw it.
  Everything in it is derived: the figures from `sumRows` over the same `/api/summary` rows the
  tables draw (so the strip cannot disagree with the numbers beneath it), the activity line
  from `/api/daily`, which `main.js` already holds. No endpoint was added for it.
- **The progress bar expands over `STATUS.counted`, the way the report's columns do.** An
  excluded status is absent from it: `total` does not include it, and a bar that failed to fill
  its own track would read as a rendering bug rather than as the deliberate gap the table's
  dashed `band--aside` rule makes explicit. Segments are painted with `colourFor`, the same
  stepped-tone function the charts use, so the bar and the doughnut cannot drift apart.
- **The headline figure is "Executed", never "Done".** It counts `STATUS.executed`, and an NG
  is work carried out that is not a pass — "70% done" beside a red NG column is a claim the
  reader has no way to check. For the same reason the day-on-day figure is *per-day activity*
  rather than a cumulative delta: `daily_rows` drops undated cases, so a running total taken
  from it would not reconcile with Summary's total. Its label names the day being compared
  *against*, not the latest one.

**Aggregation is shared, not owned by the routes.** [aggregate.py](aggregate.py) holds
`summary_rows` / `daily_rows` / `productivity_rows` / `issue_rows` as plain functions over
`TestCase` lists. The five GET endpoints are `jsonify` wrappers around them, and the report
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
were deleted once the Tools view covered them, because two front doors to an irreversible write is
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
