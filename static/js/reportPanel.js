/**
 * The SharePoint panel: signing in, and publishing the aggregates to a report
 * workbook.
 *
 * Mirrors `sourcePanel.js` — it owns everything about *where the results go*,
 * and knows nothing about the views. Publishing reads whatever the backend has
 * already loaded, so this module never touches case data itself.
 */
import { $, esc } from "./dom.js";
import {
    getSharePointStatus, postPublishReport, postSharePointLogin, postSharePointLogout,
} from "./api.js";

/** localStorage key holding the report URL, so it survives a refresh. */
const STORAGE_KEY = "tcm_report_url";

/** How often to ask whether the user has finished typing their device code. */
const POLL_MS = 3000;

let reportUrl, btnSignIn, btnSignOut, btnPublish, signInStatus, publishStatus;
let pollTimer = null;

/**
 * Wire up the panel. Call once, at startup.
 */
export function initReportPanel() {
    reportUrl = $("#reportUrl");
    btnSignIn = $("#btnSignIn");
    btnSignOut = $("#btnSignOut");
    btnPublish = $("#btnPublish");
    signInStatus = $("#sharepointStatus");
    publishStatus = $("#publishStatus");

    reportUrl.value = localStorage.getItem(STORAGE_KEY) || "";

    btnSignIn.addEventListener("click", doSignIn);
    btnSignOut.addEventListener("click", doSignOut);
    btnPublish.addEventListener("click", doPublish);

    refreshStatus();
}

/**
 * Enable publishing once there is something to publish.
 *
 * An empty publish would clear the day's rows and write none back, so the
 * button stays disabled until a load has succeeded.
 */
export function setReportEnabled(enabled) {
    btnPublish.disabled = !enabled;
}

// --- signing in ------------------------------------------------------------

/**
 * Read the current sign-in state and render it.
 * @returns {Promise<string>} The state, for the caller's own decisions.
 */
async function refreshStatus() {
    let status;
    try {
        status = await getSharePointStatus();
    } catch (e) {
        signInStatus.innerHTML = `<span class="is-error">${esc(e.message)}</span>`;
        return "error";
    }
    renderStatus(status);
    return status.state;
}

/**
 * @param {{state: string, account: ?string, user_code?: string,
 *   verification_uri?: string, error?: string}} status
 */
function renderStatus(status) {
    const signedIn = status.state === "signed_in";
    btnSignIn.hidden = signedIn;
    btnSignOut.hidden = !signedIn;

    if (signedIn) {
        signInStatus.innerHTML = `<span class="is-ok">Signed in as ${esc(status.account)}</span>`;
        return;
    }
    if (status.state === "not_configured") {
        btnSignIn.disabled = true;
        signInStatus.innerHTML =
            "Set <b>GRAPH_CLIENT_ID</b> to publish to SharePoint. See the README.";
        return;
    }
    btnSignIn.disabled = false;
    if (status.state === "pending") {
        showCode(status.user_code, status.verification_uri);
        return;
    }
    signInStatus.innerHTML = status.error
        ? `<span class="is-error">${esc(status.error)}</span>`
        : "Not signed in.";
}

/**
 * Show the device code and where to type it.
 * @param {string} code
 * @param {string} uri
 */
function showCode(code, uri) {
    signInStatus.innerHTML = `Open <a href="${esc(uri)}" target="_blank" rel="noopener">${esc(uri)}</a>`
        + ` and enter code <b>${esc(code)}</b>, then come back here.`;
}

async function doSignIn() {
    btnSignIn.disabled = true;
    signInStatus.textContent = "Asking Microsoft for a code…";
    try {
        const { ok, json } = await postSharePointLogin();
        if (!ok) {
            signInStatus.innerHTML = `<span class="is-error">${esc(json.error)}</span>`;
            return;
        }
        showCode(json.user_code, json.verification_uri);
        startPolling();
    } catch (e) {
        signInStatus.innerHTML = `<span class="is-error">Sign-in failed: ${esc(e.message)}</span>`;
    } finally {
        btnSignIn.disabled = false;
    }
}

/**
 * Watch for the sign-in finishing.
 *
 * The user is off in another tab typing the code, so the only way to know they
 * are through is to keep asking. Polling stops as soon as the state settles
 * either way.
 */
function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
        const state = await refreshStatus();
        if (state !== "pending") {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }, POLL_MS);
}

async function doSignOut() {
    btnSignOut.disabled = true;
    try {
        await postSharePointLogout();
        await refreshStatus();
    } finally {
        btnSignOut.disabled = false;
    }
}

// --- publishing ------------------------------------------------------------

async function doPublish() {
    const url = reportUrl.value.trim();
    if (!url) {
        publishStatus.innerHTML = '<span class="is-error">Paste the report file link first.</span>';
        return;
    }
    localStorage.setItem(STORAGE_KEY, url);

    btnPublish.disabled = true;
    publishStatus.textContent = "Publishing…";
    try {
        const { ok, json } = await postPublishReport(url);
        if (!ok) {
            // A publish writes sheet by sheet with no way to roll back, so a
            // failure part-way leaves the file partly updated. Say so, and say
            // that re-running is the fix.
            publishStatus.innerHTML =
                `<span class="is-error">${esc(json.error)}</span>`
                + "<br>Nothing may have been written, or only some sheets. Fix the problem"
                + " and publish again — same-day rows are replaced, not duplicated.";
            return;
        }
        publishStatus.innerHTML = renderResult(json);
        await refreshStatus();
    } catch (e) {
        publishStatus.innerHTML = `<span class="is-error">Publish failed: ${esc(e.message)}</span>`;
    } finally {
        btnPublish.disabled = false;
    }
}

/**
 * @param {{file: string, web_url: string, run_date: string,
 *   sheets: Array<{sheet: string, deleted: number, appended: number}>}} result
 * @returns {string} HTML
 */
function renderResult(result) {
    const per = result.sheets.map((s) => {
        const replaced = s.deleted ? ` (replaced ${s.deleted})` : "";
        return `${esc(s.sheet)}: <b>${s.appended}</b>${replaced}`;
    }).join(" &middot; ");

    const link = result.web_url
        ? ` <a href="${esc(result.web_url)}" target="_blank" rel="noopener">Open</a>`
        : "";
    return `<span class="is-ok">Published to <b>${esc(result.file)}</b>`
        + ` for ${esc(result.run_date)}.</span> ${per}.${link}`;
}
