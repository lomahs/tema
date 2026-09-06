/**
 * Entry point: wires the modules together and owns the tab switching.
 *
 * Loaded as `<script type="module">`, so it runs deferred — the DOM is fully
 * parsed and the Chart.js global is available before anything here executes.
 */
import { $, $$ } from "./dom.js";
import { fetchAll } from "./api.js";
import { resizeCharts } from "./charts.js";
import { initSourcePanel } from "./sourcePanel.js";
import { initReportPanel, setReportEnabled } from "./reportPanel.js";
import { renderStatCards, setTaxonomy } from "./taxonomy.js";
import { renderSummary, renderSummaryHead } from "./views/summary.js";
import { initDaily, initDailyView, renderDailyHead } from "./views/daily.js";
import { initProductivity, renderProductivityHead } from "./views/productivity.js";
import { initDetail, initDetailView } from "./views/detail.js";

/**
 * Show one of the three views and hide the others.
 * @param {"summary"|"daily"|"detail"} view
 */
function showView(view) {
    $("#summaryView").style.display = view === "summary" ? "" : "none";
    $("#dailyView").style.display = view === "daily" ? "" : "none";
    $("#detailView").style.display = view === "detail" ? "" : "none";
    // Chart.js sizes to the container, which is 0x0 while the tab is hidden.
    if (view === "detail") resizeCharts();
}

/** Wire the Summary / Daily / Detail tabs. */
function initViewTabs() {
    $$("#viewTabs a[data-view]").forEach((tab) => tab.addEventListener("click", (e) => {
        e.preventDefault();
        $$("#viewTabs a").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        showView(tab.dataset.view);
    }));
}

/**
 * Pull every endpoint and redraw all three views.
 *
 * Order matters: the taxonomy defines the status columns, so it is applied
 * before the stat cards and the three generated table headers, and the headers
 * are built before the bodies that fill them.
 */
async function refreshViews() {
    const { taxonomy, cases, summary, daily, productivity } = await fetchAll();

    setTaxonomy(taxonomy);
    renderStatCards();
    renderSummaryHead();
    renderDailyHead();
    renderProductivityHead();

    initDetail(cases);
    renderSummary(summary);
    initDaily(daily);
    initProductivity(productivity);

    // There is something to publish now.
    setReportEnabled(true);

    $("#viewTabs").style.display = "";
    $$("#viewTabs a").forEach((t) => t.classList.toggle("active", t.dataset.view === "summary"));
    showView("summary");
}

initSourcePanel({ onLoaded: refreshViews });
initReportPanel();
initDetailView();
initDailyView();
initViewTabs();
