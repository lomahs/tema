/**
 * Compare view: what changed between two snapshots.
 *
 * A drill-in like File: no nav item, a Back button, and `main.js` owns getting
 * here. Every figure is the server's (`compare_cases`); this module arranges
 * them. A delta carries no colour of its own — colour means status, so the
 * status names keep their tones and the numbers are ink with a sign.
 *
 * A move is a change of scope group, of status, or both, and `plan` says whether
 * it crossed Summary's Total — `left` or `entered`. The "In / out of plan" card
 * is those moves alone, because a case quietly leaving the denominator is the
 * one change the totals cannot show. Pressing a move's count lists its cases,
 * fetched one move at a time (`/api/snapshots/compare/cases`): a week between
 * two snapshots can be tens of thousands of changed cases.
 */
import { getSnapshotCompareCases } from "../api.js";
import { $, esc, formatStamp } from "../dom.js";
import { renderPageFooter } from "../pagination.js";
import { getCountedStatuses, getStatuses, toneFor } from "../taxonomy.js";

const num = (n) => Number(n || 0).toLocaleString();
const signed = (n) => (n > 0 ? `+${num(n)}` : n < 0 ? `−${num(-n)}` : "0");
const nameOf = (o) => (o ? `${formatStamp(o.taken_at)}${o.label ? ` · ${o.label}` : ""}` : "");

const PAGE_SIZE = 50;

/** Which moves "What moved" lists. Each is a question, not a status. */
const FILTERS = [
    { key: "all", label: "All", keep: () => true },
    { key: "plan", label: "In / out of plan", keep: (t) => t.plan != null },
    { key: "scope", label: "Scope changed", keep: (t) => t.scope_changed },
    { key: "status", label: "Status changed", keep: (t) => t.status_changed },
    { key: "rows", label: "Added / removed", keep: (t) => t.from == null || t.to == null },
];

const PLAN_WORDS = { left: "Left plan", entered: "Entered plan" };

let current = null;      // the compare answer on screen
let filter = "all";
let open = null;         // {move, cases, page, showAll} for the case list, or null
let ticket = 0;          // drops a case list that arrives after a newer press

function badge(key) {
    const s = getStatuses().find((x) => x.key === key);
    return `<span class="badge" data-tone="${esc(toneFor(key))}">${esc(s ? s.label : key)}</span>`;
}

/** Added and Removed are not statuses, so they are muted words rather than badges. */
const aside = (text) => `<span class="badge" data-tone="muted">${text}</span>`;

function scopeGroup(key) {
    return (current?.scopes || []).find((g) => g.key === key);
}

/** A scope group by label. One outside the plan carries the dashed rule that means so. */
function scopeName(key) {
    const g = scopeGroup(key);
    const out = g && !g.counted;
    return `<span class="compare-scope${out ? " compare-scope--out" : ""}"`
        + `${out ? ' title="Not in the plan"' : ""}>${esc(g ? g.label : key)}</span>`;
}

/** The two cells of one side of a move; the half that did not change is faded. */
function sideCells(side, move, word) {
    if (side == null) return `<td colspan="2">${aside(word)}</td>`;
    const mark = (changed) => (changed ? "" : ' class="is-same"');
    return `<td${mark(move.scope_changed)}>${scopeName(side.scope)}</td>`
        + `<td${mark(move.status_changed)}>${badge(side.status)}</td>`;
}

const MOVE_HEAD = `<thead><tr>
    <th>From scope</th><th>From status</th><th aria-hidden="true"></th>
    <th>To scope</th><th>To status</th><th>Plan</th><th class="num">Cases</th></tr></thead>`;

/** Rows of moves; each count is a button carrying the move's index in `current.transitions`. */
function moveRows(moves, emptyText) {
    if (!moves.length) return `<tr><td colspan="7" class="empty-note">${emptyText}</td></tr>`;
    return moves.map((t) => {
        const i = current.transitions.indexOf(t);
        const on = open && open.move === t;
        return `<tr${on ? ' class="is-current"' : ""}>
            ${sideCells(t.from, t, "Added")}
            <td class="compare-arrow" aria-hidden="true">→</td>
            ${sideCells(t.to, t, "Removed")}
            <td>${t.plan ? PLAN_WORDS[t.plan] : ""}</td>
            <td class="num"><button type="button" class="cell-link" data-move="${i}">${num(t.count)}</button></td>
        </tr>`;
    }).join("");
}

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

function renderPlan() {
    const crossed = current.transitions.filter((t) => t.plan != null);
    const sum = (dir) => crossed.filter((t) => t.plan === dir).reduce((n, t) => n + t.count, 0);
    $("#comparePlanNote").textContent = `${num(sum("left"))} left · ${num(sum("entered"))} entered`;
    // Left first: a case dropping out of the denominator is the one to explain.
    const ordered = [...crossed].sort((a, b) => (a.plan === b.plan ? 0 : a.plan === "left" ? -1 : 1));
    $("#comparePlan").innerHTML = MOVE_HEAD
        + `<tbody>${moveRows(ordered, "No case left or entered the plan.")}</tbody>`;
}

function renderFilter() {
    $("#compareFilter").innerHTML = FILTERS.map((f) => {
        const n = current.transitions.filter(f.keep).reduce((s, t) => s + t.count, 0);
        return `<button type="button" class="toggle" data-filter="${f.key}"
            aria-pressed="${f.key === filter}">${esc(f.label)} · ${num(n)}</button>`;
    }).join("");
}

function renderMoves() {
    $("#compareUnchanged").textContent = `${num(current.unchanged)} cases unchanged`;
    const keep = FILTERS.find((f) => f.key === filter).keep;
    $("#compareMoves").innerHTML = MOVE_HEAD
        + `<tbody>${moveRows(current.transitions.filter(keep), "Nothing moved.")}</tbody>`;
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

/** One raw cell across both sides: the value, or "before → after" when it moved. */
function beforeAfter(c, field, show = esc) {
    const b = c.base ? c.base[field] : undefined;
    const h = c.head ? c.head[field] : undefined;
    const cell = (v) => (v == null || v === "" ? '<span class="compare-blank">—</span>' : show(v));
    if (!c.base) return cell(h);
    if (!c.head) return cell(b);
    if (b === h) return cell(b);
    return `<span class="is-changed">${cell(b)} → ${cell(h)}</span>`;
}

function describeMove(t) {
    const side = (s, word) => (s ? `${scopeName(s.scope)} ${badge(s.status)}` : aside(word));
    return `${side(t.from, "Added")} → ${side(t.to, "Removed")}`
        + (t.plan ? ` · ${PLAN_WORDS[t.plan]}` : "");
}

function renderCases() {
    const card = $("#compareCasesCard");
    card.hidden = !open;
    if (!open) return;
    $("#compareCasesMove").innerHTML = describeMove(open.move);
    const table = $("#compareCases");
    const head = `<thead><tr><th>File</th><th>Sheet</th><th>Device</th><th class="num">Row</th>
        <th>Case no</th><th>Scope</th><th>Result</th><th>PIC</th></tr></thead>`;
    if (!open.cases) {
        table.innerHTML = head + '<tbody><tr><td colspan="8" class="empty-note">Loading…</td></tr></tbody>';
        $("#compareCasesFoot").innerHTML = "";
        return;
    }
    const all = open.cases;
    const start = open.showAll ? 0 : (open.page - 1) * PAGE_SIZE;
    const shown = open.showAll ? all : all.slice(start, start + PAGE_SIZE);
    table.innerHTML = head + `<tbody>${shown.length ? shown.map((c) => `<tr>
        <td>${esc(c.file)}</td><td>${esc(c.sheet)}</td><td>${esc(c.device)}</td>
        <td class="num">${esc(c.row)}</td><td class="mono">${esc(c.case_no)}</td>
        <td>${beforeAfter(c, "scope")}</td>
        <td>${beforeAfter(c, "result")}</td>
        <td>${beforeAfter(c, "pic")}</td></tr>`).join("")
        : '<tr><td colspan="8" class="empty-note">No cases.</td></tr>'}</tbody>`;
    renderPageFooter({
        container: "#compareCasesFoot", totalItems: all.length, pageSize: PAGE_SIZE,
        currentPage: open.page, showAll: open.showAll, unit: "case",
        onPageChange: (p) => { open.page = p; renderCases(); },
        onToggleAll: (v) => { open.showAll = v; open.page = 1; renderCases(); },
    });
}

/** Redraw the two move tables, so the open move's row is marked in both. */
function renderMoveTables() {
    renderPlan();
    renderMoves();
}

async function openMove(move) {
    const mine = ++ticket;
    open = { move, cases: null, page: 1, showAll: false };
    renderMoveTables();
    renderCases();
    $("#compareCasesCard").scrollIntoView({ behavior: "smooth", block: "start" });
    const { ok, json } = await getSnapshotCompareCases(
        current.base.id, current.head.id, move.from, move.to);
    if (mine !== ticket) return;
    open.cases = ok ? json.cases : [];
    renderCases();
}

function closeMove() {
    ticket++;
    open = null;
    renderMoveTables();
    renderCases();
}

/**
 * Draw one comparison.
 * @param {Object} json `/api/snapshots/compare`'s answer.
 * @param {{backTo: string}} opts The view Back returns to, for its label.
 */
export function showCompare(json, { backTo }) {
    current = json;
    filter = "all";
    ticket++;
    open = null;
    $("#btnCompareBack").textContent = `‹ Back to ${backTo}`;
    $("#compareSides").textContent = `${nameOf(json.base)} → ${nameOf(json.head)}`;
    renderTotals(json);
    renderFilter();
    renderMoveTables();
    renderCases();
    renderRows(json);
}

/**
 * Wire the Back button, the filter and the move counts. Call once, at startup.
 * @param {{onBack: () => void}} opts
 */
export function initCompareView({ onBack }) {
    $("#btnCompareBack").addEventListener("click", onBack);
    $("#btnCompareCasesClose").addEventListener("click", closeMove);
    $("#compareFilter").addEventListener("click", (e) => {
        const b = e.target.closest("button[data-filter]");
        if (!b || !current) return;
        filter = b.dataset.filter;
        renderFilter();
        renderMoves();
    });
    // Both move tables carry an index into `current.transitions`, never the move itself.
    for (const id of ["#comparePlan", "#compareMoves"]) {
        $(id).addEventListener("click", (e) => {
            const b = e.target.closest("button[data-move]");
            if (!b || !current) return;
            const move = current.transitions[Number(b.dataset.move)];
            if (move) openMove(move);
        });
    }
}
