/**
 * The source picker at the top of the page: folder-vs-files toggle, the Load
 * and Reload buttons, and the per-file result table.
 *
 * Owns everything about *where* the data comes from; it hands the loaded data
 * off through the `onLoaded` callback and knows nothing about the views.
 */
import { $, esc } from "./dom.js";
import { postBrowse, postLoad, postReload } from "./api.js";

/** localStorage key holding the last source, so a refresh keeps your place. */
const STORAGE_KEY = "tcm_source";

let sourceType, folderGroup, filesGroup, folderPath, filePaths;
let btnLoad, btnReload, btnBrowseFolder, btnBrowseFiles;
let loadStatus, fileResultsWrapper, fileResultsBody;

/**
 * Wire up the panel. Call once, at startup.
 * @param {Object} opts
 * @param {() => Promise<void>} opts.onLoaded Runs after a successful load or
 *   reload, to refresh the views.
 */
export function initSourcePanel({ onLoaded }) {
    sourceType = $("#sourceType");
    folderGroup = $("#folderInputGroup");
    filesGroup = $("#filesInputGroup");
    folderPath = $("#folderPath");
    filePaths = $("#filePaths");
    btnLoad = $("#btnLoad");
    btnReload = $("#btnReload");
    btnBrowseFolder = $("#btnBrowseFolder");
    btnBrowseFiles = $("#btnBrowseFiles");
    loadStatus = $("#loadStatus");
    fileResultsWrapper = $("#fileResultsWrapper");
    fileResultsBody = $("#fileResultsBody");

    restoreSource();

    sourceType.addEventListener("change", () => {
        folderGroup.classList.toggle("d-none", sourceType.value !== "folder");
        filesGroup.classList.toggle("d-none", sourceType.value !== "files");
    });
    // Sync the input visibility with the (possibly restored) dropdown value.
    sourceType.dispatchEvent(new Event("change"));

    btnLoad.addEventListener("click", () => doLoad(onLoaded));
    btnReload.addEventListener("click", () => doReload(onLoaded));
    btnBrowseFolder.addEventListener("click", () => doBrowse("folder"));
    btnBrowseFiles.addEventListener("click", () => doBrowse("files"));
}

/**
 * Where the dialog should open: the folder already in view, or the folder the
 * last listed file sits in. Blank means the OS picks.
 * @param {"folder"|"files"} mode
 * @returns {string}
 */
function initialDir(mode) {
    if (mode === "folder") return folderPath.value.trim();
    const lines = readLines(filePaths.value);
    const last = lines[lines.length - 1];
    if (!last) return "";
    const cut = Math.max(last.lastIndexOf("/"), last.lastIndexOf("\\"));
    return cut > 0 ? last.slice(0, cut) : "";
}

/**
 * Ask the server to open a native dialog, then fill the matching input.
 *
 * Browse only fills the box — loading stays a separate click, so a mis-pick
 * costs nothing. Folder mode replaces the value; file mode appends, so several
 * rounds of picking build one list.
 *
 * @param {"folder"|"files"} mode
 */
async function doBrowse(mode) {
    const btn = mode === "folder" ? btnBrowseFolder : btnBrowseFiles;
    // The dialog is modal and blocking server-side; a second click while it is
    // open would queue up a second dialog behind the first.
    btn.disabled = true;
    try {
        const { ok, json } = await postBrowse(mode, initialDir(mode));
        if (!ok) {
            loadStatus.innerHTML = `<span class="text-danger">${esc(json.error)}</span>`;
            return;
        }
        if (!json.paths.length) return;  // cancelled
        if (mode === "folder") {
            folderPath.value = json.paths[0];
        } else {
            const existing = readLines(filePaths.value);
            const added = json.paths.filter((p) => !existing.includes(p));
            filePaths.value = existing.concat(added).join("\n");
        }
    } catch (e) {
        loadStatus.innerHTML = `<span class="text-danger">Browse failed: ${esc(e.message)}</span>`;
    } finally {
        btn.disabled = false;
    }
}

/**
 * Split a textarea value into trimmed, non-empty lines.
 * @param {string} value
 * @returns {string[]}
 */
function readLines(value) {
    return value.trim().split("\n").map((l) => l.trim()).filter(Boolean);
}

/**
 * Restore the last used source from localStorage.
 *
 * Anything unparseable is ignored rather than thrown: a stale or hand-edited
 * entry should not stop the page from loading.
 */
function restoreSource() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (!saved) return;
    try {
        const s = JSON.parse(saved);
        sourceType.value = s.type;
        if (s.type === "folder") folderPath.value = s.value;
        else filePaths.value = s.value;
    } catch (_) { /* ignore a corrupt entry */ }
}

/**
 * Read the active input into a request body, remembering it for next time.
 * @returns {{folder: string}|{files: string[]}|null} `null` when the input is blank.
 */
function readSource() {
    if (sourceType.value === "folder") {
        const val = folderPath.value.trim();
        if (!val) return null;
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ type: "folder", value: val }));
        return { folder: val };
    }
    const lines = readLines(filePaths.value);
    if (!lines.length) return null;
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ type: "files", value: filePaths.value }));
    return { files: lines };
}

/**
 * Load from the entered folder or file list.
 * @param {() => Promise<void>} onLoaded
 */
async function doLoad(onLoaded) {
    const body = readSource();
    if (!body) return;

    btnLoad.disabled = true;
    loadStatus.innerHTML = '<span class="text-muted">Loading...</span>';

    try {
        const { ok, json } = await postLoad(body);
        if (!ok) {
            showError(json.error);
            return;
        }
        loadStatus.innerHTML = `Loaded <b>${json.loaded}</b> test cases from <b>${json.file_count}</b> file(s).`;
        renderFileResults(json.file_results);
        btnReload.disabled = false;
        await onLoaded();
    } catch (e) {
        loadStatus.innerHTML = `<span class="text-danger">Request failed: ${esc(e.message)}</span>`;
    } finally {
        btnLoad.disabled = false;
    }
}

/**
 * Re-read the source the backend already has.
 * @param {() => Promise<void>} onLoaded
 */
async function doReload(onLoaded) {
    btnReload.disabled = true;
    loadStatus.innerHTML = '<span class="text-muted">Reloading...</span>';
    try {
        const { ok, json } = await postReload();
        if (!ok) {
            showError(json.error);
            return;
        }
        loadStatus.innerHTML = `Reloaded <b>${json.loaded}</b> test cases from <b>${json.file_count}</b> file(s).`;
        renderFileResults(json.file_results);
        await onLoaded();
    } catch (e) {
        loadStatus.innerHTML = `<span class="text-danger">Reload failed: ${esc(e.message)}</span>`;
    } finally {
        btnReload.disabled = false;
    }
}

/**
 * Show an API error and hide the stale per-file table.
 * @param {string} message
 */
function showError(message) {
    loadStatus.innerHTML = `<span class="text-danger">${esc(message)}</span>`;
    fileResultsWrapper.style.display = "none";
}

/**
 * Render the per-file outcome table.
 *
 * One unreadable workbook does not fail the whole load, so this is where a
 * partial success gets reported: OK rows carry a case count, failed rows carry
 * the parser's message.
 *
 * @param {Array<{file: string, status: string, cases?: number, error?: string}>} results
 */
function renderFileResults(results) {
    if (!results || !results.length) {
        fileResultsWrapper.style.display = "none";
        return;
    }
    fileResultsWrapper.style.display = "";
    fileResultsBody.innerHTML = results.map((r, i) => {
        const statusCls = r.status === "OK" ? "text-success" : "text-danger fw-bold";
        return `<tr>
            <td>${i + 1}</td>
            <td>${esc(r.file)}</td>
            <td class="${statusCls}">${esc(r.status)}</td>
            <td>${r.cases != null ? r.cases : "-"}</td>
            <td>${r.error ? esc(r.error) : ""}</td>
        </tr>`;
    }).join("");
}
