/**
 * The source picker at the top of the Tools view: the folder-vs-files toggle,
 * Browse, and the Load and Reload buttons.
 *
 * Owns everything about *where* the data comes from; it hands the loaded data
 * off through the `onLoaded` callback and knows nothing about the views.
 *
 * It no longer owns the file table. `preparePanel` has as much to say about the
 * same workbooks as this does, so the table is `filesTable.js` and both panels
 * feed it — which is what let the two Tools cards merge without either panel
 * learning the other exists.
 */
import { $, esc } from "./dom.js";
import { postBrowse, postLoad, postReload } from "./api.js";
import { clearFilesTable, setLoadResults } from "./filesTable.js";

/** localStorage key holding the last source, so a refresh keeps your place. */
const STORAGE_KEY = "tcm_source";

let sourceType, folderGroup, filesGroup, folderPath, filePaths;
let btnLoad, btnReload, btnBrowseFolder, btnBrowseFiles;
let loadStatus;

/**
 * Wire up the panel. Call once, at startup.
 * @param {Object} opts
 * @param {(json: Object) => Promise<void>} opts.onLoaded Runs after a successful
 *   load or reload, handed the API response so the shell can report what
 *   arrived and put the setup drawer away.
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

    restoreSource();

    sourceType.addEventListener("change", () => {
        folderGroup.hidden = sourceType.value !== "folder";
        filesGroup.hidden = sourceType.value !== "files";
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
            loadStatus.innerHTML = `<span class="is-error">${esc(json.error)}</span>`;
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
        loadStatus.innerHTML = `<span class="is-error">Browse failed: ${esc(e.message)}</span>`;
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
    loadStatus.textContent = "Loading…";

    try {
        const { ok, json } = await postLoad(body);
        if (!ok) {
            showError(json.error);
            return;
        }
        loadStatus.innerHTML = `Loaded <b>${json.loaded}</b> cases from <b>${json.file_count}</b> file(s).`;
        setLoadResults(json.file_results);
        btnReload.disabled = false;
        await onLoaded(json);
    } catch (e) {
        loadStatus.innerHTML = `<span class="is-error">Request failed: ${esc(e.message)}</span>`;
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
    loadStatus.textContent = "Reloading…";
    try {
        const { ok, json } = await postReload();
        if (!ok) {
            showError(json.error);
            return;
        }
        loadStatus.innerHTML = `Reloaded <b>${json.loaded}</b> cases from <b>${json.file_count}</b> file(s).`;
        setLoadResults(json.file_results);
        await onLoaded(json);
    } catch (e) {
        loadStatus.innerHTML = `<span class="is-error">Reload failed: ${esc(e.message)}</span>`;
    } finally {
        btnReload.disabled = false;
    }
}

/**
 * Show an API error and clear the stale file table.
 * @param {string} message
 */
function showError(message) {
    loadStatus.innerHTML = `<span class="is-error">${esc(message)}</span>`;
    clearFilesTable();
}
