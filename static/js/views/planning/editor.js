/**
 * The slot editor: one file × device of one day, member by member.
 *
 * A native `<dialog>` opened with `showModal()` — the one floating surface in
 * the app, because rearranging a slot is a focused edit over the matrix it came
 * from, and the matrix has to stay in view behind it.
 *
 * It edits a working copy (`rows`) and writes nothing until Save, which hands
 * the whole day back through `onSave`: the day is written whole, so a refused
 * edit leaves the stored plan exactly as it was. Rows are addressed by index
 * into `rows`, never by the PIC.
 */
import { $, esc } from "../../dom.js";
import { dayLabel, shortFile } from "./cells.js";
import { data } from "./state.js";

/**
 * The editor as it stands.
 * `slot` is `{file, device}` or null in add mode before a file is chosen;
 * each row is `{pic, count, init}` with `count` kept as typed.
 */
let ed = null;

/** Installed by index.js: `(entries) => Promise<?string>`, answering an error message or null. */
let onSave = null;

export function setOnSave(fn) {
    onSave = fn;
}

const dialog = () => $("#planEditor");
const toInt = (v) => Math.max(0, Math.round(Number(v)) || 0);
const sameSlot = (e, slot) => e.file === slot.file && e.device === slot.device;

/** The board's figures for a slot: from its row if the day has it, else from `available`. */
function slotFacts(slot) {
    const b = data.board;
    const s = b.slots.find((x) => sameSlot(x, slot)) || b.available.find((x) => sameSlot(x, slot));
    return { rs: s ? s.remaining_at_start : 0, others: s ? s.planned_other_days : 0 };
}

function workedBy(pic, slot) {
    const c = data.board.cells.find((x) => x.pic === pic && sameSlot(x, slot));
    return c ? c.worked : 0;
}

/**
 * Open the editor.
 * @param {{slot: ?{file: string, device: string}, focusPic?: ?string, isNew?: boolean}} opts
 */
export function openEditor({ slot = null, focusPic = null, isNew = false }) {
    const b = data.board;
    const rows = [];
    if (slot) {
        const pics = new Set();
        b.entries.filter((e) => sameSlot(e, slot)).forEach((e) => pics.add(e.pic));
        if (b.date <= b.today) {
            b.cells.filter((c) => sameSlot(c, slot) && c.worked && c.pic !== "N/A").forEach((c) => pics.add(c.pic));
        }
        [...pics].sort().forEach((pic) => {
            const e = b.entries.find((x) => x.pic === pic && sameSlot(x, slot));
            // A member who worked it without a plan starts at what they did, so
            // saving records the work as planned rather than as zero.
            const worked = b.date <= b.today ? workedBy(pic, slot) : 0;
            rows.push({ pic, count: e ? String(e.planned) : (worked ? String(worked) : ""), init: e ? e.planned : 0 });
        });
    }
    if (focusPic && !rows.some((r) => r.pic === focusPic)) rows.push({ pic: focusPic, count: "", init: 0 });
    ed = {
        slot, isNew, focusPic, rows, error: "",
        existed: !!slot && b.entries.some((e) => sameSlot(e, slot)),
    };
    render();
    if (!dialog().open) dialog().showModal();
}

export function closeEditor() {
    ed = null;
    if (dialog().open) dialog().close();
}

function render() {
    const b = data.board;
    const d = b.date;
    const slot = ed.slot;
    const future = d >= b.today;
    const showDone = d <= b.today;
    const { rs, others } = slot ? slotFacts(slot) : { rs: 0, others: 0 };
    const total = ed.rows.reduce((a, r) => a + toInt(r.count), 0);
    const over = future && slot ? total + others - rs : 0;
    const budget = Math.max(0, rs - others);

    const onDay = new Set(b.entries.map((e) => `${e.file}\u0000${e.device}`));
    const files = [...new Set(b.available.map((a) => a.file))];
    if (slot && !files.includes(slot.file)) files.unshift(slot.file);
    const devices = slot ? b.available.filter((a) => a.file === slot.file) : [];
    const left = (f) => b.available.filter((a) => a.file === f).reduce((a, x) => a + x.remaining_at_start, 0);

    const status = !slot ? null
        : !future ? ["Past day · counts are for the record only.", ""]
        : over > 0 ? [`Over remaining by ${over}. Trim this day to ${budget}.`, "danger"]
        : [`Fits · ${-over} remaining cases still unplanned.`, "success"];
    const unplannedDone = showDone && slot && !ed.existed
        ? b.cells.filter((c) => sameSlot(c, slot)).reduce((a, c) => a + c.worked, 0) : 0;
    const used = new Set(ed.rows.map((r) => r.pic));
    const addable = b.members.filter((m) => !used.has(m));

    dialog().innerHTML = `<form method="dialog" class="plan-editor-form">
        <header class="plan-editor-head">
            <div>
                <h3 id="planEditorTitle">${ed.isNew && !slot ? "Add file to plan"
                    : esc(`${shortFile(slot.file)} · ${slot.device}`)}</h3>
                <span class="plan-muted">${esc(dayLabel(d))}${slot ? ` · ${esc(slot.file)}` : " · only files with cases left"}</span>
            </div>
            <button type="button" class="btn btn-sm btn-quiet" data-ed="close" aria-label="Close">✕</button>
        </header>
        <div class="plan-editor-body">
            ${ed.isNew ? `<div class="plan-editor-pick">
                <label class="field"><span>File</span>
                    <select class="select" data-ed="file">
                        <option value="">${files.length ? "Select file" : "No file with cases left"}</option>
                        ${files.map((f, i) => `<option value="${i}"${slot && slot.file === f ? " selected" : ""}>${esc(shortFile(f))} · ${left(f)} left</option>`).join("")}
                    </select></label>
                ${slot ? `<label class="field"><span>Device</span>
                    <select class="select" data-ed="device">
                        ${devices.length > 1 || !devices.some((x) => x.device === slot.device) ? `<option value="">Select device</option>` : ""}
                        ${devices.map((x, i) => `<option value="${i}"${x.device === slot.device ? " selected" : ""}>${esc(x.device)} · ${x.remaining_at_start} left</option>`).join("")}
                    </select></label>` : ""}
            </div>` : ""}
            ${slot && slot.device ? `<div class="plan-editor-stats">
                <div><span class="stat-label">Remaining</span><span class="num">${rs}</span></div>
                <div><span class="stat-label">Other days</span><span class="num">${others}</span></div>
                <div><span class="stat-label">${d === b.today ? "Planned today" : "Planned this day"}</span>
                    <span class="num"${over > 0 ? ' data-tone="danger"' : ""}>${total}</span></div>
            </div>
            <div class="plan-editor-status"${status[1] ? ` data-tone="${status[1]}"` : ""}>
                <span>${esc(status[0])}</span>
                ${future && over > 0 ? `<button type="button" class="btn btn-sm" data-ed="fit">Fit to remaining</button>` : ""}
            </div>` : ""}
            ${unplannedDone ? `<p class="plan-editor-aside"><strong>${unplannedDone} run without a plan</strong>
                <span class="plan-muted">Planned = Done + new cases</span></p>` : ""}
            <div class="plan-editor-rows">
                <div class="plan-editor-row plan-editor-row--head">
                    <span>Member</span><span class="num" title="Cases this member already ran on this file and device this day">Done</span>
                    <span>Planned</span><span class="num">Day load</span><span></span>
                </div>
                ${ed.rows.length ? ed.rows.map((r, i) => {
                    const cnt = toInt(r.count);
                    const load = (b.load[r.pic] || 0)
                        - (b.entries.find((e) => e.pic === r.pic && slot && sameSlot(e, slot))?.planned || 0) + cnt;
                    const changed = cnt !== r.init;
                    return `<div class="plan-editor-row${r.pic === ed.focusPic ? " is-focus" : ""}">
                        <span>${esc(r.pic)}</span>
                        <span class="num">${showDone && slot ? workedBy(r.pic, slot) : "—"}</span>
                        <span class="plan-editor-count">
                            <input type="text" inputmode="numeric" autocomplete="off" class="input input-mono${changed ? " is-changed" : ""}"
                                   data-ed="count" data-i="${i}" value="${esc(r.count)}" placeholder="0" aria-label="Planned for ${esc(r.pic)}">
                            ${changed ? `<span class="plan-muted">was ${r.init}</span>` : ""}
                        </span>
                        <span class="num"${load > b.daily_target ? ' data-tone="warn"' : ""}>${load} / ${b.daily_target}</span>
                        <button type="button" class="btn btn-sm btn-quiet" data-ed="remove" data-i="${i}"
                                aria-label="Remove ${esc(r.pic)} from this file">✕</button>
                    </div>`;
                }).join("") : `<p class="empty-note">No members yet. Add one below.</p>`}
                <select class="select" data-ed="add">
                    <option value="">+ Add member</option>
                    ${addable.map((m, i) => `<option value="${i}">${esc(m)}</option>`).join("")}
                </select>
            </div>
            <p class="empty-note is-error"${ed.error ? "" : " hidden"}>${esc(ed.error)}</p>
        </div>
        <footer class="plan-editor-foot">
            <div>${ed.existed ? `<button type="button" class="btn btn-sm btn-quiet" data-ed="clear"
                title="Set every member to 0; Save to apply">Clear file from this day</button>` : ""}</div>
            <div class="plan-editor-actions">
                <button type="button" class="btn" data-ed="close">Cancel</button>
                <button type="button" class="btn btn-primary" data-ed="save"${slot && slot.device ? "" : " disabled"}>Save</button>
            </div>
        </footer>
    </form>`;
    ed.addable = addable;
    ed.files = files;
    ed.devices = devices;
}

/** Share the budget out top-down, keeping what each member already ran today. */
function fit() {
    const b = data.board;
    const { rs, others } = slotFacts(ed.slot);
    const base = ed.rows.map((r) => {
        const c = toInt(r.count);
        const done = b.date === b.today ? workedBy(r.pic, ed.slot) : 0;
        return { c, keep: Math.min(c, done) };
    });
    let left = Math.max(0, Math.max(0, rs - others) - base.reduce((a, o) => a + o.keep, 0));
    ed.rows = ed.rows.map((r, i) => {
        const extra = Math.min(base[i].c - base[i].keep, left);
        left -= extra;
        return { ...r, count: String(base[i].keep + extra) };
    });
}

async function save() {
    const slot = ed.slot;
    const entries = data.board.entries.filter((e) => !sameSlot(e, slot));
    ed.rows.forEach((r) => {
        const n = toInt(r.count);
        if (n) entries.push({ pic: r.pic, file: slot.file, device: slot.device, planned: n });
    });
    const error = await onSave(entries);
    if (error) {
        ed.error = error;
        render();
    } else {
        closeEditor();
    }
}

/** Bind once. The dialog's content is redrawn on every change; its listeners are delegated. */
export function initEditor() {
    const dlg = dialog();
    dlg.addEventListener("click", (ev) => {
        if (ev.target === dlg) { closeEditor(); return; }      // the backdrop
        const el = ev.target.closest("[data-ed]");
        if (!el || !ed) return;
        const i = Number(el.dataset.i);
        switch (el.dataset.ed) {
        case "close": closeEditor(); break;
        case "remove": ed.rows.splice(i, 1); render(); break;
        case "clear": ed.rows = ed.rows.map((r) => ({ ...r, count: "0" })); render(); break;
        case "fit": fit(); render(); break;
        case "save": save(); break;
        default: break;
        }
    });
    dlg.addEventListener("change", (ev) => {
        const el = ev.target;
        if (!ed) return;
        switch (el.dataset.ed) {
        case "file": {
            const f = el.value === "" ? null : ed.files[Number(el.value)];
            const devs = f ? data.board.available.filter((a) => a.file === f) : [];
            openEditor({ slot: f ? { file: f, device: devs.length === 1 ? devs[0].device : "" } : null,
                         focusPic: ed.focusPic, isNew: true });
            break;
        }
        case "device": {
            const x = el.value === "" ? null : ed.devices[Number(el.value)];
            openEditor({ slot: { file: ed.slot.file, device: x ? x.device : "" },
                         focusPic: ed.focusPic, isNew: true });
            break;
        }
        case "add": {
            const pic = ed.addable[Number(el.value)];
            if (pic) { ed.rows.push({ pic, count: "", init: 0 }); ed.focusPic = pic; }
            render();
            break;
        }
        default: break;
        }
    });
    // Counts redraw on every keystroke so the totals and the fit line follow;
    // focus and the caret are put back on the input that was being typed in.
    // It is a text input, not a number one: a number input reports no caret,
    // so the redraw would drop it at the start and "123" would type as "321".
    // Anything but a digit is dropped here instead, caret kept in step.
    dlg.addEventListener("input", (ev) => {
        const el = ev.target;
        if (!ed || el.dataset.ed !== "count") return;
        const i = Number(el.dataset.i);
        const raw = el.value;
        const at = el.selectionStart ?? raw.length;
        const pos = raw.slice(0, at).replace(/\D/g, "").length;
        ed.rows[i].count = raw.replace(/\D/g, "");
        render();
        const again = dlg.querySelector(`[data-ed="count"][data-i="${i}"]`);
        if (again) { again.focus(); again.setSelectionRange(pos, pos); }
    });
    // Enter in a count submits the form, and a `method="dialog"` form closes
    // the dialog on submit: that would throw the edit away. It saves instead.
    dlg.addEventListener("submit", (ev) => {
        ev.preventDefault();
        if (ed && ed.slot && ed.slot.device) save();
    });
    dlg.addEventListener("close", () => { ed = null; });
}
