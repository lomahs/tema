/**
 * Planning's derivation layer: turns the board and the phase into what is
 * drawn, and writes no DOM.
 *
 * Every figure arrives from the server (`/api/plan/board/<date>` and
 * `/api/plan/phase`); what happens here is classification and arrangement —
 * which state a cell is in, whether a member is behind, which slot rows share a
 * file — the part that is about the page rather than about the counts.
 *
 * A slot is one (file, device) block. Slots and members are addressed by index
 * into the arrays built here; a file name or a PIC never travels through an
 * attribute.
 */

/** What `daily_rows` calls a case with no PIC. It is nobody to plan for. */
export const NO_PIC = "N/A";

const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** "2026-09-25" as a local date, never through `Date.parse` (which reads UTC). */
export function parseISO(iso) {
    const [y, m, d] = String(iso).split("-").map(Number);
    return new Date(y, (m || 1) - 1, d || 1);
}

/** "Fri 09-25". */
export function dayLabel(iso) {
    return `${DOW[parseISO(iso).getDay()]} ${String(iso).slice(5)}`;
}

/** The nearest working day before (-1) or after (+1) `iso`. */
export function shiftWorkday(iso, dir) {
    const d = parseISO(iso);
    do { d.setDate(d.getDate() + dir); } while (d.getDay() === 0 || d.getDay() === 6);
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** "TC_Order_Entry.xlsx" → "Order Entry": the part of a workbook name a reader scans for. */
export function shortFile(name) {
    return String(name).replace(/^TC_/, "").replace(/\.(xlsx|xlsm|xls|csv)$/i, "").replace(/_/g, " ");
}

const slotKey = (file, device) => `${file}\u0000${device}`;

/**
 * The state of one member × slot cell.
 *
 * `empty` nothing planned or run; `unplanned` run with no plan; `future` planned
 * on a day that has not happened; then, once it has: `nys` nothing run yet,
 * `wip` some, `done` exactly the plan, `exceeded` more.
 */
export function cellState(planned, worked, showDone) {
    if (!planned && !worked) return "empty";
    if (!planned) return "unplanned";
    if (!showDone) return "future";
    if (worked === 0) return "nys";
    if (worked < planned) return "wip";
    return worked === planned ? "done" : "exceeded";
}

/** The label a cell state reads as. */
export const STATE_LABEL = {
    empty: "", unplanned: "Unplanned", future: "Planned",
    nys: "NYS", wip: "WIP", done: "Done", exceeded: "Exceeded",
};

/**
 * How a planned figure stands against what was run.
 *
 * `onPlan` counts only work that was planned — a member who ran ten unplanned
 * cases and none of their own is behind. Past days are "missed", today and
 * later "to go".
 *
 * A total can beat its plan while a cell under it falls short: one member ran
 * twenty over on one file and left three undone on another. That is not "on
 * plan" and it is not simply "missed 3" beside a figure reading 120 / 100, so
 * it is its own kind, `offset`: the surplus as the headline and the shortfall
 * as a `note` beneath it, naming how many cells (`short`, of `unit`) owe it.
 *
 * @returns {{text: string, kind: ""|"ok"|"exceeded"|"offset"|"togo"|"missed",
 *            gap: number, note?: {text: string, kind: "togo"|"missed"}}}
 */
export function behind(planned, worked, onPlan, date, today, short = 0, unit = "cell") {
    if (date > today || !planned) return { text: "", kind: "", gap: 0 };
    const gap = Math.max(0, planned - onPlan);
    const extra = worked - planned;
    if (!gap) {
        return extra > 0 ? { text: `exceeded +${num(extra)}`, kind: "exceeded", gap }
                         : { text: "✓ on plan", kind: "ok", gap };
    }
    const late = date < today ? { text: `missed ${num(gap)}`, kind: "missed" }
                              : { text: `${num(gap)} to go`, kind: "togo" };
    if (extra < 0) return { ...late, gap };
    const where = short ? ` · ${short} ${unit}${short === 1 ? "" : "s"}` : "";
    return {
        text: extra > 0 ? `exceeded +${num(extra)}` : "total met",
        kind: "offset", gap,
        note: { text: `${late.text}${where}`, kind: late.kind },
    };
}

const num = (n) => Number(n || 0).toLocaleString();

/** How many of `cells` ran less than they planned. */
const shortOf = (cells) => cells.filter((c) => c.planned && c.worked < c.planned).length;

/**
 * The day, arranged for drawing.
 *
 * Rows are slots, columns the members active that day (everyone, when nobody
 * is), and each cell carries its planned and worked figures and its state.
 * Worked cases with no PIC count toward a slot's total but never get a column.
 *
 * @param {Object} board `/api/plan/board/<date>`.
 */
export function arrangeDay(board) {
    const { date, today } = board;
    const showDone = date <= today;
    const cellsBy = new Map();
    board.cells.forEach((c) => cellsBy.set(`${c.pic}\u0000${slotKey(c.file, c.device)}`, c));

    const active = [...new Set(board.cells
        .filter((c) => (c.planned || c.worked) && c.pic !== NO_PIC).map((c) => c.pic))].sort();
    const members = active.length ? active : board.members.slice();

    const slots = board.slots.map((s, r) => {
        const key = slotKey(s.file, s.device);
        const cells = members.map((pic) => {
            const c = cellsBy.get(`${pic}\u0000${key}`) || { planned: 0, worked: 0 };
            const worked = showDone ? c.worked : 0;
            const state = cellState(c.planned, worked, showDone);
            const pct = c.planned ? Math.min(100, Math.round(worked / c.planned * 100)) : (worked ? 100 : 0);
            return { pic, planned: c.planned, worked, state, pct, over: c.planned > 0 && s.over_by > 0 };
        });
        const noPic = cellsBy.get(`${NO_PIC}\u0000${key}`);
        const planned = cells.reduce((a, c) => a + c.planned, 0);
        const worked = cells.reduce((a, c) => a + c.worked, 0) + (showDone && noPic ? noPic.worked : 0);
        const onPlan = cells.reduce((a, c) => a + Math.min(c.planned, c.worked), 0);
        const prev = board.slots[r - 1];
        return {
            ...s, index: r, cells, planned, worked, onPlan,
            firstOfFile: !prev || prev.file !== s.file,
            behind: behind(planned, worked, onPlan, date, today, shortOf(cells), "member"),
        };
    });

    const totals = members.map((pic, m) => {
        const mine = slots.map((s) => s.cells[m]);
        const planned = mine.reduce((a, c) => a + c.planned, 0);
        const worked = mine.reduce((a, c) => a + c.worked, 0);
        const onPlan = mine.reduce((a, c) => a + Math.min(c.planned, c.worked), 0);
        const b = behind(planned, worked, onPlan, date, today, shortOf(mine), "file");
        return { pic, planned, worked, onPlan, behind: b,
                 overTarget: (board.load[pic] || 0) > board.daily_target };
    });

    const planned = slots.reduce((a, s) => a + s.planned, 0);
    const worked = slots.reduce((a, s) => a + s.worked, 0);
    const onPlan = slots.reduce((a, s) => a + s.onPlan, 0);
    const unplanned = board.cells.filter((c) => !c.planned && c.worked && c.pic !== NO_PIC);
    const behindMembers = totals.filter((t) => t.behind.gap > 0).length;
    const behindSlots = slots.filter((s) => s.behind.gap > 0).length;

    return {
        date, today, showDone, members, slots, totals,
        planned, worked, onPlan,
        behind: behind(planned, worked, onPlan, date, today, behindSlots, "file/device"),
        unplanned: { rows: unplanned.length, cases: unplanned.reduce((a, c) => a + c.worked, 0) },
        activeMembers: active.length,
        files: [...new Set(board.slots.map((s) => s.file))],
        summary: !showDone || !planned ? null
            : !behindMembers ? { text: worked > planned ? `All members on plan · exceeded +${num(worked - planned)}`
                                                        : "All members on plan", kind: "ok" }
            : { text: `${behindMembers} member${behindMembers > 1 ? "s" : ""} · ${behindSlots} file/device `
                    + (date < today ? "missed plan" : "not done yet"),
                kind: date < today ? "missed" : "togo" },
    };
}

/**
 * The List layout's rows: every planned entry, plus work run without a plan.
 * Each row names its slot by index into `day.slots` and its member by name.
 */
export function listRows(day) {
    const rows = [];
    day.slots.forEach((s) => {
        s.cells.forEach((c) => {
            if (!c.planned && !c.worked) return;
            rows.push({
                slot: s.index, pic: c.pic, file: shortFile(s.file), fullFile: s.file,
                device: s.device, planned: c.planned, done: day.showDone ? c.worked : null,
                left: s.remaining, over: s.over_by > 0 && c.planned > 0, isPlanned: c.planned > 0,
            });
        });
    });
    return rows;
}

/**
 * One phase-grid cell: what it shows and how it reads.
 *
 * Behind today a cell shows what was worked against what was planned; ahead of
 * it, what is planned, ringed when that plan outruns what is left. Today counts
 * as ahead until somebody has worked on it.
 */
export function gridCell(pl, ex, date, today, overRemaining) {
    const future = date > today || (date === today && !ex);
    let kind;
    let label;
    if (future) {
        kind = overRemaining ? "under" : "future";
        label = !pl ? "Nothing planned" : overRemaining ? "Plan exceeds remaining cases"
            : date === today ? "Not started yet" : "Upcoming";
    } else if (!pl && !ex) {
        kind = null;
        label = "Nothing planned or run";
    } else {
        kind = !pl ? "unplanned" : ex > pl ? "over" : ex === pl ? "on" : date === today ? "wip" : "under";
        label = { unplanned: "Run without a plan", over: `Over plan by ${ex - pl}`, on: "On plan",
                  wip: `In progress · ${pl - ex} to go`, under: `Under plan by ${pl - ex}` }[kind];
    }
    const empty = !pl && !ex;
    return {
        text: future ? (pl || "") : (empty ? "" : ex),
        kind: future && !pl ? null : kind,
        ring: future && overRemaining,
        empty, future, label,
    };
}

