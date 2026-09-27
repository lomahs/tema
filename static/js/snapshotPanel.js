/**
 * Tools → Snapshots: keep what is loaded, open it again, compare two.
 *
 * A panel in the mould of `sourcePanel.js`: it owns its card and knows nothing
 * about the views. Opening one and comparing two are reported back through the
 * hooks `main.js` installs, because redrawing the app and changing view are
 * `main.js`'s business. Rows address a snapshot by index into `list`, never
 * through an attribute.
 */
import { $, esc, formatStamp } from "./dom.js";
import { deleteSnapshot, getSnapshots, postOpenSnapshot, postSnapshot } from "./api.js";

/** @type {Array<{id:number, taken_at:string, label:string, case_count:number, file_count:number}>} newest first */
let list = [];
/** @type {?{id:number}} the snapshot on screen, or null for live data */
let origin = null;
let hooks = { onOpened: () => {}, onCompare: () => {} };

function status(text, isError = false) {
    const el = $("#snapshotStatus");
    el.textContent = text;
    el.classList.toggle("is-error", isError);
}

const nameOf = (s) => `${formatStamp(s.taken_at)}${s.label ? ` · ${s.label}` : ""}`;

function render() {
    const current = (s) => origin && origin.id === s.id;
    $("#snapshotEmpty").hidden = list.length > 0;
    $("#snapshotTableWrap").hidden = list.length === 0;
    $("#snapshotBody").innerHTML = list.map((s, i) => `
        <tr${current(s) ? ' class="is-current"' : ""}>
            <td class="mono">${esc(formatStamp(s.taken_at))}</td>
            <td>${esc(s.label)}${current(s) ? ' <span class="chip">On screen</span>' : ""}</td>
            <td class="num">${s.file_count.toLocaleString()}</td>
            <td class="num">${s.case_count.toLocaleString()}</td>
            <td class="actions">
                <button type="button" class="btn btn-sm" data-act="open" data-index="${i}">Open</button>
                <button type="button" class="btn btn-sm btn-quiet" data-act="delete" data-index="${i}">Delete</button>
            </td>
        </tr>`).join("");

    const options = list.map((s, i) => `<option value="${i}">${esc(nameOf(s))}</option>`).join("");
    $("#snapshotCompareRow").hidden = list.length < 2;
    $("#snapshotBase").innerHTML = options;
    $("#snapshotHead").innerHTML = options;
    // The one before the newest against the newest is the usual question:
    // "what changed since last time".
    if (list.length >= 2) {
        $("#snapshotBase").value = "1";
        $("#snapshotHead").value = "0";
    }
}

/** Re-read the history and redraw. Call after anything that changes it. */
export async function refreshSnapshots() {
    const { ok, json } = await getSnapshots();
    if (!ok) { status(json.error || "Could not read the snapshots.", true); return; }
    list = json.snapshots;
    origin = json.origin;
    render();
}

/**
 * Saving needs live data loaded. A snapshot on screen is refused by the server
 * too: a copy would be stamped now while holding old data.
 * @param {boolean} on
 * @param {string} [why] The tooltip saying what to do while it is off.
 */
export function setSnapshotSaveEnabled(on, why = "Load test cases first") {
    const btn = $("#btnSnapshotSave");
    btn.disabled = !on;
    btn.title = on ? "" : why;
}

/**
 * Wire the card. Call once, at startup.
 * @param {{onOpened: (state: Object) => Promise<void>|void,
 *          onCompare: (base: number, head: number) => void}} opts
 */
export function initSnapshotPanel(opts) {
    hooks = { ...hooks, ...opts };

    $("#btnSnapshotSave").addEventListener("click", async () => {
        const { ok, json } = await postSnapshot($("#snapshotLabel").value);
        if (!ok) { status(json.error, true); return; }
        $("#snapshotLabel").value = "";
        status(`Saved ${json.case_count.toLocaleString()} cases as ${nameOf(json)}.`);
        await refreshSnapshots();
    });

    $("#snapshotBody").addEventListener("click", async (ev) => {
        const btn = ev.target.closest("[data-act]");
        if (!btn) return;
        const s = list[Number(btn.dataset.index)];
        if (!s) return;
        if (btn.dataset.act === "open") {
            const { ok, json } = await postOpenSnapshot(s.id);
            if (!ok) { status(json.error, true); return; }
            status(`Opened ${nameOf(s)}.`);
            await hooks.onOpened(json);
            await refreshSnapshots();
        } else if (btn.dataset.act === "delete") {
            if (!window.confirm(`Delete the snapshot ${nameOf(s)}? This cannot be undone.`)) return;
            const { ok, json } = await deleteSnapshot(s.id);
            if (!ok) { status(json.error, true); return; }
            status(`Deleted ${nameOf(s)}.`);
            await refreshSnapshots();
        }
    });

    $("#btnSnapshotCompare").addEventListener("click", () => {
        const base = list[Number($("#snapshotBase").value)];
        const head = list[Number($("#snapshotHead").value)];
        if (!base || !head) return;
        if (base.id === head.id) { status("Pick two different snapshots to compare.", true); return; }
        hooks.onCompare(base.id, head.id);
    });

    refreshSnapshots();
}
