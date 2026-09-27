/**
 * Compare view: what changed between two snapshots.
 *
 * A drill-in like File: no nav item, a Back button, and `main.js` owns getting
 * here. Every figure is the server's (`compare_cases`); this module arranges
 * them. A delta carries no colour of its own — colour means status, so the
 * status names keep their tones and the numbers are ink with a sign.
 */
import { $, esc, formatStamp } from "../dom.js";
import { getCountedStatuses, getStatuses, toneFor } from "../taxonomy.js";

const num = (n) => Number(n || 0).toLocaleString();
const signed = (n) => (n > 0 ? `+${num(n)}` : n < 0 ? `−${num(-n)}` : "0");
const nameOf = (o) => (o ? `${formatStamp(o.taken_at)}${o.label ? ` · ${o.label}` : ""}` : "");

function badge(key) {
    const s = getStatuses().find((x) => x.key === key);
    return `<span class="badge" data-tone="${esc(toneFor(key))}">${esc(s ? s.label : key)}</span>`;
}

/** Added and Removed are not statuses, so they are muted words rather than badges. */
const aside = (text) => `<span class="badge" data-tone="muted">${text}</span>`;

function renderTotals(json) {
    const statuses = getStatuses();
    const head = `<thead><tr><th></th>${statuses.map((s) =>
        `<th class="num">${badge(s.key)}</th>`).join("")}<th class="num">Total</th></tr></thead>`;
    const line = (label, pick, fmt = num) => `<tr><th scope="row">${label}</th>${statuses.map((s) =>
        `<td class="num">${fmt(pick(json.totals[s.key]))}</td>`).join("")}
        <td class="num">${fmt(pick(json.total))}</td></tr>`;
    $("#compareTotals").innerHTML = head + "<tbody>"
        + line("Base", (t) => t.base) + line("Head", (t) => t.head)
        + line("Change", (t) => t.delta, signed) + "</tbody>";
}

function renderMoves(json) {
    $("#compareUnchanged").textContent = `${num(json.unchanged)} cases unchanged`;
    $("#compareMoves").innerHTML = `<thead><tr><th>From</th><th>To</th><th class="num">Cases</th></tr></thead>
        <tbody>${json.transitions.length ? json.transitions.map((t) => `<tr>
            <td>${t.from == null ? aside("Added") : badge(t.from)}</td>
            <td>${t.to == null ? aside("Removed") : badge(t.to)}</td>
            <td class="num">${num(t.count)}</td></tr>`).join("")
        : '<tr><td colspan="3" class="empty-note">Nothing moved.</td></tr>'}</tbody>`;
}

function renderRows(json) {
    const counted = getCountedStatuses();
    // Rows where nothing changed are noise here; the totals already count them.
    const rows = json.rows.filter((r) => Object.values(r.delta).some((d) => d !== 0));
    $("#compareRows").innerHTML = `<thead><tr><th>File</th><th>Device</th>
        <th class="num">Base</th><th class="num">Head</th><th class="num">Change</th>
        ${counted.map((s) => `<th class="num">${badge(s.key)}</th>`).join("")}</tr></thead>
        <tbody>${rows.length ? rows.map((r) => `<tr>
            <td>${esc(r.file)}</td><td>${esc(r.device)}</td>
            <td class="num">${num(r.base.total)}</td><td class="num">${num(r.head.total)}</td>
            <td class="num">${signed(r.delta.total)}</td>
            ${counted.map((s) => `<td class="num">${r.delta[s.key] ? signed(r.delta[s.key]) : ""}</td>`).join("")}
        </tr>`).join("")
        : `<tr><td colspan="${5 + counted.length}" class="empty-note">No file changed.</td></tr>`}</tbody>`;
}

/**
 * Draw one comparison.
 * @param {Object} json `/api/snapshots/compare`'s answer.
 * @param {{backTo: string}} opts The view Back returns to, for its label.
 */
export function showCompare(json, { backTo }) {
    $("#btnCompareBack").textContent = `‹ Back to ${backTo}`;
    $("#compareSides").textContent = `${nameOf(json.base)} → ${nameOf(json.head)}`;
    renderTotals(json);
    renderMoves(json);
    renderRows(json);
}

/**
 * Wire the Back button. Call once, at startup.
 * @param {{onBack: () => void}} opts
 */
export function initCompareView({ onBack }) {
    $("#btnCompareBack").addEventListener("click", onBack);
}
