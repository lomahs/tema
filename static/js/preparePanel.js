/**
 * The "Prepare the workbooks" section of the setup drawer.
 *
 * Mirrors `sourcePanel.js` and `reportPanel.js`: it owns everything about
 * *changing the source files* and knows nothing about the views. The two
 * operations it drives both write to disk, which is why nothing here acts on
 * one click — every button produces a preview, and a second, explicit Apply is
 * what writes.
 *
 * The section stays hidden until something has been loaded, because the file
 * list it works from is the loaded source's.
 */
import { $, esc } from "./dom.js";
import {
    getPrepareFiles, getStatuses, postPrepareClear, postPrepareToolData,
} from "./api.js";

/** localStorage key holding the kept status keys, so a round keeps its choice. */
const STORAGE_KEY = "tcm_prepare_keep";

let section, keepBox, filesBody, filesWrapper, statusLine;
let preview, applyRow, btnApply, btnCancel, btnDetectAll, btnClearAll;

/** Runs after a successful write, so the shell can re-read the changed files. */
let onApplied = async () => {};

/** The taxonomy's statuses, for the keep checkboxes. */
let statuses = [];

/**
 * The file list as the server last reported it.
 *
 * Rows are addressed by index into this array rather than by writing the path
 * into a `data-` attribute: an HTML attribute is not a lossless channel, and a
 * path is the one thing here that must survive a click intact.
 */
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

    section = $("#prepareSection");
    keepBox = $("#keepStatuses");
    filesBody = $("#prepareFilesBody");
    filesWrapper = $("#prepareFilesWrapper");
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

    // One listener for the whole table: rows are redrawn on every refresh.
    filesBody.addEventListener("click", onRowClick);

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
 * Built from `/api/statuses` rather than listed here, so adding a status to
 * `result_status.json` reaches this panel with no change to the JS.
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

/** The keep set, defaulting to Cancel the first time the panel is opened. */
function readKeep() {
    try {
        const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
        if (Array.isArray(saved)) return saved;
    } catch { /* a corrupt entry just means the default */ }
    return ["Cancel"];
}

/** The keys currently ticked. */
function currentKeep() {
    return [...keepBox.querySelectorAll("input:checked")].map((i) => i.value);
}

/**
 * Show the section and re-read the loaded source's files.
 *
 * Called after every load, so a workbook that has just been given a TOOL_DATA
 * sheet shows up as described without a page refresh.
 */
export async function refreshPrepare() {
    section.hidden = false;
    pending = null;
    renderPreview(null);

    let res;
    try {
        res = await getPrepareFiles();
    } catch (e) {
        return setStatus(`Could not list the workbooks: ${e}`, "is-error");
    }
    if (!res.ok) return setStatus(res.json.error, "is-error");

    files = res.json.files;
    renderFiles();
    setStatus("");
}

/** Draw one row per workbook, with the buttons its state allows. */
function renderFiles() {
    filesWrapper.hidden = files.length === 0;

    filesBody.innerHTML = files.map((f, index) => {
        const described = f.has_tool_data;
        const state = f.error
            ? `<span class="is-error">${esc(f.error)}</span>`
            : described
                ? `<span class="mono">${f.blocks} block${f.blocks === 1 ? "" : "s"}</span>`
                : `<span class="muted">none</span>`;

        // A workbook with no TOOL_DATA cannot be cleared: nothing says which
        // cells hold results.
        return `<tr>
            <td class="clip" title="${esc(f.path)}">${esc(f.file)}</td>
            <td>${state}</td>
            <td class="actions">
                <button type="button" class="btn btn-sm" data-act="tool-data" data-index="${index}">
                    ${described ? "Check TOOL_DATA" : "Create TOOL_DATA"}
                </button>
                <button type="button" class="btn btn-sm" data-act="clear" data-index="${index}"
                        ${described ? "" : "disabled title=\"Needs a TOOL_DATA sheet first\""}>
                    Clear results
                </button>
            </td>
        </tr>`;
    }).join("");
}

/** Route a click on either per-row button. */
function onRowClick(event) {
    const btn = event.target.closest("button[data-act]");
    if (!btn || btn.disabled) return;

    const file = files[Number(btn.dataset.index)];
    if (!file) return;

    if (btn.dataset.act === "tool-data") runToolData([file.path]);
    else runClear([file.path]);
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
