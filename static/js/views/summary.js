/**
 * Summary view: one row per (file, device), plus the cases that are missing a
 * reason.
 *
 * Stateless — `renderSummary` is handed the `/api/summary` payload and draws it.
 */
import { $, esc } from "../dom.js";
import { getStatuses, statusCells, statusTextClass, sumRows } from "../taxonomy.js";

/**
 * Build the summary table header from the taxonomy.
 *
 * Separate from {@link renderSummary} because the columns depend only on the
 * status list, not on the data.
 */
export function renderSummaryHead() {
    $("#summaryHead").innerHTML =
        "<th>File</th><th>Device</th><th>Total</th>"
        + getStatuses().map((s) => {
            const cls = statusTextClass(s.key).replace(" fw-bold", "");
            return `<th${cls ? ` class="${cls}"` : ""}>${esc(s.label)}</th>`;
        }).join("");
}

/**
 * Draw the summary table, its totals row, and the "missing reason" table.
 *
 * The missing-reason section stays hidden when the list is empty, so a clean
 * run shows nothing rather than an empty table.
 *
 * @param {{groups: Object[], missing_reason: Object[]}} data `/api/summary` body.
 */
export function renderSummary(data) {
    const { groups, missing_reason } = data;

    $("#summaryBody").innerHTML = groups.map((g) => `<tr>
        <td>${esc(g.file)}</td><td>${esc(g.device)}</td>
        <td>${g.total}</td>
        ${statusCells(g, true)}
    </tr>`).join("");

    const totals = sumRows(groups);
    $("#summaryFoot").innerHTML = `<tr>
        <td colspan="2">Total</td>
        <td>${totals.total}</td>
        ${statusCells(totals, true)}
    </tr>`;

    const mrWrapper = $("#missingReasonWrapper");
    const mrBody = $("#missingReasonBody");
    if (missing_reason.length) {
        mrWrapper.style.display = "";
        mrBody.innerHTML = missing_reason.map((c) => `<tr>
            <td>${esc(c.file)}</td><td>${esc(c.sheet)}</td>
            <td>${esc(c.device)}</td><td>${c.row}</td>
            <td>${esc(c.case_no)}</td>
            <td><span class="badge bg-danger">${esc(c.result)}</span></td>
        </tr>`).join("");
    } else {
        mrWrapper.style.display = "none";
    }
}
