/**
 * Planning: the phase, what each day hands out, and how it is going.
 *
 * The only module `main.js` imports. It binds the listeners and owns the
 * refresh cycle; `render.js` draws, `editor.js` edits one slot, `cells.js`
 * derives, `state.js` holds. Like every view it calls no `fetch` of its own and
 * imports no other view: saving a day announces itself through `plan.js`,
 * which is how Daily and Productivity hear that their plan figures moved.
 */
import { $ } from "../../dom.js";
import {
    getPlanBoard, getPlanCalendar, getPlanPhase, putPlanDay, putPlanSettings,
} from "../../api.js";
import { setPlanCalendar } from "../../plan.js";
import { shiftWorkday } from "./cells.js";
import { closeEditor, initEditor, openEditor, setOnSave } from "./editor.js";
import {
    GRID_STEP, drawn, gridBounds, hideTip, renderBurndown, renderDay, renderGrid,
    renderKpis, renderPhase, showError, showTip,
} from "./render.js";
import {
    data, expanded, getDay, getWindow, listFilter, setDay, setFocus, setGridOffset,
    setLayout, setWindow,
} from "./state.js";

let focusTimer = null;

// --- loading -------------------------------------------------------------------

async function loadPhase() {
    const res = await getPlanPhase(getWindow());
    if (!res.ok) { showError("#planPhaseError", res.json.error); return; }
    showError("#planPhaseError", "");
    data.phase = res.json;
    if (!getDay()) setDay(res.json.today);
    renderPhase();
    renderKpis();
    renderBurndown();
    renderGrid();
}

async function loadBoard() {
    const date = getDay();
    if (!date) return;
    const res = await getPlanBoard(date);
    // Pressing ‹ › faster than the server answers can land an older day's
    // board last. Drawing it would be wrong, and saving over it would write
    // that day's rows under this day's date.
    if (date !== getDay()) return;
    if (!res.ok) { showError("#planDayError", res.json.error); return; }
    showError("#planDayError", "");
    data.board = res.json;
    renderDay();
    renderGrid();            // the grid marks the day the Day plan is on
}

async function reloadAll() {
    await loadPhase();
    await loadBoard();
}

/**
 * Write the whole day and redraw everything that reads it.
 * @returns {Promise<?string>} the server's message on refusal, else null.
 */
async function saveDay(entries) {
    const res = await putPlanDay(getDay(), entries);
    if (!res.ok) return res.json.error || "The plan could not be saved.";
    await reloadAll();
    const cal = await getPlanCalendar();
    if (cal.ok) setPlanCalendar(cal.json);
    return null;
}

async function goToDay(date, focus = null) {
    if (!date) return;
    setDay(date);
    setLayout("matrix");
    await loadBoard();
    if (focus) {
        setFocus(focus);
        renderDay();
        $("#day-plan").scrollIntoView({ behavior: "smooth", block: "start" });
        clearTimeout(focusTimer);
        focusTimer = setTimeout(() => { setFocus(null); renderDay(); }, 3200);
    }
}

// --- listeners -----------------------------------------------------------------

function bindPhase() {
    $("#planPhase").addEventListener("change", async (ev) => {
        const el = ev.target.closest("[data-setting]");
        if (!el) return;
        const s = { ...data.phase.settings };
        delete s.stored;
        s[el.dataset.setting] = el.dataset.setting === "daily_target" ? Number(el.value) : el.value;
        const res = await putPlanSettings(s);
        if (!res.ok) {
            showError("#planPhaseError", res.json.error);
            renderPhase();           // put the inputs back to what is stored
            return;
        }
        await reloadAll();
    });
}

function bindDay() {
    $("#planDayHead").addEventListener("click", async (ev) => {
        const el = ev.target.closest("[data-act]");
        if (!el) return;
        switch (el.dataset.act) {
        case "prev-day": await goToDay(shiftWorkday(getDay(), -1)); break;
        case "next-day": await goToDay(shiftWorkday(getDay(), 1)); break;
        case "today": await goToDay(data.board.today); break;
        case "add-file": openEditor({ slot: null, isNew: true }); break;
        case "layout": setLayout(el.dataset.layout); renderDay(); break;
        default: break;
        }
    });
    $("#planDayHead").addEventListener("change", (ev) => {
        if (ev.target.dataset.act === "pick-day" && ev.target.value) goToDay(ev.target.value);
    });

    $("#planMatrix").addEventListener("click", (ev) => {
        const el = ev.target.closest("[data-act]");
        if (!el) return;
        const day = drawn().day;
        const m = el.dataset.m == null ? null : Number(el.dataset.m);
        const pic = m == null ? null : day.members[m];
        if (el.dataset.act === "add-file") { openEditor({ slot: null, focusPic: pic, isNew: true }); return; }
        const s = day.slots[Number(el.dataset.r)];
        if (!s) return;
        openEditor({ slot: { file: s.file, device: s.device }, focusPic: pic });
    });

    const list = $("#planList");
    list.addEventListener("click", async (ev) => {
        const el = ev.target.closest("[data-act]");
        if (!el) return;
        if (el.dataset.act === "clear-list") {
            Object.assign(listFilter, { pic: "", file: "", status: "" });
            renderDay();
            return;
        }
        const row = drawn().list[Number(el.dataset.i)];
        if (!row) return;
        const s = drawn().day.slots[row.slot];
        if (el.dataset.act === "plan-row") {
            openEditor({ slot: { file: s.file, device: s.device }, focusPic: row.pic });
        } else if (el.dataset.act === "remove") {
            await writeRow(row, 0);
        }
    });
    list.addEventListener("change", async (ev) => {
        const el = ev.target;
        if (el.dataset.filter) {
            listFilter[el.dataset.filter] = el.value;
            renderDay();
            return;
        }
        if (el.dataset.act === "count") {
            const row = drawn().list[Number(el.dataset.i)];
            if (row) await writeRow(row, Math.max(0, Math.round(Number(el.value)) || 0));
        }
    });
}

/** Set one member's count on one slot of the open day; 0 removes the row. */
async function writeRow(row, n) {
    const s = drawn().day.slots[row.slot];
    const entries = data.board.entries.filter(
        (e) => !(e.pic === row.pic && e.file === s.file && e.device === s.device));
    if (n) entries.push({ pic: row.pic, file: s.file, device: s.device, planned: n });
    const error = await saveDay(entries);
    showError("#planDayError", error);
    if (error) renderDay();
}

function bindBurndown() {
    $("#planBurnHead").addEventListener("click", async (ev) => {
        const el = ev.target.closest("[data-act='window']");
        if (!el) return;
        setWindow(el.dataset.window);
        await loadPhase();
    });
}

function bindGrid() {
    $("#planGridHead").addEventListener("click", (ev) => {
        const el = ev.target.closest("[data-act]");
        if (!el) return;
        const { off, maxOff } = gridBounds();
        switch (el.dataset.act) {
        case "grid-prev": setGridOffset(Math.max(0, off - GRID_STEP)); break;
        case "grid-next": setGridOffset(Math.min(maxOff, off + GRID_STEP)); break;
        case "grid-today": setGridOffset(null); break;
        case "grid-all": {
            const files = [...new Set(data.phase.grid.slots.map((s) => s.file))];
            const allOpen = files.length > 0 && files.every((f) => expanded.has(f));
            expanded.clear();
            if (!allOpen) files.forEach((f) => expanded.add(f));
            break;
        }
        default: return;
        }
        renderGrid();
    });

    const table = $("#planGridTable");
    table.addEventListener("click", (ev) => {
        const el = ev.target.closest("[data-act]");
        if (!el) return;
        const { gridRows, gridCols } = drawn();
        if (el.dataset.act === "grid-toggle") {
            const row = gridRows[Number(el.dataset.r)];
            if (expanded.has(row.file)) expanded.delete(row.file); else expanded.add(row.file);
            renderGrid();
        } else if (el.dataset.act === "grid-day") {
            goToDay(gridCols[Number(el.dataset.c)], null).then(() => $("#day-plan").scrollIntoView({ behavior: "smooth" }));
        } else if (el.dataset.act === "grid-cell") {
            const row = gridRows[Number(el.dataset.r)];
            hideTip();
            goToDay(gridCols[Number(el.dataset.c)], { file: row.file, device: row.device });
        }
    });
    table.addEventListener("mouseover", (ev) => {
        const el = ev.target.closest("[data-act='grid-cell']");
        if (el && !el.disabled) showTip(Number(el.dataset.r), Number(el.dataset.c), el);
    });
    table.addEventListener("mouseout", (ev) => {
        const el = ev.target.closest("[data-act='grid-cell']");
        if (el && !el.contains(ev.relatedTarget)) hideTip();
    });
}

// --- entry points ----------------------------------------------------------------

/** Bind every listener. Called once, at startup, before anything is loaded. */
export function initPlanningView() {
    bindPhase();
    bindDay();
    bindBurndown();
    bindGrid();
    initEditor();
    setOnSave(saveDay);
}

/** (Re)load the phase and the open day. Called after every load of the workbooks. */
export async function initPlanning() {
    closeEditor();
    await reloadAll();
}
