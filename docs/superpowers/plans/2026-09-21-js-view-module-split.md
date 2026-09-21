# JS View Module Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `static/js/views/detail.js` (1128 lines) and `static/js/views/summary.js` (969 lines) into focused modules without changing a single rendered pixel or a single line of behaviour.

**Architecture:** Each view becomes a directory of four modules layered by what they own: `state.js` holds the mutable state and is the only module that declares it; `filters.js` / `buckets.js` derive rows from that state and touch no DOM; `render.js` writes the DOM and reads state through `state.js`; `index.js` is the composition point — it binds listeners, orchestrates the refresh cycle, and re-exports the public surface `main.js` imports. Dependencies point one way: `index → render → {filters|buckets} → state`. Where a lower module needs to trigger a higher one, it takes a callback the higher one installs, which is the pattern already used by `setJumpHandler`, `onOpenFile`, `onDrillIn` and `onTargetChange`.

**Tech Stack:** Hand-written ES modules, no bundler, no framework, no JS test framework. Browsers resolve `import` paths literally.

**Spec:** [docs/superpowers/specs/2026-09-20-project-restructure-design.md](../specs/2026-09-20-project-restructure-design.md) — Phase 3.

## Global Constraints

- **Behaviour must not change.** This is a move, not a rewrite. Every function body is transplanted verbatim; only `import` / `export` lines and the callback seams named in this plan are new text.
- **Each piece of mutable state keeps exactly one owning module and is reached through functions.** An imported ES binding cannot be reassigned by the importer, so a `let` that two modules must both write is a bug. `state.js` is the owner; scalars are read and written through accessors, and `Map` / `Set` / array-valued state is exported directly because mutating a `Map` is not reassigning a binding.
- **No view imports another view.** `views/summary/**` must not import `views/detail/**`, and neither imports `views/file.js`. Cross-view navigation goes through the callbacks `main.js` installs.
- **The widgets import no view or panel module.** `pagination.js`, `groupedTable.js` and `filesTable.js` stay leaf modules.
- **No circular imports.** A cycle between the new modules is a defect even when the hoisting happens to make it work.
- **Browsers do not resolve directory indexes.** There is no bundler, so `./views/detail/index.js` must be written out in full in every importer. `./views/detail/` will 404.
- **`node --check` silently passes `.js` files.** Syntax-check a module by copying it to `.mjs` first.
- **The public surface is fixed.** After the split, `static/js/main.js` must import exactly the same names it imports today, and no other file may need editing.

---

## File Structure

**Created:**

| File | Owns |
|---|---|
| `static/js/views/detail/state.js` | detail's mutable state, the column and filter tables, the accessors |
| `static/js/views/detail/filters.js` | narrowing and sorting `allData` into `filtered`; no DOM writes |
| `static/js/views/detail/render.js` | every DOM write for the detail screen |
| `static/js/views/detail/index.js` | listeners, the refresh cycle, fetching, the public exports |
| `static/js/views/summary/state.js` | summary's mutable state, `BUCKETS`, `GROUPINGS`, the callbacks |
| `static/js/views/summary/buckets.js` | bucketing, grouping and row-combining transforms; no DOM writes |
| `static/js/views/summary/render.js` | every DOM write for the summary screen |
| `static/js/views/summary/index.js` | listeners, `renderSummary`, `alignSummaryColumns`, the public exports |

**Deleted:** `static/js/views/detail.js`, `static/js/views/summary.js`

**Modified:** `static/js/main.js` (two import paths), `CLAUDE.md`, `README.md`

---

## Task 1: Split the detail view

**Files:**
- Create: `static/js/views/detail/state.js`, `static/js/views/detail/filters.js`, `static/js/views/detail/render.js`, `static/js/views/detail/index.js`
- Delete: `static/js/views/detail.js`
- Modify: `static/js/main.js:32` (the import path only)
- Test: none — no JS test framework exists. Verification is the syntax check in Step 6 and the browser walkthrough in Task 3.

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `static/js/views/detail/index.js` exporting exactly these ten names, unchanged in signature —
  `initDetailView()`, `initDetail(summary)`, `enterDetail()`, `showReview()`, `showMissingReason()`,
  `showStatusCases(ctx)`, `reviewCount()`, `renderResultToggles()`, `renderDetailCards()`, `renderDetailHead()`.
  (`renderScopeCards` is exported by today's module but imported by nobody. Keep it exported from
  `render.js` and re-export it from `index.js` — removing a dead export is a separate decision, not
  this task's.)

### The function assignment

Move each function to the file named here. **Bodies are transplanted verbatim** — do not reformat, rename or "improve" them. Line numbers refer to today's `static/js/views/detail.js`.

**`state.js`** — every module-level binding in today's lines 62–200:

```
PAGE_SIZE, GROUP_PAGE_SIZE, DEFAULT_EXPANDED, COLUMNS, FILTERS, DATE_FILTERS   (const, exported as-is)
cache, chosenStatuses, chosenScopes, chosenRawScopes, expanded, detailSort      (Map/Set/object — exported as-is)
showAll, missingOnly, scopeGroups, summaryRows, allData, filtered,
conditions, pending, currentPage, loading, loadToken, stale                     (let — accessors, see below)
```

**`filters.js`** — `groupBy` (736), `applyFilters` (750), `matchesSearch` (793), `countsByScope` (687), `defaultScopes` (337), `clearNarrowing` (321)

**`render.js`** — `renderStats` (808), `renderChips` (852), `isSectionHeader` (943), `cellCls` (964), `td` (992), `caseCells` (1000), `emptyMessage` (1025), `groupValues` (1033), `renderTable` (1043), `renderResultToggles` (579), `paintResultToggles` (636), `renderScopeToggles` (597), `paintScopeToggles` (609), `renderDetailCards` (623), `renderScopeCards` (670), `paintScopeCards` (700), `renderDetailHead` (727), `paintMissingReason` (332)

**`index.js`** — `initDetailView` (205), `showReview` (349), `showMissingReason` (373), `showStatusCases` (411), `loadChosen` (452), `rebuild` (481), `reviewCount` (520), `initDetail` (539), `enterDetail` (568)

- [ ] **Step 1: Write `state.js`**

Create the directory and the state module. The scalars need accessors because an importer cannot reassign an imported binding; the collections do not, because `cache.set(...)` and `chosenStatuses.add(...)` mutate an object rather than rebind a name.

Carry each binding's existing JSDoc comment across with it — those comments are the reason the state is shaped the way it is, and they are the most valuable thing in the file.

```js
/**
 * Detail's state, and the only module that declares it.
 *
 * An imported ES binding cannot be reassigned by the importer, so a scalar two
 * modules both write is reached through the accessors below; a Map, Set or
 * object is exported directly, because mutating one is not rebinding a name.
 */

export const PAGE_SIZE = 50;

/** Groups per page once grouping is on. */
export const GROUP_PAGE_SIZE = 8;

export const DEFAULT_EXPANDED = true;

/**
 * Status key -> that status' cases, as `/api/cases` served them.
 *
 * The whole reason this screen is affordable. Cleared by `initDetail`, which
 * runs on every load and every config save — the cases behind a status can
 * change without anything here being clicked.
 *
 * @type {Map<string, Object[]>}
 */
export const cache = new Map();

/** @type {Set<string>} status keys chosen; also the fetch key. Empty shows nothing. */
export const chosenStatuses = new Set();

/** @type {Set<string>} scope group keys pressed. A filter over the cache, never fetched. */
export const chosenScopes = new Set();

/** @type {Set<string>} raw Scope strings pressed in the filter well. Empty means every scope. */
export const chosenRawScopes = new Set();

/** @type {Set<string>} which groups are open */
export const expanded = new Set();

/** @type {import("../../sorting.js").SortState} */
export const detailSort = { col: null, asc: true };

let showAll = false;
export const getShowAll = () => showAll;
export const setShowAll = (v) => { showAll = v; };

let missingOnly = false;
export const getMissingOnly = () => missingOnly;
export const setMissingOnly = (v) => { missingOnly = v; };

/** @type {{key: string, label: string, counted: boolean}[]} groups, from /api/summary */
let scopeGroups = [];
export const getScopeGroups = () => scopeGroups;
export const setScopeGroups = (v) => { scopeGroups = v; };

/** @type {Object[]} /api/summary rows — where the card figures come from */
let summaryRows = [];
export const getSummaryRows = () => summaryRows;
export const setSummaryRows = (v) => { summaryRows = v; };

/** @type {Object[]} the cached cases of the chosen statuses, within the chosen scopes */
let allData = [];
export const getAllData = () => allData;
export const setAllData = (v) => { allData = v; };

/** @type {Object[]} `allData` after the filters and the sort */
let filtered = [];
export const getFiltered = () => filtered;
export const setFiltered = (v) => { filtered = v; };

let conditions = { deviceFamily: "", sheet: "" };
export const getConditions = () => conditions;
export const setConditions = (v) => { conditions = v; };

/** @type {?Object} filter values a drill-in asked for, applied once its cases arrive. */
let pending = null;
export const getPending = () => pending;
export const setPending = (v) => { pending = v; };

let currentPage = 1;
export const getCurrentPage = () => currentPage;
export const setCurrentPage = (v) => { currentPage = v; };

let loading = false;
export const getLoading = () => loading;
export const setLoading = (v) => { loading = v; };

let loadToken = 0;
export const nextLoadToken = () => ++loadToken;
export const getLoadToken = () => loadToken;

/** Whether the cache was dropped since this view was last drawn. */
let stale = true;
export const getStale = () => stale;
export const setStale = (v) => { stale = v; };
```

Then append `COLUMNS`, `FILTERS` and `DATE_FILTERS` exactly as they appear at lines 148–194 of today's file, each with its full comment, prefixed with `export `.

- [ ] **Step 2: Write `filters.js`**

Move the six functions listed above, verbatim. Replace every bare reference to a scalar with its accessor — `filtered = ...` becomes `setFiltered(...)`, `missingOnly` becomes `getMissingOnly()`, and so on. Collections (`chosenRawScopes.size`, `detailSort`) are referenced unchanged.

`applyFilters`'s last four lines are its **only** DOM contact:

```js
    renderStats();
    renderChips();
    renderTable();
    renderCharts(filtered);
```

Delete those four lines from `applyFilters`. They move to `refresh()` in `index.js` (Step 4). This is what keeps `filters.js → render.js` from existing; without it the two modules import each other.

`applyFilters` therefore ends at `setFiltered(...)` and returns nothing.

Header:

```js
/**
 * Narrowing and sorting: `allData` in, `filtered` out.
 *
 * Nothing here touches the DOM. `applyFilters` used to end by calling the four
 * render functions; that tail now lives in `refresh()` in `index.js`, because a
 * filter module that called the renderer and a renderer that re-filtered on
 * sort would be a cycle.
 */
import { lacksReason } from "../../taxonomy.js";
import { sortGrouped, sortRows } from "../../sorting.js";
import { $ } from "../../dom.js";
import {
    DATE_FILTERS, FILTERS, chosenRawScopes, chosenScopes, chosenStatuses,
    detailSort, getAllData, getConditions, getMissingOnly, getScopeGroups,
    getSummaryRows, setFiltered,
} from "./state.js";
```

Adjust that import list to exactly what the six moved functions reference — no more, no less. Note every `../` became `../../`: these files are one directory deeper than the module they came from.

- [ ] **Step 3: Write `render.js`**

Move the eighteen functions listed above, verbatim, with the same accessor substitution.

Two functions call back into the refresh cycle and must not import `index.js`. `renderDetailHead` (line 727) ends:

```js
    makeSortable("#detailHead th.sortable", detailSort, () => { currentPage = 1; applyFilters(); });
```

and `renderTable`'s footer and group handlers do the same. Replace every such call with a module-local hook that `index.js` installs:

```js
/**
 * What to run when a control inside a rendered fragment changes the view.
 *
 * A callback rather than an import, for the reason `summaryOverview.js` takes
 * one: the renderer is below `index.js` in the dependency order, and reaching
 * up for `refresh` would make the two modules import each other.
 */
let onChanged = () => {};

/** Installed once by `initDetailView`. */
export function setOnChanged(fn) { onChanged = fn; }
```

so the line above becomes:

```js
    makeSortable("#detailHead th.sortable", detailSort, () => { setCurrentPage(1); onChanged(); });
```

Apply the same substitution everywhere a moved render function calls `applyFilters()` or `rebuild()`. Find them with:

```bash
grep -n "applyFilters()\|rebuild()" static/js/views/detail/render.js
```

Every hit inside a render function is an `onChanged()`. If a hit needs `rebuild()` rather than `applyFilters()` — i.e. it changes which cases are in hand, not merely which are shown — leave a second hook `onReload` and install it the same way. Check each call site against today's file before deciding; do not assume they are all the same.

- [ ] **Step 4: Write `index.js`**

Move the nine functions listed above, verbatim. Add the refresh orchestrator that `applyFilters` gave up in Step 2:

```js
/**
 * One narrowing pass and the four redraws that follow it.
 *
 * This is the tail `applyFilters` used to carry. It lives here because it is
 * the only place that legitimately knows about both halves.
 */
function refresh() {
    applyFilters();
    renderStats();
    renderChips();
    renderTable();
    renderCharts(getFiltered());
}
```

Every call to `applyFilters()` that today expects the redraw to follow becomes a call to `refresh()`. Inside `initDetailView`, install the hook before binding anything:

```js
    setOnChanged(refresh);
```

Re-export the public surface at the foot of the file:

```js
export {
    renderDetailCards, renderDetailHead, renderResultToggles, renderScopeCards,
} from "./render.js";
```

and leave `initDetailView`, `initDetail`, `enterDetail`, `showReview`, `showMissingReason`, `showStatusCases` and `reviewCount` as `export function` declarations in this file.

Carry across the whole 49-line header comment from today's `detail.js` lines 1–49 — it is the view's design rationale, and `index.js` is where a reader arrives.

- [ ] **Step 5: Delete the old module and repoint `main.js`**

```bash
git rm static/js/views/detail.js
```

In `static/js/main.js`, change line 32's specifier from `"./views/detail.js"` to `"./views/detail/index.js"` and leave the imported names untouched. **Write the path in full** — `"./views/detail/"` does not resolve in a browser.

- [ ] **Step 6: Syntax-check all four modules**

`node --check` silently passes `.js`, so copy each to `.mjs` first:

```bash
cd static/js/views/detail
for f in state filters render index; do cp $f.js /tmp/$f.mjs && node --check /tmp/$f.mjs && echo "OK $f"; done
rm -f /tmp/state.mjs /tmp/filters.mjs /tmp/render.mjs /tmp/index.mjs
```

Expected: four `OK` lines and no error output.

- [ ] **Step 7: Prove the public surface is unchanged**

```bash
cd /Users/lomahs/lomahs/Coding/test-management
git show HEAD:static/js/views/detail.js | grep -o "^export function [a-zA-Z]*" | awk '{print $3}' | sort > /tmp/before.txt
grep -ho "^export function [a-zA-Z]*" static/js/views/detail/index.js | awk '{print $3}' > /tmp/after.txt
grep -o "[a-zA-Z]*," static/js/views/detail/index.js | tr -d ',' >> /tmp/after.txt
sort -u /tmp/after.txt -o /tmp/after.txt
comm -23 /tmp/before.txt /tmp/after.txt
```

Expected: **no output.** Any name printed is an export that existed before and does not now — `main.js` would fail to import it, and the app would not boot.

- [ ] **Step 8: Check for cycles**

```bash
cd static/js/views/detail
grep -Hn "^import" state.js filters.js render.js index.js | grep "\./"
```

Expected shape, and nothing outside it:
- `state.js` — no `./` imports at all
- `filters.js` — `./state.js` only
- `render.js` — `./state.js` and `./filters.js` only
- `index.js` — any of the three

A `./index.js` appearing in `render.js` or `filters.js` is the cycle this task exists to avoid. Fix it with a callback, not with a lazy import.

- [ ] **Step 9: Commit**

```bash
git add static/js/views/detail static/js/main.js
git commit -m "Split the detail view into state, filters, render and index

1128 lines in one module, holding the case cache, the chosen statuses and
scopes, every narrowing, and every DOM write for the busiest screen in the
app. The four modules layer by what they own, and the dependency runs one
way: index -> render -> filters -> state.

applyFilters gave up its four-line render tail to refresh() in index.js,
and the render functions reach the refresh cycle through a callback
index.js installs rather than importing it, so no two modules import each
other. Behaviour is unchanged: every body is transplanted verbatim and
main.js imports the same ten names.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: Split the summary view

**Files:**
- Create: `static/js/views/summary/state.js`, `static/js/views/summary/buckets.js`, `static/js/views/summary/render.js`, `static/js/views/summary/index.js`
- Delete: `static/js/views/summary.js`
- Modify: `static/js/main.js:20` (the import path only)
- Test: none — verification is the syntax check in Step 6 and the browser walkthrough in Task 3.

**Interfaces:**
- Consumes: nothing from Task 1. The two views share no module and must not start.
- Produces: `static/js/views/summary/index.js` exporting exactly three names, unchanged in signature —
  `initSummaryView({onOpenFile, onDrillIn})`, `renderSummary(data, dailyRows)`, `alignSummaryColumns()`.

**Note on the file count.** The spec names three modules (`buckets`, `render`, `index`). This task creates four, adding `state.js` for the same reason detail has one: `groups`, `scopes`, `chosenScopes`, `sort`, `grouping`, `families`, `paging`, `noExpansion` and the two callbacks are written by `index.js` and read by both of the others, and a `let` cannot be written through an imported binding. Putting them in `index.js` would make `buckets.js` and `render.js` import it, which is the cycle Task 1 spent a callback to avoid.

### The function assignment

Line numbers refer to today's `static/js/views/summary.js`.

**`state.js`** — every module-level binding in today's lines 46–160: `PAGE_SIZE`, `BUCKETS`, `GROUPINGS`, `FILTERS`, `chosenScopes`, `sort`, `paging`, `noExpansion` (exported as-is — object or collection), and `groups`, `scopes`, `grouping`, `families`, `onOpenFile`, `onDrillIn` (accessors).

**`buckets.js`** — `filtered` (273), `combine` (289), `combineByFamily` (321), `pressedScopes` (391), `groupsOf` (398), `mergeByDevice` (423), `bucketRows` (445), `regroup` (820)

**`render.js`** — `asideChip` (360), `scopeTabs` (481), `chips` (510), `render` (535), `alignColumns` (650), `giveTiers` (711), `progressWidth` (725), `fitToPane` (745), `renderTable` (833), `linkFor` (920), `progressCell` (942), `renderFooter` (957)

**`index.js`** — `initSummaryView` (165), `renderSummary` (255), `alignSummaryColumns` (815)

- [ ] **Step 1: Write `state.js`**

Same shape as Task 1 Step 1: carry each binding's JSDoc across, export collections directly, wrap scalars in accessors.

```js
/**
 * Summary's state, and the only module that declares it.
 *
 * Same rule as `views/detail/state.js`: a scalar two modules both write is
 * reached through an accessor, because an imported binding cannot be
 * reassigned; a Map, Set or object is exported directly.
 */

const PAGE_SIZE = 10;

let groups = [];
export const getGroups = () => groups;
export const setGroups = (v) => { groups = v; };

let scopes = [];
export const getScopes = () => scopes;
export const setScopes = (v) => { scopes = v; };

/** @type {Set<string>} scope group keys pressed, across every bucket. */
export const chosenScopes = new Set();

/** @type {import("../../sorting.js").SortState} shared by every bucket's table. */
export const sort = { col: null, asc: true };

let grouping = "split";
export const getGrouping = () => grouping;
export const setGrouping = (v) => { grouping = v; };

/** @type {Object[]} device families, from /api/summary. */
let families = [];
export const getFamilies = () => families;
export const setFamilies = (v) => { families = v; };

/** @type {Map<string, number>} bucket key -> its page. Paging is per table. */
export const paging = new Map();

/** @type {Set<string>} */
export const noExpansion = new Set();

let onOpenFile = () => {};
export const getOnOpenFile = () => onOpenFile;
export const setOnOpenFile = (fn) => { onOpenFile = fn; };

let onDrillIn = () => {};
export const getOnDrillIn = () => onDrillIn;
export const setOnDrillIn = (fn) => { onDrillIn = fn; };
```

Then append `PAGE_SIZE`, `BUCKETS`, `GROUPINGS` and `FILTERS` exactly as they appear today, each with its full comment, prefixed with `export `. `BUCKETS`' comment explains why Summary draws one table per role rather than per group and must survive the move intact.

- [ ] **Step 2: Write `buckets.js`**

Move the eight transforms verbatim, substituting accessors. Nothing here writes to the DOM, and `document` must not appear in the file:

```bash
grep -c "document\|\$(" static/js/views/summary/buckets.js
```

Expected: `0`. If `filtered()` reads a filter `<select>` through `$("#summaryFilterDevice")`, that read stays — it is an input, not a write — but note it in the header comment so the boundary is honest rather than silently broken.

- [ ] **Step 3: Write `render.js`**

Move the twelve render functions verbatim. Install the same callback seam Task 1 used: any call to `render()` or `renderSummary()` from inside a rendered fragment's handler becomes `onChanged()`, with

```js
let onChanged = () => {};
export function setOnChanged(fn) { onChanged = fn; }
```

Find the call sites first:

```bash
grep -n "render()\|renderSummary(\|alignColumns()" static/js/views/summary/render.js
```

`alignColumns()` is internal to this module and stays a direct call; only reaches *out* of the module become hooks.

- [ ] **Step 4: Write `index.js`**

Move `initSummaryView`, `renderSummary` and `alignSummaryColumns` verbatim. `initSummaryView`'s two destructured callbacks are stored through `setOnOpenFile` / `setOnDrillIn` rather than assigned to module-level `let`s, and it installs the render hook:

```js
    setOnChanged(render);
```

Carry the 31-line header comment from today's `summary.js` lines 1–31 across to `index.js`.

- [ ] **Step 5: Delete the old module and repoint `main.js`**

```bash
git rm static/js/views/summary.js
```

In `static/js/main.js`, change line 20's specifier from `"./views/summary.js"` to `"./views/summary/index.js"`.

Then check nothing else referenced the old path:

```bash
grep -rn "views/summary\.js\|views/detail\.js" static/js/ templates/
```

Expected: only prose inside comments (`main.js:256`, `taxonomy.js:310`, `summaryOverview.js:36`, `templates/index.html:223`). Update those four comment references to the new paths — a comment naming a file that no longer exists is worse than no comment.

- [ ] **Step 6: Syntax-check and check for cycles**

```bash
cd static/js/views/summary
for f in state buckets render index; do cp $f.js /tmp/s_$f.mjs && node --check /tmp/s_$f.mjs && echo "OK $f"; done
rm -f /tmp/s_*.mjs
grep -Hn "^import" state.js buckets.js render.js index.js | grep "\./"
```

Expected: four `OK` lines, and the import graph running `index → render → buckets → state` with no back-edge.

- [ ] **Step 7: Prove the public surface is unchanged**

`main.js` imports exactly `alignSummaryColumns`, `initSummaryView` and `renderSummary`. Confirm all three are exported:

```bash
for n in alignSummaryColumns initSummaryView renderSummary; do
  grep -q "export function $n\|$n," static/js/views/summary/index.js && echo "OK $n" || echo "MISSING $n"
done
```

Expected: three `OK` lines.

- [ ] **Step 8: Commit**

```bash
git add static/js/views/summary static/js/main.js static/js/taxonomy.js static/js/views/summaryOverview.js templates/index.html
git commit -m "Split the summary view into state, buckets, render and index

969 lines holding the three role buckets, the Split/By-device-type/Combined
grouping, the shared sort, per-table paging and the column alignment pass.
buckets.js holds the transforms and touches no DOM; render.js holds every
write; state.js owns what both read.

Four modules rather than the spec's three: the state has to leave index.js
or buckets.js and render.js would import it, which is the cycle detail's
split already spent a callback to avoid.

main.js imports the same three names, and the four comments naming the old
file paths now name the new ones.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: Verify in a browser, then document

**Files:**
- Modify: `CLAUDE.md`, `README.md`
- Test: manual — the walkthrough below is the only verification these two tasks have.

**Interfaces:**
- Consumes: the eight modules from Tasks 1 and 2.
- Produces: nothing code depends on.

- [ ] **Step 1: Run the Python suite**

The split touches no Python, so this proves only that nothing was collaterally broken. Run it anyway — it is cheap and it is the baseline the next step assumes.

```bash
.venv/bin/python -m pytest -q
```

Expected: 484 passed.

- [ ] **Step 2: Start the app and walk every view**

```bash
.venv/bin/python app.py
```

Open http://127.0.0.1:5000 and load the sample workbooks. **Open the browser console first and keep it visible** — an ES module that fails to resolve fails silently on the page and loudly in the console, and a 404 on `views/detail/index.js` is the single most likely mistake in this plan.

Walk all seven views, in both light and dark themes:

| # | Check | What a failure looks like |
|---|---|---|
| 1 | Summary: all three buckets draw; scope cards inside a multi-group bucket toggle | a bucket missing, or a card that does not invert when pressed |
| 2 | Summary: Rows cycles Split → By device type → Combined, and the totals do not move | a total that changes with the grouping |
| 3 | Summary: sort a column — every bucket's table re-sorts together | two tables showing two orders |
| 4 | Summary: Prev / Next / Show all in one bucket leaves the others alone | paging that moves every table |
| 5 | Summary: press a KPI card and a result-breakdown line — both open Detail | nothing happens; console shows an import error |
| 6 | Summary: press a figure in a status band — Detail opens on that status | Detail opens empty |
| 7 | Detail: press a status card, then a second — both statuses list, no double-counting | a case listed twice |
| 8 | Detail: press a scope card, including an excluded one — its dashed border survives the press | the dashed border disappearing when pressed |
| 9 | Detail: the File / Device / PIC selects, the date bounds and the search box each narrow the table, and each leaves the status cards where they are | a card figure moving when you type in the search box |
| 10 | Detail: each narrowing gets a chip; pressing a chip's ✕ drops it | a chip that does not clear |
| 11 | Detail: Clear all leaves the statuses and the scopes pressed | an empty table after Clear all |
| 12 | Detail: set the group-by control, expand and collapse a group | a chevron that does nothing — the group-path-through-the-DOM bug |
| 13 | Detail: sort, then page — paging counts groups, not rows | a page that splits a group |
| 14 | Detail: the charts strip expands and the charts size correctly | charts drawn 0×0 |
| 15 | Daily: the CSS bar chart, its dashed plan line, and grouping | the chart empty while the table has rows |
| 16 | Productivity: renders and sorts | — |
| 17 | File: click a file name on Summary and in Tools; Back returns you where you came from | Back going to the wrong view |
| 18 | Tools: source, report and prepare panels; the merged file table | — |
| 19 | Config: edit a status label, save, and watch Summary's heading change | a save that validates but changes nothing on screen |
| 20 | Toggle the theme on every view — charts rebuild with the new palette | a chart keeping the old palette |

**The console must be empty of errors at the end of the walk.** Anything printed is a finding; stop and fix it before Step 3.

- [ ] **Step 3: Update `CLAUDE.md`**

Every path that named the two old modules now names a new one. Find them:

```bash
grep -n "views/detail\.js\|views/summary\.js" CLAUDE.md
```

Rewrite each. The **Frontend state ownership** paragraph needs more than a path swap — it currently reads:

> the per-status case cache and the chosen statuses/scopes/filters/page/expansion in `views/detail.js`

and must now say that detail's state lives in `views/detail/state.js`, summary's in `views/summary/state.js`, and that the accessor pattern is why: a `let` cannot be written through an imported binding, so the owning module exports a getter and a setter and the other three modules never declare a copy.

Add a short paragraph after it recording the dependency direction and the callback seam:

> **Each split view is four modules, layered one way.** `state.js` declares the
> mutable state and nothing else; `filters.js` / `buckets.js` derive rows from it
> and write no DOM; `render.js` writes the DOM; `index.js` binds the listeners and
> owns the refresh cycle. Imports run `index → render → {filters|buckets} → state`
> and never back — where a rendered fragment's handler has to re-run the cycle it
> calls a hook `index.js` installed through `setOnChanged`, the same shape as
> `setJumpHandler` and `onOpenFile`. A back-edge would be a cycle, and the reason
> `applyFilters` no longer ends by calling the four render functions.

- [ ] **Step 4: Update `README.md`**

The Vietnamese structure tree lists `static/js/views/`. Replace the two file entries with the two directories and their four modules each, keeping the surrounding Vietnamese prose style.

```bash
grep -n "detail.js\|summary.js" README.md
```

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "Record the split view modules in CLAUDE.md and README

Names the four-module shape, the one-way import order, and the setOnChanged
seam that keeps render.js from reaching back into index.js.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```
