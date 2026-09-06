# Refactor for readability & maintainability

## Context

`static/js/app.js` has grown to 586 lines inside a single IIFE. It mixes DOM lookups, HTTP calls,
shared mutable state, three independent view renderers, sorting, pagination, and Chart.js setup
with no internal boundaries — every function can reach every variable, so changing one view risks
breaking another. It also carries no JSDoc.

The Python side is in better shape (most non-obvious functions already have docstrings) but has
gaps: `parser/models.py` documents none of its dataclass fields, and several loader/route/generator
functions are undocumented.

Goal: split `app.js` into small single-purpose ES modules, document the functions that aren't
self-explanatory, and change **no behavior**. The UI must look and act identically afterward.

Decisions confirmed with the user:
- **ES modules**, loaded via `<script type="module">` — no build step, Flask serves them as-is.
- Document **JS + the Python gaps**; leave already-documented functions alone.
- **No JS test framework.** Verify by running the app and exercising every view.

---

## Part 1 — Split `static/js/app.js` into ES modules

Delete `app.js` at the end; `main.js` becomes the entry point.

### The state problem (read this first)

The current code works because everything shares module-level `let` bindings: `allData`,
`filtered`, `currentPage`, `dailyData`, `charts`, `statuses`, `needsReason`, `badgeOf`. An imported
ES-module binding **cannot be reassigned by the importer**, so a naive split breaks at runtime.

Do **not** solve this with a global store object. Instead give each piece of state to the one module
that owns it, and export functions rather than variables:

| State | Owner | Exposed as |
|---|---|---|
| `statuses`, `needsReason`, `badgeOf` | `taxonomy.js` | `setTaxonomy()`, `getStatuses()`, `badgeFor()`, `requiresReason()` |
| `allData`, `filtered`, `currentPage` | `views/detail.js` | `initDetail()`, `applyFilters()` |
| `dailyData` | `views/daily.js` | `initDaily()` |
| `charts` | `charts.js` | `renderCharts()`, `resizeCharts()` |

### Target layout under `static/js/`

| File | Contents (moved from `app.js`) | ~size |
|---|---|---|
| `main.js` | entry point; view-tab wiring + `showView`; orchestrates fetch → render | ~70 |
| `dom.js` | `$`, `$$`, `esc` | ~20 |
| `api.js` | every `fetch` call: `postLoad`, `postReload`, `fetchAll` (the `Promise.all`) | ~50 |
| `sourcePanel.js` | source selector, `localStorage` restore/save, `doLoad`, `doReload`, `renderFileResults` | ~110 |
| `taxonomy.js` | taxonomy state + `sumRows`, `statusCells`, `statusTextClass`, `renderStatCards` | ~90 |
| `sorting.js` | `makeSortable`, `sortRows` | ~45 |
| `filters.js` | `uniqueOf`, `populateSelect` (shared by daily + detail) | ~30 |
| `pagination.js` | `pageNumbers` (pure), `renderPagination` | ~55 |
| `charts.js` | `COLORS`, `countBy`, `renderPieChart`, `renderBarChart`, `renderCharts`, `resizeCharts` | ~70 |
| `views/summary.js` | `renderSummaryHead`, `renderSummary` | ~50 |
| `views/daily.js` | `renderDailyHead`, `initDaily`, `renderDaily` | ~80 |
| `views/detail.js` | `initDetail`, `populateFilters`, `applyFilters`, `renderStats`, `cellCls`, `td`, `renderTable` | ~140 |

`pagination.js` must **not** import `views/detail.js` (that would be circular). Make it a
self-contained widget instead:

```js
renderPagination({ totalItems, pageSize, currentPage, onPageChange })
```

`detail.js` passes its own state in and handles the page change in the callback.

### Behavior traps to preserve exactly

These are the places where a mechanical move silently changes behavior:

1. **`.sortable` binds once, `.daily-sortable` binds per-render.**
   [app.js:498](static/js/app.js#L498) calls `makeSortable(".sortable", …)` at load time against
   static `<th>` elements in [index.html:163-171](templates/index.html#L163-L171) — it must stay a
   one-time call, or repeated loads stack duplicate listeners.
   [app.js:258](static/js/app.js#L258) calls `makeSortable(".daily-sortable", …)` at the end of
   `renderDailyHead`, which is correct: that function replaces `#dailyHead`'s innerHTML, destroying
   the old `<th>`s and their listeners first. Keep both exactly as they are.

2. **Chart resize on tab switch** — [app.js:56](static/js/app.js#L56). Chart.js sizes to its
   container, which is 0×0 while the tab is hidden. `showView("detail")` must still call
   `resizeCharts()`.

3. **`populateSelect` preserves the placeholder and the selection** —
   [app.js:397-404](static/js/app.js#L397-L404) reads `el.options[0].text` to keep the "All Files"
   label and restores `el.value` afterward. Easy to drop in a rewrite.

4. **Initial `change` dispatch** — [app.js:74](static/js/app.js#L74)
   (`sourceType.dispatchEvent(new Event("change"))`) syncs folder/files input visibility on load.

5. **Render order in `fetchData`** — [app.js:156-167](static/js/app.js#L156-L167). `setTaxonomy()`
   must run before `renderStatCards` / `renderSummaryHead` / `renderDailyHead`, which read it.

6. **Module scripts are deferred.** Keep the Chart.js `<script>` tag *before* the module tag so the
   `Chart` global exists when `charts.js` runs.

### `templates/index.html`

Replace [index.html:207](templates/index.html#L207):

```html
<script type="module" src="{{ url_for('static', filename='js/main.js') }}"></script>
```

No other template change. Every element id the JS queries stays as-is.

---

## Part 2 — Documentation

JSDoc every exported function in the new modules (`@param` / `@returns` where the shape isn't
obvious). Carry the existing explanatory comments across — they capture real reasoning
(e.g. the `sumRows` note at [app.js:190-192](static/js/app.js#L190-L192) about why status columns
reconcile to `total`) and should not be lost in the move.

Python — fill only these gaps, leave documented functions untouched:

- [parser/models.py](parser/models.py) — class docstrings for `SheetConfig` and `TestCase`
  explaining what each field means (`row_num` is the 1-based Excel row; `scope`, `pic`, `ticket_id`
  are not self-evident).
- [parser/excel_reader.py](parser/excel_reader.py) — `load_file`, `load_from_folder`,
  `load_from_files`, `_col_idx`.
- [api/routes.py](api/routes.py) — `load_data`, `reload_data`, `get_data`, `_load` (note that it
  returns a `(body, status)` tuple and only records `source` on success).
- [tools/generate_samples.py](tools/generate_samples.py) — `load_config`, `validate_config`,
  `generate`.

Update the structure tree in [README.md](README.md) — it currently lists a single
`static/js/app.js`; replace that line with the new module layout.

---

## Explicitly out of scope

`api/routes.py` keeps its module-level `_data` dict. It's global mutable state, but it's a
deliberate choice for a single-user local tool and replacing it is a behavior change, not a
readability fix.

---

## Verification

No JS tests exist, so the JS half is verified by hand. Run all of this:

```bash
python -m pytest -q                                   # Python must stay green
python -m tools.generate_samples --out samples/generated --seed 1
python app.py                                          # http://127.0.0.1:5000
```

In the browser, with `samples/generated` loaded — check the console is **clean** (a bad import path
fails silently in the network tab, and a circular import shows up only at runtime):

- **Load/Reload** — both buttons work; the per-file results table appears; a bad folder path still
  shows the red error.
- **Persistence** — reload the page; the previous source is restored from `localStorage`; the
  Folder/File(s) dropdown toggles the right input.
- **Summary tab** — stat columns per status; the footer total equals the sum of the status columns;
  the "Missing Reason" table appears (the generator's `missing_reason_rate` guarantees rows).
- **Daily tab** — all five filters apply; **click a column header three times** and confirm the
  asc → desc → cleared cycle, then reload data and confirm one click still sorts once (this is trap
  #1 — a duplicated listener sorts twice and appears to do nothing).
- **Detail tab** — charts render (trap #2: switch to Detail *after* loading, not before); all seven
  filters + Clear work; sorting works; pagination shows the ellipsis gap with >400 cases; red
  `table-danger` cells still flag missing mandatory fields and missing ticket/note.
