/**
 * Changing the source workbooks: give one a TOOL_DATA sheet, or empty last
 * round's results out of it.
 *
 * Mirrors `sourcePanel.js` and `reportPanel.js`: it owns everything about
 * *changing the source files* and knows nothing about the views. The two
 * operations it drives both write to disk, which is why nothing here acts on
 * one click — every button produces a preview, and a second, explicit Apply is
 * what writes.
 *
 * It shares its file list with `sourcePanel`, through `filesTable.js`: one list
 * of workbooks is one table, and what this panel contributes to each row is the
 * TOOL_DATA state and the two buttons. The controls that act on *every*
 * workbook at once stay hidden until a load succeeds, because the list they
 * work from is the loaded source's.
 */
import { $, esc } from "./dom.js";
import {
    getPrepareFiles, getStatuses, postPrepareClear, postPrepareToolData,
} from "./api.js";
import { setActionsEnabled, setPrepareFiles } from "./filesTable.js";

/** localStorage key holding the kept status keys, so a round keeps its choice. */
const STORAGE_KEY = "tcm_prepare_keep";

let controls, keepBox, statusLine;
let preview, applyRow, btnApply, btnCancel, btnDetectAll, btnClearAll;

/** Runs after a successful write, so the shell can re-read the changed files. */
let onApplied = async () => {};

/** The taxonomy's statuses, for the keep checkboxes. */
let statuses = [];

/** The file list as the server last reported it. */
let files = [];

/** The previewed operation awaiting Apply, or `null`. */
let pending = null;

/**
 * Wire up the panel. Call once, at startup.
 * @param {Object} opts
 * @param {() => Promise<void>} opts.onApplied Runs after a write succeeds. The
 *   workbooks on disk no longer match what is loaded, so the caller re-reads
 *   the source — which refreshes this panel's file list on the way through.
 */
export function initPreparePanel({ onApplied: applied }) {
    onApplied = applied;

    controls = $("#prepareControls");
    keepBox = $("#keepStatuses");
    statusLine = $("#prepareStatus");
    preview = $("#preparePreview");
    applyRow = $("#prepareApplyRow");
    btnApply = $("#btnPrepareApply");
    btnCancel = $("#btnPrepareCancel");
    btnDetectAll = $("#btnDetectAll");
    btnClearAll = $("#btnClearAll");

    btnApply.addEventListener("click", doApply);
    btnCancel.addEventListener("click", () => { pending = null; renderPreview(null); });

    btnDetectAll.addEventListener("click", () =>
        runToolData(files.map((f) => f.path)));
    btnClearAll.addEventListener("click", () =>
        runClear(files.filter((f) => f.has_tool_data).map((f) => f.path)));

    loadStatuses();
}

/** Fetch the taxonomy and draw the keep checkboxes. */
async function loadStatuses() {
    try {
        const taxonomy = await getStatuses();
        statuses = taxonomy.statuses || [];
    } catch {
        statuses = [];
    }
    renderKeepChecks();
}

/**
 * Draw one checkbox per status.
 *
 * Built from `/api/statuses` rather than listed here, so adding a status —
 * whether by editing `result_status.json` or from the Config view — reaches
 * this panel with no change to the JS. Redrawn on every `refreshPrepare`,
 * because the taxonomy can now change without the page being reloaded.
 */
function renderKeepChecks() {
    const kept = new Set(readKeep());
    keepBox.innerHTML = statuses.map((s) => `
        <label class="check">
            <input type="checkbox" value="${esc(s.key)}"${kept.has(s.key) ? " checked" : ""}>
            <span class="badge" data-tone="${esc(s.tone)}">${esc(s.label)}</span>
        </label>`).join("");

    keepBox.querySelectorAll("input").forEach((input) =>
        input.addEventListener("change", () => {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(currentKeep()));
            // The plan on screen was drawn for a different keep set.
            if (pending && pending.kind === "clear") { pending = null; renderPreview(null); }
        }));
}

/**
 * The keep set, defaulting to Cancel the first time the panel is opened.
 *
 * Filtered against the taxonomy as it stands now: a status can be renamed or
 * removed from the Config view, and a remembered key that no longer exists is
 * not a choice anyone can make — leaving it in would send the clear endpoint a
 * key it refuses, on behalf of a box nobody could see.
 */
function readKeep() {
    const known = new Set(statuses.map((s) => s.key));
    let saved = ["Cancel"];
    try {
        const stored = JSON.parse(localStorage.getItem(STORAGE_KEY));
        if (Array.isArray(stored)) saved = stored;
    } catch { /* a corrupt entry just means the default */ }
    return saved.filter((key) => known.has(key));
}

/** The keys currently ticked. */
function currentKeep() {
    return [...keepBox.querySelectorAll("input:checked")].map((i) => i.value);
}

/**
 * Show the controls and re-read the loaded source's files.
 *
 * Called after every load, so a workbook that has just been given a TOOL_DATA
 * sheet shows up as described without a page refresh. The rows themselves are
 * drawn by `filesTable`; what is handed over is this panel's half of them.
 */
export async function refreshPrepare() {
    controls.hidden = false;
    pending = null;
    renderPreview(null);

    // The taxonomy may have changed since these boxes were drawn — the Config
    // view can rename or remove a status while the app runs, and this is the
    // one list in the app built from `/api/statuses` outside a view refresh.
    await loadStatuses();

    let res;
    try {
        res = await getPrepareFiles();
    } catch (e) {
        return setStatus(`Could not list the workbooks: ${e}`, "is-error");
    }
    if (!res.ok) return setStatus(res.json.error, "is-error");

    files = res.json.files;
    setPrepareFiles(files);
    setActionsEnabled(true);
    setStatus("");
}

/**
 * Run the action a row's button asked for.
 *
 * `filesTable` reports the workbook's path rather than an index, because the
 * row it was pressed on is a merged one and its position in this panel's list
 * is not the position on screen.
 *
 * @param {string} path
 * @param {"tool-data"|"clear"} action
 */
export function runFileAction(path, action) {
    if (action === "tool-data") runToolData([path]);
    else runClear([path]);
}

// --- previewing ------------------------------------------------------------

/**
 * Whether writing this result would actually change the workbook.
 *
 * A workbook whose TOOL_DATA already matches detection needs no write, and
 * offering one would invite a pointless overwrite of a sheet that is correct.
 */
function wouldChange(result) {
    if (!result.detected.length) return false;
    return result.diff ? result.diff.differs : true;
}

/** Preview what detection would make of these workbooks. */
async function runToolData(paths) {
    if (!paths.length) return setStatus("No workbooks to check.", "is-error");

    startRun("Checking…");
    const res = await postPrepareToolData(paths, false);
    if (!res.ok) return setStatus(res.json.error, "is-error");

    const results = res.json.results;
    const writable = results.filter(wouldChange).map((r) => r.path);
    pending = writable.length ? { kind: "tool-data", paths: writable } : null;

    renderPreview(renderToolDataPreview(results));

    if (pending) {
        setStatus(`${writable.length} workbook(s) would change.`);
    } else if (results.some((r) => r.detected.length)) {
        setStatus("Every workbook already matches what detection found.", "is-ok");
    } else {
        setStatus("Nothing detected — no headers matched.", "is-error");
    }
}

/** Preview which rows a clear would empty. */
async function runClear(paths) {
    if (!paths.length) return setStatus("No workbooks with a TOOL_DATA sheet.", "is-error");

    const keep = currentKeep();
    startRun("Planning…");
    const res = await postPrepareClear(paths, keep, false);
    if (!res.ok) return setStatus(res.json.error, "is-error");

    const results = res.json.results;
    const writable = results.filter((r) => r.plan && r.plan.rows).map((r) => r.path);
    pending = writable.length ? { kind: "clear", paths: writable, keep } : null;

    renderPreview(renderClearPreview(results));
    const rows = results.reduce((n, r) => n + (r.plan ? r.plan.rows : 0), 0);
    setStatus(pending
        ? `${rows.toLocaleString()} row(s) would be cleared in ${writable.length} workbook(s).`
        : "Nothing to clear.", pending ? "" : "is-error");
}

/**
 * Clear the screen before a request goes out.
 *
 * The preview on screen belongs to the last button pressed. Leaving it up while
 * the next one is in flight would show a plan that Apply is no longer for.
 */
function startRun(message) {
    pending = null;
    renderPreview(null);
    setStatus(message);
}

/** Render the preview block, or hide it when there is nothing to show. */
function renderPreview(html) {
    preview.hidden = !html;
    preview.innerHTML = html || "";
    applyRow.hidden = !pending;
    if (pending) {
        btnApply.textContent = pending.kind === "clear"
            ? `Clear ${pending.paths.length} workbook(s)`
            : `Write TOOL_DATA to ${pending.paths.length} workbook(s)`;
    }
}

/** One block per workbook: what was detected, what was not, what would change. */
function renderToolDataPreview(results) {
    return results.map((r) => {
        const lines = [];

        if (r.error) lines.push(`<span class="is-error">${esc(r.error)}</span>`);

        r.detected.forEach((c) => lines.push(
            `${esc(c.sheet)} / <b>${esc(c.device)}</b> &nbsp;rows ${c.start_row}–${c.end_row}` +
            ` &nbsp;<span class="muted">no=${esc(c.test_no_col)} scope=${esc(c.scope_col)}` +
            ` result=${esc(c.result_col)} date=${esc(c.test_date_col)} pic=${esc(c.pic_col)}` +
            ` ticket=${esc(c.ticket_id_col)} note=${esc(c.note_col)}</span>`));

        if (!r.detected.length && !r.error) lines.push(`<span class="muted">nothing detected</span>`);

        r.unresolved.forEach((u) => lines.push(
            `<span class="is-error">unresolved</span> ${esc(u.sheet)} row ${u.row}: ${esc(u.reason)}`));

        if (r.diff) lines.push(...diffLines(r.diff));
        if (r.diff_error) lines.push(`<span class="is-error">${esc(r.diff_error)}</span>`);

        return block(r.file, lines);
    }).join("");
}

/** The comparison against a TOOL_DATA sheet the workbook already has. */
function diffLines(diff) {
    if (!diff.differs) return [`<span class="is-ok">matches the sheet already in the workbook</span>`];

    const lines = [];
    diff.changed.forEach((b) => {
        const fields = b.fields.map((f) =>
            `${esc(f.field)} <s>${esc(f.existing)}</s> → <b>${esc(f.detected)}</b>`).join(", ");
        lines.push(`<b>changed</b> ${esc(b.sheet)} / ${esc(b.device)} &nbsp;${fields}`);
    });
    diff.only_existing.forEach((b) => lines.push(
        `<b>only in the sheet</b> ${esc(b.sheet)} / ${esc(b.device)}` +
        ` <span class="muted">— overwriting would drop it</span>`));
    diff.only_detected.forEach((b) => lines.push(
        `<b>newly detected</b> ${esc(b.sheet)} / ${esc(b.device)}`));
    return lines;
}

/** One block per workbook: which blocks lose rows, and what survives. */
function renderClearPreview(results) {
    return results.map((r) => {
        const lines = [];

        if (r.error) lines.push(`<span class="is-error">${esc(r.error)}</span>`);

        if (r.plan) {
            r.plan.blocks.forEach((b) => lines.push(
                `${esc(b.sheet)} / <b>${esc(b.device)}</b> &nbsp;${b.rows.toLocaleString()} row(s)`));

            if (!r.plan.rows) lines.push(`<span class="muted">nothing to clear</span>`);
            else lines.push(`clearing: ${counts(r.plan.by_status)}`);

            if (Object.keys(r.plan.kept).length) {
                lines.push(`<span class="is-ok">keeping</span>: ${counts(r.plan.kept)}`);
            }
        }

        return block(r.file, lines);
    }).join("");
}

/** A `{key: n}` tally as "OK 12, NG 3", commonest first. */
function counts(tally) {
    return Object.entries(tally)
        .sort((a, b) => b[1] - a[1])
        .map(([key, n]) => `${esc(key)} ${n.toLocaleString()}`)
        .join(", ");
}

/** One file's preview: its name, then its lines. */
function block(file, lines) {
    return `<div class="preview-block">
        <div class="preview-file">${esc(file)}</div>
        ${lines.map((l) => `<div class="preview-line">${l}</div>`).join("")}
    </div>`;
}

// --- applying --------------------------------------------------------------

/** Carry out the previewed operation, then re-read what is on disk. */
async function doApply() {
    if (!pending) return;

    const { kind, paths, keep } = pending;
    btnApply.disabled = true;
    setStatus(kind === "clear" ? "Clearing…" : "Writing…");

    let res;
    try {
        res = kind === "clear"
            ? await postPrepareClear(paths, keep, true)
            : await postPrepareToolData(paths, true);
    } catch (e) {
        return setStatus(`Could not reach the server: ${e}`, "is-error");
    } finally {
        btnApply.disabled = false;
    }

    if (!res.ok) return setStatus(res.json.error, "is-error");

    const results = res.json.results;
    const done = results.filter((r) => (kind === "clear" ? r.applied : r.written)).length;
    const failed = results.filter((r) => r.error);

    pending = null;
    renderPreview(null);

    // The workbooks have changed under the loaded data, so re-read them. This
    // comes back through `refreshPrepare`, redrawing the file list — which is
    // why the status line is written afterwards and not before.
    await onApplied();

    if (failed.length) {
        setStatus(`${done} workbook(s) written; ${failed.length} failed: ` +
            failed.map((r) => `${r.file} — ${r.error}`).join("; "), "is-error");
    } else {
        setStatus(`${done} workbook(s) written.`, "is-ok");
    }
}

/** Write one line of feedback under the table. */
function setStatus(text, cls = "") {
    statusLine.className = `status-line ${cls}`.trim();
    statusLine.textContent = text || "";
}
