/**
 * The detail view's charts.
 *
 * `Chart` is a global, loaded from a classic <script> tag before the module
 * entry point. Module scripts are deferred, so it is always defined by the time
 * anything here runs.
 *
 * Colour is the point of this module. The result chart counts by **status key**
 * and takes each slice's colour from that status' tone, so a slice, its badge
 * in the table and its column in the status band are the same colour by
 * construction — they cannot drift the way a positional palette did.
 *
 * The device and PIC charts carry no status meaning, so they get a monochrome
 * ink ramp rather than a categorical palette. That holds the rule the whole
 * theme rests on: chromatic colour on screen always means status, so a device
 * breakdown can never be misread as a pass/fail one.
 */
import { cssValue, resolveColour } from "./theme.js";
import { colourFor, getStatuses } from "./taxonomy.js";

/** @type {Object<string, Chart>} canvas id -> live chart instance */
const charts = {};

/** The rows last drawn, so a theme change can repaint without a data reload. */
let lastRows = null;

/**
 * Count rows by the value of one field.
 * @param {Object[]} arr
 * @param {string} key
 * @returns {Object<string, number>} Blank values are bucketed under "None".
 */
function countBy(arr, key) {
    const m = {};
    arr.forEach((d) => { const k = d[key] || "None"; m[k] = (m[k] || 0) + 1; });
    return m;
}

/**
 * Count rows by status, in taxonomy order, labelled as the taxonomy labels them.
 *
 * Counting by `status` rather than by the raw `result` string is what lets the
 * slice colour come from the taxonomy: a raw string has no tone.
 *
 * @param {Object[]} rows
 * @returns {{labels: string[], values: number[], colours: string[]}}
 */
function countByStatus(rows) {
    const counts = {};
    rows.forEach((d) => { counts[d.status] = (counts[d.status] || 0) + 1; });
    const present = getStatuses().filter((s) => counts[s.key]);
    return {
        labels: present.map((s) => s.label),
        values: present.map((s) => counts[s.key]),
        colours: present.map((s) => colourFor(s.key)),
    };
}

/**
 * A ramp of ink tints, for breakdowns that carry no status meaning.
 * @param {number} n
 * @returns {string[]}
 */
function inkRamp(n) {
    const ink = cssValue("--ink-soft") || "#5b635a";
    return Array.from({ length: n }, (_, i) => {
        const pct = Math.round((1 - (i / Math.max(n, 1)) * 0.68) * 100);
        return resolveColour(`color-mix(in srgb, ${ink} ${pct}%, transparent)`);
    });
}

/** Chart.js options shared by every chart, themed from the tokens. */
function baseOptions(title) {
    const ink = cssValue("--ink");
    const soft = cssValue("--ink-soft");
    return {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
            title: { display: true, text: title, color: ink, font: { size: 13, weight: "600" } },
            legend: { labels: { color: soft, boxWidth: 10, font: { size: 11 } } },
            tooltip: { backgroundColor: ink, titleColor: cssValue("--ink-invert"),
                       bodyColor: cssValue("--ink-invert"), displayColors: false },
        },
    };
}

/**
 * Replace the chart on `id` with a doughnut.
 * @param {string} id Canvas element id.
 * @param {string} title
 * @param {string[]} labels
 * @param {number[]} values
 * @param {string[]} colours
 */
function renderDoughnut(id, title, labels, values, colours) {
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart(document.getElementById(id), {
        type: "doughnut",
        data: {
            labels,
            datasets: [{
                data: values,
                backgroundColor: colours,
                borderColor: cssValue("--paper"),
                borderWidth: 1,
            }],
        },
        options: baseOptions(title),
    });
}

/**
 * Replace the chart on `id` with a bar chart.
 * @param {string} id Canvas element id.
 * @param {string} title
 * @param {Object<string, number>} data label -> count
 */
function renderBarChart(id, title, data) {
    if (charts[id]) charts[id].destroy();
    const labels = Object.keys(data);
    const soft = cssValue("--ink-soft");
    const rule = cssValue("--rule");
    const options = baseOptions(title);
    options.plugins.legend = { display: false };
    options.scales = {
        x: { ticks: { color: soft, font: { size: 11 } }, grid: { display: false },
             border: { color: rule } },
        y: { beginAtZero: true, ticks: { color: soft, precision: 0, font: { size: 11 } },
             grid: { color: rule }, border: { display: false } },
    };

    charts[id] = new Chart(document.getElementById(id), {
        type: "bar",
        data: {
            labels,
            datasets: [{ label: "Cases", data: Object.values(data), backgroundColor: soft }],
        },
        options,
    });
}

/**
 * Redraw all three detail-view charts from the currently filtered rows.
 * @param {Object[]} rows
 */
export function renderCharts(rows) {
    lastRows = rows;
    const byStatus = countByStatus(rows);
    renderDoughnut("chartResult", "Results", byStatus.labels, byStatus.values, byStatus.colours);

    const byDevice = countBy(rows, "device");
    renderDoughnut("chartDevice", "By device", Object.keys(byDevice),
                   Object.values(byDevice), inkRamp(Object.keys(byDevice).length));

    renderBarChart("chartPIC", "Cases by PIC", countBy(rows, "pic"));
}

/**
 * Rebuild every chart against the current palette.
 *
 * Chart.js resolves colours when a chart is constructed, so a theme change
 * leaves the canvases painted in the old palette until they are rebuilt.
 */
export function refreshChartTheme() {
    if (lastRows) renderCharts(lastRows);
}

/**
 * Resize every live chart.
 *
 * Chart.js sizes to its container, which is 0x0 while the detail tab or the
 * charts strip is hidden, so the charts come out collapsed unless they are
 * resized on the way in.
 */
export function resizeCharts() {
    Object.values(charts).forEach((c) => c.resize());
}
