/**
 * Entry point: wires the modules together and owns which view is showing.
 *
 * Loaded as `<script type="module">`, so it runs deferred — the DOM is fully
 * parsed and the Chart.js global is available before anything here executes.
 */
import { $ } from "./dom.js";
import { fetchAll, getFile, postReload } from "./api.js";
import { refreshChartTheme, resizeCharts } from "./charts.js";
import { initTheme, onThemeChange } from "./theme.js";
import {
    initShell, setActiveView, setNavCounts, setNavEnabled, setPageHead, setSourceSummary,
} from "./shell.js";
import { initSourcePanel } from "./sourcePanel.js";
import { initReportPanel, setReportEnabled } from "./reportPanel.js";
import { initPreparePanel, refreshPrepare, runFileAction } from "./preparePanel.js";
import { initFilesTable } from "./filesTable.js";
import { initConfigView } from "./views/config.js";
import { getReviewStatuses, setTaxonomy } from "./taxonomy.js";
import { alignSummaryColumns, initSummaryView, renderSummary } from "./views/summary.js";
import {
    currentFile, initFileView, renderFileHeads, showFile,
} from "./views/file.js";
import { setJumpHandler } from "./views/summaryOverview.js";
import { initDaily, initDailyView, renderDailyHead } from "./views/daily.js";
import {
    initProductivity, initProductivityView, renderProductivityHead,
} from "./views/productivity.js";
import { initTarget } from "./target.js";
import {
    enterDetail, initDetail, initDetailView, renderDetailCards, renderDetailHead,
    renderResultToggles, reviewCount, showMissingReason, showReview, showStatusCases,
} from "./views/detail/index.js";

/**
 * Every view, and the heading each carries.
 *
 * The subtitle is a function rather than a string because two of them are only
 * answerable once the taxonomy has loaded, and because both exist to correct a
 * reasonable wrong assumption: that Productivity answers to Daily's filters,
 * and that Review shows everything.
 */
const VIEWS = {
    summary: {
        title: "Summary",
        sub: () => "Every case loaded, one table per scope group.",
    },
    daily: {
        title: "Daily",
        sub: () => "Cases executed per day. Cases with no test date are not counted here.",
    },
    productivity: {
        title: "Productivity",
        sub: () => "Executed cases divided by the days that member actually tested. "
                 + "Covers everything loaded — Daily's filters do not apply.",
    },
    detail: {
        title: "Detail",
        sub: () => "The cases behind a status figure. Cases are fetched one status "
                 + "at a time and kept, so the card figures say what is there to "
                 + "list — the filters below narrow the table, not the cards.",
    },
    file: {
        // The only title that is not a constant: this view is about a subject
        // the reader picked, so the heading is that subject.
        title: () => openFileName || "File",
        sub: () => "Every case in this workbook, sheet by sheet. Includes scope groups "
                 + "outside the plan, so its figures can exceed Review's.",
    },
    tools: {
        title: "Tools",
        sub: () => "Where the cases come from, what gets written back to the workbooks, "
                 + "and where the report goes.",
    },
    config: {
        title: "Config",
        sub: () => "The data files the rest of the app is driven by. Saving one applies it "
                 + "to the running app — no restart.",
    },
};

/**
 * The last `/api/load` response, or `null` while nothing is loaded.
 *
 * Held because a config save changes what every figure on screen *means* —
 * which statuses are columns, which scopes are tables — without anything having
 * been loaded again. Redrawing then needs the figures the rail is showing, and
 * they arrive only with a load.
 */
let lastLoad = null;

/**
 * The workbook the file view has open, and the view to go back to.
 *
 * Held here rather than in `views/file.js` because it is navigation: this module
 * owns which view is showing, and the back button names wherever the reader
 * came from — a file opened from Tools returns to Tools, not to Summary.
 */
let openFileName = "";
let fileOrigin = "summary";

/**
 * A view's heading. Constant for every view but the file one, whose subject is
 * whichever workbook was clicked.
 * @param {keyof VIEWS} view
 * @returns {string}
 */
function titleOf(view) {
    const t = VIEWS[view].title;
    return typeof t === "function" ? t() : t;
}

/**
 * Show one view and hide the others.
 * @param {keyof VIEWS} view
 */
function showView(view) {
    Object.keys(VIEWS).forEach((v) => { $(`#${v}View`).hidden = v !== view; });
    setActiveView(view);
    setPageHead(titleOf(view), VIEWS[view].sub());
    // Back to the top. The rail is the only fixed thing on screen now, so a
    // view change that kept the scroll position landed the reader halfway down
    // a table they had not seen the head of.
    window.scrollTo({ top: 0 });
    // Chart.js sizes to the container, which is 0x0 while the view is hidden.
    // Entering is also when Detail fetches: a load whose case list nobody opens
    // should cost nothing, which is the point of serving cases per status.
    if (view === "detail") { enterDetail(); resizeCharts(); }
    // Summary's tables are measured against each other so their columns line
    // up, and a hidden table measures zero — same reason, same moment.
    if (view === "summary") alignSummaryColumns();
}

/**
 * Open the file view on one workbook.
 *
 * The only view fetched on demand: its data is one file, so pulling it with
 * every load would carry per-sheet rows and every case of every workbook
 * whether or not anybody clicked one.
 *
 * A 404 means the source changed under the reader — a workbook cleared and
 * reloaded, say — so the link they followed no longer names anything. Leaving
 * them where they are is the honest answer; the file list they clicked from is
 * about to be redrawn anyway.
 *
 * @param {string} name Basename of the workbook, as the rows spell it.
 * @param {keyof VIEWS} origin The view clicked from, which the Back button names.
 */
async function openFile(name, origin) {
    const { ok, json } = await getFile(name);
    if (!ok) return;

    openFileName = name;
    fileOrigin = origin;
    showFile(json, { backTo: titleOf(origin) });
    showView("file");
}

/**
 * Pull every endpoint and redraw every view.
 *
 * Order matters: the taxonomy defines the status columns, so it is applied
 * before the stat cards and the generated table headers, and the headers are
 * built before the bodies that fill them. Summary is the exception — it draws
 * one table per scope group, so it cannot know its headers until it has the
 * data, and `renderSummary` builds both together.
 *
 * @param {Object} loadResult The `/api/load` or `/api/reload` response.
 * @param {{show?: boolean}} [opts] `show: false` leaves the current view in
 *   place — the prepare panel reloads from inside Tools, and throwing the user
 *   onto Summary mid-workflow would lose their place.
 */
async function refreshViews(loadResult, { show = true } = {}) {
    lastLoad = loadResult;
    const { taxonomy, summary, daily, productivity } = await fetchAll();

    setTaxonomy(taxonomy);
    renderDetailCards();
    renderDailyHead();
    renderProductivityHead();
    renderDetailHead();
    renderResultToggles();
    renderFileHeads();

    // Detail is handed the summary rows, not the cases: its cards count from
    // them, and the cases behind a figure are fetched when somebody asks for
    // one. This also drops whatever it had cached, which a reload or a config
    // save makes wrong.
    initDetail(summary);
    // Summary's overview reports the last day anyone tested, which lives in the
    // daily rows rather than the summary ones.
    renderSummary(summary, daily);
    initDaily(daily);
    initProductivity(productivity);

    // There is something to publish now.
    setReportEnabled(true);

    setSourceSummary(loadResult);
    setNavCounts({ total: loadResult.loaded, review: reviewCount() });
    setNavEnabled(true);

    if (show) showView("summary");

    // The file view is the one view `fetchAll` cannot redraw, because its data
    // is a single workbook fetched on demand. Re-pull it so a reload or a
    // taxonomy edit reaches the page the reader is actually looking at. Its
    // filters reset deliberately: a config save can remove the very status
    // their card had pressed.
    if (openFileName) {
        const { ok, json } = await getFile(openFileName);
        if (ok) showFile(json, { backTo: titleOf(fileOrigin) });
        else {
            // The workbook is no longer in the source at all.
            openFileName = "";
            if (!$("#fileView").hidden) showView("summary");
        }
    }

    // The prepare panel works from the loaded source's file list, so it only
    // has something to show once a load has succeeded.
    await refreshPrepare();
}

/**
 * Re-read the source after the prepare panel has written to the workbooks.
 *
 * Clearing a round's results is meant to empty the views, so this is not
 * optional bookkeeping — without it the screen would keep showing results that
 * are no longer in the files.
 */
async function reloadAfterPrepare() {
    const { ok, json } = await postReload();
    if (ok) await refreshViews(json, { show: false });
}

/**
 * Redraw after a config file was saved.
 *
 * The taxonomy decides what every status column counts and the scope groups
 * decide how many Summary tables there are, so both change the screen without
 * anything having been re-read from disk — the endpoints classify per request.
 * `show: false` keeps the user on Config, where they are still working.
 *
 * Nothing is redrawn when nothing is loaded: there would be nothing to redraw,
 * and `refreshViews` would turn the nav on over an empty app.
 */
async function refreshAfterConfigSave() {
    if (lastLoad) await refreshViews(lastLoad, { show: false });
}

initTheme();
initTarget();
onThemeChange(refreshChartTheme);
initShell({ onNavigate: showView });
// Summary's KPI cards navigate, but `views/summary.js` must not import
// `views/detail.js` to do it — this module owns the views, so the jump comes
// back through here instead, and it is also what translates a card's filter
// name into the call on whichever module owns that view's state.
setJumpHandler((view, filter, ctx = {}) => {
    if (filter === "missing") showMissingReason();
    else if (ctx.statuses && ctx.statuses.length) showStatusCases({ statuses: ctx.statuses });
    else if (view === "detail") showReview();
    showView(view);
});

/**
 * Open Detail on the cases behind a status figure.
 *
 * Every status band in the app reports its pressed figure here — Summary's rows
 * and footers, the file page, Daily — so a figure means the same thing wherever
 * it is clicked, and no view has to import the one it leads to. The context is
 * whatever the row knew: a file, a device or a device family, a scope group, a
 * sheet, a PIC, a date.
 *
 * @param {Object} ctx See `showStatusCases`.
 */
function openStatusCases(ctx) {
    showStatusCases(ctx);
    showView("detail");
}
// Clicking a file name is navigation, so it comes back through here rather than
// either module importing the file view: `views/summary.js` and `filesTable.js`
// report the name, this decides what to do with it and what Back should say.
initFileView({ onBack: () => showView(fileOrigin), onDrillIn: openStatusCases });
initSourcePanel({ onLoaded: refreshViews });
initReportPanel();
initPreparePanel({ onApplied: reloadAfterPrepare });
// The two Tools panels share one table of workbooks; it reports a pressed row
// button to whichever of them owns that action.
initFilesTable({
    onAction: (path, action, file) =>
        (action === "open" ? openFile(file, "tools") : runFileAction(path, action)),
});
initConfigView({ onSaved: refreshAfterConfigSave });
initDetailView();
initDailyView({ onDrillIn: openStatusCases });
initSummaryView({
    onOpenFile: (name) => openFile(name, "summary"),
    onDrillIn: openStatusCases,
});
initProductivityView();

// Nothing is loaded yet, so the only view that can answer anything is Tools.
// It is the empty state now: a separate "nothing loaded" panel in front of the
// folder field said the same thing twice.
showView("tools");
