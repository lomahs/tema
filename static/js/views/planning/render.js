/**
 * Every DOM write Planning makes, except the editor dialog's.
 *
 * Imports run `index → render → cells → state` and never back. What a click
 * has to find again — which slot, which member, which grid row — is kept in the
 * render-local arrays below and reached by index through `drawn()`, never read
 * off an attribute as a name.
 */
import { $, esc } from "../../dom.js";
import { makeSortable, paintSortIndicators, sortRows, sortableTh } from "../../sorting.js";
import {
    STATE_LABEL, arrangeDay, dayLabel, gridCell, listRows, shortFile,
} from "./cells.js";
import {
    data, expanded, getFocus, getGridOffset, getLayout, getWindow, listFilter, listSort,
} from "./state.js";

/** The grid's visible width, in days, and how far ‹ › move it. */
export const GRID_WINDOW = 10;
export const GRID_STEP = 5;

const WINDOW_OPTIONS = [["3", "3d"], ["5", "5d"], ["10", "10d"], ["all", "All"]];
const LIST_NUMERIC = new Set(["planned", "done", "left"]);

/** What the last render drew, for the listeners in index.js to address by index. */
const last = { day: null, list: [], gridRows: [], gridCols: [] };

/** @returns {{day: Object, list: Object[], gridRows: Object[], gridCols: string[]}} */
export function drawn() {
    return last;
}

const num = (n) => Number(n || 0).toLocaleString();
const toneOf = { ok: "success", togo: "warn", missed: "danger" };

// --- phase bar and KPIs ------------------------------------------------------

export function renderPhase() {
    const p = data.phase;
    if (!p) return;
    const s = p.settings;
    $("#planPhase").innerHTML = `
        <label class="inline-field">Phase
            <input type="date" class="input input-mono" data-setting="phase_start" value="${esc(s.phase_start)}">
        </label>
        <span class="plan-phase-arrow" aria-hidden="true">→</span>
        <input type="date" class="input input-mono" data-setting="phase_end" value="${esc(s.phase_end)}"
               aria-label="Phase end">
        <span class="plan-phase-info">${p.phase.days.length} working days · ${p.phase.left} left incl. today</span>
        <label class="inline-field plan-phase-target">Target / member / day
            <input type="number" min="1" class="input input-mono" data-setting="daily_target"
                   value="${esc(s.daily_target)}">
        </label>`;
}

export function renderKpis() {
    const p = data.phase;
    if (!p) return;
    const k = p.kpis;
    const end = p.settings.phase_end;
    const late = (d) => (!d || d > end ? "danger" : "success");
    const cards = [
        { label: "Remaining", value: num(k.remaining), sub: `of ${num(k.at_start)} at phase start` },
        { label: "Planned today", value: num(k.planned_today),
          sub: `${num(k.done_today)} done · ${k.members_today} member${k.members_today === 1 ? "" : "s"}` },
        { label: "Needed pace", value: k.needed_pace == null ? "—" : `${num(k.needed_pace)}/day`,
          sub: `to finish by ${dayLabel(end)}` },
        { label: "Current plan completes",
          value: k.plan_finish ? dayLabel(k.plan_finish) : "Not covered",
          sub: k.plan_finish ? (k.plan_finish <= end ? "within phase" : "after phase end")
                             : `${num(k.unplanned)} cases unplanned`,
          tone: late(k.plan_finish) },
        { label: "Forecast finish", value: k.forecast_finish ? dayLabel(k.forecast_finish) : "—",
          sub: `at ${Math.round(k.rate)}/day · ${windowLabel(k.window_days)}`,
          tone: late(k.forecast_finish) },
    ];
    $("#planKpis").innerHTML = cards.map((c) => `
        <div class="kpi">
            <span class="stat-label">${esc(c.label)}</span>
            <span class="kpi-value"${c.tone ? ` data-tone="${c.tone}"` : ""}>${esc(c.value)}</span>
            <span class="kpi-sub">${esc(c.sub)}</span>
        </div>`).join("");
}

function windowLabel(days) {
    return getWindow() === "all" ? "all phase days" : `last ${days} day${days === 1 ? "" : "s"}`;
}

// --- the day plan ------------------------------------------------------------

export function renderDay() {
    const board = data.board;
    if (!board) return;
    const day = arrangeDay(board);
    last.day = day;
    renderDayHead(day, board);

    const note = $("#planUnplannedNote");
    note.hidden = !day.unplanned.rows;
    note.textContent = day.unplanned.rows
        ? `${num(day.unplanned.cases)} cases run without a plan (${day.unplanned.rows} member × file). `
          + "Click a cell to add them to the plan."
        : "";

    const list = getLayout() === "list";
    $("#planMatrix").hidden = list;
    $("#planList").hidden = !list;
    if (list) renderList(day);
    else renderMatrix(day);
}

function renderDayHead(day, board) {
    const badge = day.date === day.today ? ["Today", "plan-badge--today"]
        : day.date < day.today ? ["Past", ""] : ["Upcoming", ""];
    const devices = {};
    board.slots.forEach((s) => { devices[s.device] = (devices[s.device] || 0) + 1; });
    const parts = [dayLabel(day.date), board.entries.length ? `${num(day.planned)} planned` : "nothing planned"];
    if (day.showDone) parts.push(`${num(day.worked)} done`);
    if (day.activeMembers) {
        parts.push(`${day.activeMembers} member${day.activeMembers === 1 ? "" : "s"}`,
                   `${day.files.length} file${day.files.length === 1 ? "" : "s"}`,
                   ...Object.keys(devices).sort().map((d) => `${devices[d]} ${d}`));
    }
    const layout = getLayout();
    $("#planDayHead").innerHTML = `
        <div class="plan-day-title">
            <div class="plan-day-title-row">
                <h2>Day plan</h2>
                <span class="badge ${badge[1]}">${badge[0]}</span>
                ${day.summary ? `<span class="badge" data-tone="${toneOf[day.summary.kind]}">${esc(day.summary.text)}</span>` : ""}
            </div>
            <span class="plan-day-headline">${esc(parts.join(" · "))}</span>
        </div>
        <div class="plan-day-controls">
            <div class="plan-stepper">
                <button type="button" class="btn btn-sm" data-act="prev-day" aria-label="Previous working day">&lsaquo;</button>
                <input type="date" class="input input-mono" data-act="pick-day" value="${esc(day.date)}" aria-label="Day">
                <button type="button" class="btn btn-sm" data-act="next-day" aria-label="Next working day">&rsaquo;</button>
            </div>
            <button type="button" class="btn btn-sm" data-act="today">Today</button>
            <button type="button" class="btn btn-sm btn-primary" data-act="add-file">+ Add file</button>
            <div class="toggles toggles--seg" role="group" aria-label="Layout">
                <button type="button" class="toggle" data-act="layout" data-layout="matrix"
                        aria-pressed="${layout === "matrix"}">Matrix</button>
                <button type="button" class="toggle" data-act="layout" data-layout="list"
                        aria-pressed="${layout === "list"}">List</button>
            </div>
        </div>`;
}

function renderMatrix(day) {
    const focus = getFocus();
    if (!day.slots.length) {
        // Nothing planned or run: one column that invites the first file.
        $("#planMatrix").innerHTML = `
            <table class="ledger plan-matrix">
                <thead><tr><th>Test case</th><th>Device</th>
                    ${day.members.map((m) => `<th class="plan-member">${esc(m)}</th>`).join("")}
                    <th class="num">Total</th></tr></thead>
                <tbody><tr><td>Test case</td>
                    <td><button type="button" class="plan-slot" data-act="add-file">choose file</button></td>
                    ${day.members.map((_, m) => `<td><button type="button" class="plan-cell" data-state="empty"
                        data-act="add-file" data-m="${m}" title="Click to plan a file">+</button></td>`).join("")}
                    <td class="num">0</td></tr></tbody>
            </table>`;
        return;
    }
    const head = `<tr><th class="plan-sticky">Test case</th><th class="plan-sticky plan-sticky--2">Device</th>
        ${day.members.map((m) => `<th class="plan-member">${esc(m)}</th>`).join("")}
        <th class="num">Total</th></tr>`;
    const body = day.slots.map((s) => {
        const hit = focus && s.file === focus.file && (focus.device == null || s.device === focus.device);
        const sub = day.date < day.today ? `${num(s.remaining)} left`
            : `${num(s.need_through)} / ${num(s.remaining_at_start)} left`;
        const cells = s.cells.map((c, m) => {
            const text = c.state === "empty" ? "+" : c.state === "future" ? num(c.planned) : num(c.worked);
            const of = c.state === "empty" || c.state === "future" ? ""
                : c.state === "unplanned" ? " / —" : ` / ${num(c.planned)}`;
            const title = `${c.pic} · ${shortFile(s.file)} · ${s.device} · planned ${c.planned}`
                + (day.showDone ? ` · run ${c.worked}` : "")
                + (c.state === "unplanned" ? " · run without a plan" : "")
                + (c.over ? " · plan exceeds remaining" : "");
            return `<td><button type="button" class="plan-cell${c.over ? " plan-cell--over" : ""}"
                        data-state="${c.state}" data-act="cell" data-r="${s.index}" data-m="${m}"
                        style="--pct:${c.pct}%" title="${esc(title)}">
                    <span class="num">${text}<span class="plan-cell-of">${of}</span></span>
                    <span class="plan-cell-state">${STATE_LABEL[c.state]}</span>
                </button></td>`;
        }).join("");
        const total = day.showDone ? `${num(s.worked)} / ${num(s.planned)}` : (s.planned ? num(s.planned) : "—");
        return `<tr class="${s.firstOfFile && s.index ? "plan-file-start" : ""}${hit ? " is-focus" : ""}">
            <td class="plan-sticky" title="${esc(s.file)}">${s.firstOfFile ? esc(shortFile(s.file)) : ""}</td>
            <td class="plan-sticky plan-sticky--2"><button type="button" class="plan-slot" data-act="slot"
                    data-r="${s.index}" title="Re-plan ${esc(shortFile(s.file))} · ${esc(s.device)}">
                <span>${esc(s.device)}</span>
                <span class="plan-slot-sub${s.over_by ? " is-over" : ""}">${sub}${s.over_by ? ` · over by ${num(s.over_by)}` : ""}</span>
            </button></td>
            ${cells}
            <td class="num plan-total">${total}${behindLine(s.behind)}</td>
        </tr>`;
    }).join("");
    const foot = `<tr><td class="plan-sticky">Total</td><td class="plan-sticky plan-sticky--2"></td>
        ${day.totals.map((t) => `<td class="num${t.overTarget ? " is-heavy" : ""}"
            title="${t.overTarget ? `Planned load above the target of ${esc(data.board.daily_target)}` : ""}">
            ${day.showDone ? `${num(t.worked)} / ${num(t.planned)}` : (t.planned ? num(t.planned) : "—")}${behindLine(t.behind)}</td>`).join("")}
        <td class="num plan-total">${day.showDone ? `${num(day.worked)} / ${num(day.planned)}` : num(day.planned)}${behindLine(day.behind)}</td></tr>`;
    $("#planMatrix").innerHTML = `<table class="ledger plan-matrix">
        <thead>${head}</thead><tbody>${body}</tbody><tfoot>${foot}</tfoot></table>`;
}

function behindLine(b) {
    return b.text ? `<span class="plan-behind" data-tone="${toneOf[b.kind]}">${esc(b.text)}</span>` : "";
}

function renderList(day) {
    const rows = listRows(day);
    const pics = [...new Set(rows.map((r) => r.pic))].sort();
    const files = [...new Set(rows.map((r) => r.fullFile))];
    const fileIdx = listFilter.file === "" ? -1 : Number(listFilter.file);
    const shown = sortRows(rows.filter((r) => (!listFilter.pic || r.pic === listFilter.pic)
        && (fileIdx < 0 || r.fullFile === files[fileIdx])
        && (!listFilter.status || (listFilter.status === "unplanned" ? !r.isPlanned
            : listFilter.status === "over" ? r.over : r.isPlanned))), listSort, LIST_NUMERIC);
    last.list = shown;

    const filtered = listFilter.pic || listFilter.file !== "" || listFilter.status;
    const opt = (v, label, cur) => `<option value="${esc(v)}"${String(v) === String(cur) ? " selected" : ""}>${esc(label)}</option>`;
    $("#planList").innerHTML = `<table class="ledger plan-list">
        <thead>
            <tr id="planListHead">${sortableTh("pic", "Member")}${sortableTh("file", "File")}${sortableTh("device", "Device")}
                ${sortableTh("planned", "Planned", { cls: "num" })}${sortableTh("done", "Done", { cls: "num" })}
                ${sortableTh("left", "Left", { cls: "num" })}<th></th></tr>
            <tr class="plan-list-filters">
                <th><select class="select" data-filter="pic">${opt("", "All members", listFilter.pic)}${pics.map((p) => opt(p, p, listFilter.pic)).join("")}</select></th>
                <th><select class="select" data-filter="file">${opt("", "All files", listFilter.file)}${files.map((f, i) => opt(i, shortFile(f), listFilter.file)).join("")}</select></th>
                <th colspan="4"><select class="select" data-filter="status">
                    ${[["", "All rows"], ["planned", "Planned"], ["unplanned", "Not planned"], ["over", "Exceeds remaining"]]
                        .map(([v, l]) => opt(v, l, listFilter.status)).join("")}</select></th>
                <th>${filtered ? `<button type="button" class="btn btn-sm btn-quiet" data-act="clear-list">Clear</button>` : ""}</th>
            </tr>
        </thead>
        <tbody>${shown.length ? shown.map((r, i) => `<tr class="${r.isPlanned ? "" : "row--aside"}${r.over ? " is-over" : ""}">
            <td>${esc(r.pic)}</td><td title="${esc(r.fullFile)}">${esc(r.file)}</td><td>${esc(r.device)}</td>
            <td class="num">${r.isPlanned
                ? `<input type="number" min="0" class="input input-mono plan-count" data-act="count" data-i="${i}" value="${r.planned}" aria-label="Planned">`
                : `<span class="plan-muted">Not planned</span>`}</td>
            <td class="num">${r.done == null ? "—" : num(r.done)}</td>
            <td class="num${r.over ? " is-over" : ""}">${num(r.left)}</td>
            <td class="actions">${r.isPlanned
                ? `<button type="button" class="btn btn-sm btn-quiet" data-act="remove" data-i="${i}">Remove</button>`
                : `<button type="button" class="btn btn-sm" data-act="plan-row" data-i="${i}">Add to plan</button>`}</td>
        </tr>`).join("") : `<tr><td colspan="7" class="empty-note">${rows.length
            ? "No rows match these filters." : "Nothing planned for this day. Use + Add file to assign members."}</td></tr>`}</tbody>
    </table>`;
    paintSortIndicators("#planListHead th.sortable", listSort);
    makeSortable("#planListHead th.sortable", listSort, () => renderList(last.day));
}

// --- burndown ------------------------------------------------------------------

export function renderBurndown() {
    const p = data.phase;
    if (!p) return;
    const b = p.burndown;
    const k = p.kpis;
    const w = getWindow();
    $("#planBurnHead").innerHTML = `
        <h2>Burndown · remaining cases</h2>
        <div class="plan-burn-controls">
            <span class="legend-item"><span class="plan-swatch plan-swatch--plan"></span>Plan</span>
            <span class="legend-item"><span class="plan-swatch plan-swatch--actual"></span>Actual</span>
            <span class="legend-item"><span class="plan-swatch plan-swatch--forecast"></span>Forecast</span>
            <span class="plan-burn-pace">Pace from</span>
            <div class="toggles toggles--seg" role="group" aria-label="Forecast pace window">
                ${WINDOW_OPTIONS.map(([v, l]) => `<button type="button" class="toggle" data-act="window"
                    data-window="${v}" aria-pressed="${w === v}">${l}</button>`).join("")}
            </div>
        </div>`;

    const n = Math.max(1, b.axis.length);
    const X = (i) => (i / n * 1000).toFixed(1);
    const Y = (v) => (280 - v / b.y_max * 280).toFixed(1);
    const pts = (vals, from = 0) => vals.map((v, i) => `${X(from + i)},${Y(v)}`).join(" ");
    const pct = (i) => `${((i + 1) / n * 100).toFixed(2)}%`;
    const step = Math.max(1, Math.ceil(n / 9));
    const ticks = [0, 1, 2, 3, 4].map((i) => ({ pos: `${i * 25}%`, label: num(Math.round(b.y_max * i / 4)) }));

    $("#planBurnChart").innerHTML = `
        <div class="plan-burn-y">${ticks.map((t) => `<span style="bottom:${t.pos}">${t.label}</span>`).join("")}</div>
        <div class="plan-burn-plot">
            ${ticks.map((t) => `<div class="plan-burn-grid" style="bottom:${t.pos}"></div>`).join("")}
            ${b.today_index >= 0 ? `<div class="plan-burn-mark" style="left:${pct(b.today_index)}"><span>Today</span></div>` : ""}
            ${b.end_index >= 0 ? `<div class="plan-burn-mark plan-burn-mark--end" style="left:${pct(b.end_index)}"><span>Phase end</span></div>` : ""}
            <svg viewBox="0 0 1000 280" preserveAspectRatio="none" aria-hidden="true">
                <polyline class="plan-line plan-line--plan" points="${pts(b.plan)}"></polyline>
                ${b.forecast.length > 1 ? `<polyline class="plan-line plan-line--forecast" points="${pts(b.forecast, b.forecast_from)}"></polyline>` : ""}
                <polyline class="plan-line plan-line--actual" points="${pts(b.actual)}"></polyline>
            </svg>
        </div>
        <div class="plan-burn-x">${b.axis.map((d, i) => (i % step ? "" : `<span style="left:${pct(i)}">${d.slice(5)}</span>`)).join("")}</div>`;

    const end = p.settings.phase_end;
    const lateDays = k.forecast_finish ? b.axis.filter((d) => d > end && d <= k.forecast_finish).length : 0;
    const note = $("#planBurnNote");
    note.textContent = k.remaining === 0 ? "All cases executed."
        : !k.forecast_finish ? "No execution in the forecast window, so no forecast yet."
        : `At ${Math.round(k.rate)} cases/day (${windowLabel(k.window_days)}), the remaining `
          + `${num(k.remaining)} cases finish on ${dayLabel(k.forecast_finish)}`
          + (lateDays ? `, ${lateDays} working day${lateDays > 1 ? "s" : ""} after phase end.` : ", within the phase.");
    note.dataset.tone = lateDays || (!k.forecast_finish && k.remaining) ? "danger" : "success";
}

// --- the phase grid ------------------------------------------------------------

export function gridBounds() {
    const cols = data.phase ? data.phase.grid.days : [];
    const ti = Math.max(0, cols.indexOf(data.phase ? data.phase.today : ""));
    const maxOff = Math.max(0, cols.length - GRID_WINDOW);
    const off = Math.min(maxOff, Math.max(0, getGridOffset() ?? ti - 3));
    return { cols, off, maxOff };
}

export function renderGrid() {
    const p = data.phase;
    if (!p) return;
    const g = p.grid;
    const today = p.today;
    const { cols, off, maxOff } = gridBounds();
    const wcols = cols.slice(off, off + GRID_WINDOW);
    last.gridCols = wcols;
    const planDay = data.board ? data.board.date : today;

    const files = [...new Set(g.slots.map((s) => s.file))];
    const allOpen = files.length > 0 && files.every((f) => expanded.has(f));
    $("#planGridHead").innerHTML = `
        <div class="card-head">
            <h2>Phase plan</h2>
            <p>Executed cases on past days, planned cases ahead. Hover a cell for details; click a day to open it in Day plan.</p>
        </div>
        <div class="plan-grid-controls">
            <span class="plan-muted">${wcols.length ? `${dayLabel(wcols[0])} – ${dayLabel(wcols[wcols.length - 1])} · ${cols.length} days in phase` : ""}</span>
            <div class="plan-stepper">
                <button type="button" class="btn btn-sm" data-act="grid-prev" ${off > 0 ? "" : "disabled"} aria-label="Earlier days">&lsaquo;</button>
                <button type="button" class="btn btn-sm" data-act="grid-today">Today</button>
                <button type="button" class="btn btn-sm" data-act="grid-next" ${off < maxOff ? "" : "disabled"} aria-label="Later days">&rsaquo;</button>
            </div>
            <button type="button" class="btn btn-sm" data-act="grid-all">${allOpen ? "Collapse devices" : "Show devices"}</button>
        </div>`;

    const rows = [];
    files.forEach((f) => {
        const slots = g.slots.filter((s) => s.file === f);
        const devs = (d) => slots.map((s) => ({ device: s.device, pl: s.cells[d].planned, ex: s.cells[d].worked }));
        rows.push({
            file: f, device: null, label: shortFile(f), title: f, fileRow: true, open: expanded.has(f),
            sub: `${slots.length} device${slots.length > 1 ? "s" : ""}`,
            left: slots.reduce((a, s) => a + s.remaining, 0),
            cells: wcols.map((d) => ({
                pl: slots.reduce((a, s) => a + s.cells[d].planned, 0),
                ex: slots.reduce((a, s) => a + s.cells[d].worked, 0),
                over: slots.some((s) => s.cells[d].over_remaining), devs: devs(d),
            })),
        });
        if (expanded.has(f)) {
            slots.forEach((s) => rows.push({
                file: f, device: s.device, label: s.device, title: `${f} · ${s.device}`, fileRow: false,
                left: s.remaining,
                cells: wcols.map((d) => ({ pl: s.cells[d].planned, ex: s.cells[d].worked,
                                          over: s.cells[d].over_remaining, devs: devs(d) })),
            }));
        }
    });
    last.gridRows = rows;

    const head = `<tr><th class="plan-sticky">File</th><th class="num">Left</th>
        ${wcols.map((d, c) => `<th class="plan-grid-day${d === planDay ? " is-selected" : d === today ? " is-today" : ""}">
            <button type="button" data-act="grid-day" data-c="${c}"><span>${dayLabel(d).slice(0, 3)}</span>
            <span class="num">${d.slice(5)}</span></button></th>`).join("")}</tr>`;
    const body = rows.length ? rows.map((r, ri) => `<tr class="${r.fileRow ? "plan-grid-file" : "plan-grid-device"}">
        <td class="plan-sticky">${r.fileRow
            ? `<button type="button" class="plan-grid-name" data-act="grid-toggle" data-r="${ri}" title="${esc(r.title)}"
                   aria-expanded="${r.open}"><span aria-hidden="true">${r.open ? "▾" : "▸"}</span>
                   <span>${esc(r.label)}</span><span class="plan-muted">${esc(r.sub)}</span></button>`
            : `<span class="plan-grid-name plan-grid-name--device" title="${esc(r.title)}">${esc(r.label)}</span>`}</td>
        <td class="num">${num(r.left)}</td>
        ${r.cells.map((c, ci) => {
            const cell = gridCell(c.pl, c.ex, wcols[ci], today, c.over);
            return `<td><button type="button" class="plan-grid-cell${cell.ring ? " is-ring" : ""}"
                ${cell.kind ? `data-kind="${cell.kind}"` : ""} data-act="grid-cell" data-r="${ri}" data-c="${ci}"
                ${cell.empty ? "disabled" : ""} aria-label="${esc(cell.label)}"><span class="num">${esc(cell.text)}</span></button></td>`;
        }).join("")}</tr>`).join("")
        : `<tr><td colspan="${wcols.length + 2}" class="empty-note">Nothing in this phase yet.</td></tr>`;
    const foot = `<tr><td class="plan-sticky">Planned</td><td></td>
            ${wcols.map((d) => `<td class="num">${g.planned_by_date[d] || ""}</td>`).join("")}</tr>
        <tr><td class="plan-sticky">Executed</td><td></td>
            ${wcols.map((d) => {
                const pv = g.planned_by_date[d] || 0;
                const ev = g.worked_by_date[d] || 0;
                return `<td class="num"${d <= today && ev < pv ? ' data-tone="danger"' : ""}>${d <= today ? ev : ""}</td>`;
            }).join("")}</tr>`;
    $("#planGridTable").innerHTML = `<table class="ledger plan-grid">
        <thead>${head}</thead><tbody>${body}</tbody><tfoot>${foot}</tfoot></table>`;
}

/** The hover card over a grid cell. */
export function showTip(ri, ci, anchor) {
    const row = last.gridRows[ri];
    const d = last.gridCols[ci];
    if (!row || !d || !data.phase) return;
    const today = data.phase.today;
    const c = row.cells[ci];
    const cell = gridCell(c.pl, c.ex, d, today, c.over);
    const ahead = d > today;
    const tip = $("#planTip");
    tip.innerHTML = `
        <div class="plan-tip-head"><strong>${esc(shortFile(row.file))}${row.device == null ? " · all devices" : ` · ${esc(row.device)}`}</strong>
            <span>${esc(dayLabel(d))}${d === today ? " · today" : ""}</span></div>
        <table><thead><tr><th>Device</th><th class="num">Plan</th><th class="num">Actual</th></tr></thead>
        <tbody>${c.devs.map((o) => `<tr${row.device != null && o.device === row.device ? ' class="is-current"' : ""}>
            <td>${esc(o.device)}</td><td class="num">${o.pl}</td><td class="num">${ahead ? "—" : o.ex}</td></tr>`).join("")}</tbody>
        <tfoot><tr><td>Total</td><td class="num">${c.devs.reduce((a, o) => a + o.pl, 0)}</td>
            <td class="num">${ahead ? "—" : c.devs.reduce((a, o) => a + o.ex, 0)}</td></tr></tfoot></table>
        <span class="plan-tip-status"${cell.kind && cell.kind !== "future" ? ` data-kind="${cell.kind}"` : ""}>${esc(cell.label)}</span>
        <span class="plan-muted">Click to open in Day plan</span>`;
    tip.hidden = false;
    const r = anchor.getBoundingClientRect();
    const below = r.top < 190;
    const x = Math.max(140, Math.min(window.innerWidth - 140, r.left + r.width / 2));
    tip.style.left = `${x}px`;
    tip.style.top = `${below ? r.bottom + 8 : r.top - 8}px`;
    tip.classList.toggle("is-below", below);
}

export function hideTip() {
    $("#planTip").hidden = true;
}

export function showError(sel, message) {
    const el = $(sel);
    el.hidden = !message;
    el.textContent = message || "";
}
