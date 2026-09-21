/**
 * Summary view: one card per scope group, each holding a flat table.
 *
 * FPT work and JP work are separate commitments, so they are reported as
 * separate tables. A single table adding them together answers no question
 * anyone asks, and the two rarely move for the same reason. The backend splits
 * the rows; which Scope belongs to which table is configured in
 * `config/scope_groups.json`, so this module never names a scope itself.
 *
 * That is the one place this screen departs from the design canvas, which has a
 * single table and a Scope dropdown. Everything else it draws is the design's:
 * the Device and File selects, the Rows toggle, the Executed
 * progress column, the condition chips and the Prev/Next/Show-all footer. The
 * Scope select is the one control that would be meaningless here — the scope is
 * the heading of the card you are already reading.
 *
 * The filters are shared across the cards, for the reason the sort is: the
 * tables have identical columns, so "iPad only" ought to mean the same thing
 * everywhere at once rather than in whichever table you happened to set it in.
 * Paging is *not* shared — a page number only means something within one table.
 *
 * The tables are deliberately **not** grouped internally. Every row carries its
 * own file and device, which is what makes it sortable on any column, readable
 * without opening anything, and safe to select and paste into Excel — a roll-up
 * row interleaved among the data would paste as a duplicate total.
 *
 * Owns the summary dataset, the scope group list, the shared filter and sort
 * state, and each card's page. The KPI cards and panels above the tables are
 * `summaryOverview.js` — it owns none of that state and re-renders on a
 * different trigger, so it is kept out of here.
 */
import { $ } from "../../dom.js";
import { populateSelect, uniqueOf } from "../../filters.js";
import { renderOverview } from "../summaryOverview.js";
import { groupsOf, pressedScopes } from "./buckets.js";
import { alignColumns, render } from "./render.js";
import {
    BUCKETS, FILTERS, GROUPINGS, chosenScopes, getGrouping, getGroups,
    getOnDrillIn, getOnOpenFile, getScopes, paging, setFamilies, setGrouping,
    setGroups, setOnDrillIn, setOnOpenFile, setScopes,
} from "./state.js";

/**
 * Wire the shared controls. Call once, at startup.
 *
 * They live in the static template, so unlike the sortable headers they are
 * never replaced and must only be bound a single time.
 *
 * @param {{onOpenFile?: (file: string) => void}} [opts] What to do when a file
 *   name is clicked. This module does not know there is a file view.
 */
export function initSummaryView({ onOpenFile: open = () => {},
                                  onDrillIn: drill = () => {} } = {}) {
    setOnOpenFile(open);
    setOnDrillIn(drill);

    // One listener for every table: the cards are regenerated per scope group
    // on each render, and a file cell — or a status figure — is the same link in
    // all of them. A status figure is checked first because a row's File cell is
    // a link too, and only one of the two can be meant by a click.
    $("#summaryTables").addEventListener("click", (e) => {
        const figure = e.target.closest("button[data-status]");
        if (figure) {
            // The attribute names the *bucket* — one of this module's own three
            // literals — and the scope keys are resolved here, from the pressed
            // cards. Configured text never goes through a `data-` attribute:
            // that is the rule the NUL-separated group paths are kept out of the
            // DOM for, and a scope key is configured text.
            const { bucket: key, ...rest } = figure.dataset;
            getOnDrillIn()({ ...rest, scopes: pressedScopes(key) });
            return;
        }
        const cell = e.target.closest("button[data-file]");
        if (cell) getOnOpenFile()(cell.dataset.file);
    });

    // The scope tabs never fetch: every row is already here, and pressing one
    // is a filter over them. Delegated like the file cells, because the tabs
    // are regenerated on every render.
    $("#summaryTables").addEventListener("click", (e) => {
        // `All` is a shortcut, not a fourth state: it presses every group in
        // its bucket and has no way back, because unpressing them all shows
        // nothing. The attribute carries a bucket key — one of this module's
        // own three literals — never a configured scope key.
        const all = e.target.closest("button[data-scope-all]");
        if (all) {
            const bucket = BUCKETS.find((b) => b.key === all.dataset.scopeAll);
            if (bucket) groupsOf(bucket).forEach((g) => chosenScopes.add(g.key));
            paging.clear();
            render();
            return;
        }
        const tab = e.target.closest("button[data-scope-tab]");
        if (!tab) return;
        const key = tab.dataset.scopeTab;
        if (chosenScopes.has(key)) chosenScopes.delete(key);
        else chosenScopes.add(key);
        paging.clear();
        render();
    });

    FILTERS.forEach((sel) => $(sel).addEventListener("change", () => {
        paging.clear();
        render();
    }));

    $("#btnSummaryGrouping").addEventListener("click", () => {
        const at = GROUPINGS.findIndex((g) => g.key === getGrouping());
        setGrouping(GROUPINGS[(at + 1) % GROUPINGS.length].key);
        paging.clear();
        render();
    });

    // The columns are fitted to the pane, so the pane changing size is a reason
    // to fit them again — the measured widths themselves do not depend on the
    // viewport, but how much room there is for them does. Debounced, because a
    // drag fires this continuously and each pass is a forced layout.
    let refit;
    window.addEventListener("resize", () => {
        clearTimeout(refit);
        refit = setTimeout(alignColumns, 120);
    });

    $("#btnClearSummaryFilters").addEventListener("click", () => {
        FILTERS.forEach((sel) => { $(sel).value = ""; });
        paging.clear();
        render();
    });
}

/**
 * Adopt a fresh dataset and draw it.
 *
 * The overview is drawn once here rather than inside `render()`: it reports
 * over every row regardless of order, so re-sorting or paging a table must not
 * redraw it.
 *
 * @param {{groups: Object[], scopes: ScopeGroup[], missing_reason: Object[]}} data
 *   `/api/summary` body.
 * @param {Object[]} [dailyRows] `/api/daily` rows, for the activity line.
 */
export function renderSummary(data, dailyRows) {
    setGroups(data.groups || []);
    setScopes(data.scopes || []);
    setFamilies(data.device_families || []);
    // Every group pressed: a bucket exists to show what is in it, and a load
    // arriving pre-filtered by the last one would hide rows without saying so.
    chosenScopes.clear();
    getScopes().forEach((g) => chosenScopes.add(g.key));
    paging.clear();

    populateSelect("#summaryFilterDevice", uniqueOf(getGroups(), "device"));
    populateSelect("#summaryFilterFile", uniqueOf(getGroups(), "file"));

    renderOverview(data, dailyRows);
    render();
}

/**
 * Align the tables now that they can be measured.
 *
 * `main.js` calls this when Summary is shown: the load path renders while the
 * view is still hidden, where every column measures zero.
 */
export function alignSummaryColumns() {
    alignColumns();
}
