/**
 * Chart.js doughnut and bar charts for the detail view.
 *
 * `Chart` is a global, loaded from a classic <script> tag before the module
 * entry point. Module scripts are deferred, so it is always defined by the time
 * anything here runs.
 */

/** @type {Object<string, Chart>} canvas id -> live chart instance */
const charts = {};

const COLORS = ["#198754", "#dc3545", "#ffc107", "#0d6efd", "#6f42c1",
    "#20c997", "#fd7e14", "#0dcaf0", "#d63384", "#6c757d"];

/**
 * Count rows by the value of one field.
 * @param {Object[]} arr
 * @param {string} key
 * @returns {Object<string, number>} Blank values are bucketed under "N/A".
 */
function countBy(arr, key) {
    const m = {};
    arr.forEach((d) => { const k = d[key] || "N/A"; m[k] = (m[k] || 0) + 1; });
    return m;
}

/**
 * Replace the chart on `id` with a doughnut of `data`.
 * @param {string} id Canvas element id.
 * @param {string} title
 * @param {Object<string, number>} data label -> count
 */
function renderPieChart(id, title, data) {
    if (charts[id]) charts[id].destroy();
    const labels = Object.keys(data);
    charts[id] = new Chart(document.getElementById(id), {
        type: "doughnut",
        data: {
            labels,
            datasets: [{ data: Object.values(data), backgroundColor: COLORS.slice(0, labels.length) }],
        },
        options: { responsive: true, plugins: { title: { display: true, text: title } } },
    });
}

/**
 * Replace the chart on `id` with a bar chart of `data`.
 * @param {string} id Canvas element id.
 * @param {string} title
 * @param {Object<string, number>} data label -> count
 */
function renderBarChart(id, title, data) {
    if (charts[id]) charts[id].destroy();
    const labels = Object.keys(data);
    charts[id] = new Chart(document.getElementById(id), {
        type: "bar",
        data: {
            labels,
            datasets: [{ label: "Cases", data: Object.values(data), backgroundColor: "#0d6efd" }],
        },
        options: {
            responsive: true,
            plugins: { title: { display: true, text: title }, legend: { display: false } },
            scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } },
        },
    });
}

/**
 * Redraw all three detail-view charts from the currently filtered rows.
 * @param {Object[]} rows
 */
export function renderCharts(rows) {
    renderPieChart("chartResult", "Result Distribution", countBy(rows, "result"));
    renderPieChart("chartDevice", "By Device", countBy(rows, "device"));
    renderBarChart("chartPIC", "Cases by PIC", countBy(rows, "pic"));
}

/**
 * Resize every live chart.
 *
 * Chart.js sizes to its container, which is 0x0 while the detail tab is hidden,
 * so the charts come out collapsed unless they are resized on the way in.
 */
export function resizeCharts() {
    Object.values(charts).forEach((c) => c.resize());
}
