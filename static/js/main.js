/**
 * Entry point: wires the modules together and owns the tab switching.
 *
 * Loaded as `<script type="module">`, so it runs deferred — the DOM is fully
 * parsed and the Chart.js global is available before anything here executes.
 */
import { $, $$ } from "./dom.js";
import { fetchAll } from "./api.js";
import { refreshChartTheme, resizeCharts } from "./charts.js";
import { initTheme, onThemeChange } from "./theme.js";
import { closeDrawer, initSetupDrawer, setSourceSummary } from "./setupDrawer.js";
import { initSourcePanel } from "./sourcePanel.js";
import { initReportPanel, setReportEnabled } from "./reportPanel.js";
import { renderStatCards, setTaxonomy } from "./taxonomy.js";
import { renderSummary } from "./views/summary.js";
import { initDaily, initDailyView, renderDailyHead } from "./views/daily.js";
import { initProductivity, renderProductivityHead } from "./views/productivity.js";
import { initDetail, initDetailView, renderDetailHead, renderResultToggles } from "./views/detail.js";

const VIEWS = ["summary", "daily", "detail"];

/**
 * Show one of the three views and hide the others.
 * @param {"summary"|"daily"|"detail"} view
 */
function showView(view) {
    VIEWS.forEach((v) => { $(`#${v}View`).hidden = v !== view; });
    $$("#viewTabs .tab").forEach((t) =>
        t.setAttribute("aria-selected", String(t.dataset.view === view)));
    // Chart.js sizes to the container, which is 0x0 while the tab is hidden.
    if (view === "detail") resizeCharts();
}

/** Wire the Summary / Daily / Detail tabs. */
function initViewTabs() {
    $$("#viewTabs .tab").forEach((tab) =>
        tab.addEventListener("click", () => showView(tab.dataset.view)));
}

/**
 * Pull every endpoint and redraw all three views.
 *
 * Order matters: the taxonomy defines the status columns, so it is applied
 * before the stat cards and the generated table headers, and the headers are
 * built before the bodies that fill them. Summary is the exception — it draws
 * one table per scope group, so it cannot know its headers until it has the
 * data, and `renderSummary` builds both together.
 *
 * @param {Object} loadResult The `/api/load` or `/api/reload` response.
 */
async function refreshViews(loadResult) {
    const { taxonomy, cases, summary, daily, productivity } = await fetchAll();

    setTaxonomy(taxonomy);
    renderStatCards();
    renderDailyHead();
    renderProductivityHead();
    renderDetailHead();
    renderResultToggles();

    initDetail(cases);
    renderSummary(summary);
    initDaily(daily);
    initProductivity(productivity);

    // There is something to publish now.
    setReportEnabled(true);

    setSourceSummary(loadResult);
    $("#emptyState").hidden = true;
    $("#viewTabs").hidden = false;
    showView("summary");
    closeDrawer();
}

initTheme();
onThemeChange(refreshChartTheme);
initSetupDrawer();
initSourcePanel({ onLoaded: refreshViews });
initReportPanel();
initDetailView();
initDailyView();
initViewTabs();
