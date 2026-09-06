/**
 * Every call to the Flask backend lives here, so no view module talks to
 * `fetch` directly.
 *
 * The POST helpers deliberately do not throw on a 4xx: the API answers errors
 * with a JSON `{error: "..."}` body that the caller renders inline. Network and
 * parse failures still reject, and callers catch those separately.
 */

/**
 * @typedef {{ok: boolean, json: Object}} ApiResponse
 *   `ok` mirrors `Response.ok`; `json` is the decoded body either way.
 */

/**
 * Load test cases from a folder or an explicit file list.
 * @param {{folder: string}|{files: string[]}} body
 * @returns {Promise<ApiResponse>} On success `json` is
 *   `{loaded, file_count, file_results}`; on failure `{error}`.
 */
export async function postLoad(body) {
    const res = await fetch("/api/load", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    return { ok: res.ok, json: await res.json() };
}

/**
 * Open a native folder / file dialog on the server and return what was picked.
 *
 * The browser cannot hand the backend a real filesystem path, so the dialog runs
 * server-side; this works because the server is local.
 *
 * @param {"folder"|"files"} mode
 * @param {string} initial Directory the dialog opens at; "" for the default.
 * @returns {Promise<ApiResponse>} On success `json` is `{paths: string[]}`,
 *   empty when the user cancelled; on failure `{error}`.
 */
export async function postBrowse(mode, initial) {
    const res = await fetch("/api/browse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, initial }),
    });
    return { ok: res.ok, json: await res.json() };
}

/**
 * Re-read whatever source `/api/load` last accepted.
 * @returns {Promise<ApiResponse>} Same shape as {@link postLoad}; errors with
 *   `{error}` when nothing has been loaded yet.
 */
export async function postReload() {
    const res = await fetch("/api/reload", { method: "POST" });
    return { ok: res.ok, json: await res.json() };
}

/**
 * Fetch everything the UI needs for one render pass, in parallel.
 *
 * `taxonomy` must be applied before any view renders, because the status
 * columns of the summary and daily tables are built from it.
 *
 * @returns {Promise<{taxonomy: Object, cases: Object[], summary: Object,
 *   daily: Object[], productivity: Object[]}>}
 */
export async function fetchAll() {
    const [statusRes, dataRes, summaryRes, dailyRes, prodRes] = await Promise.all([
        fetch("/api/statuses"),
        fetch("/api/data"),
        fetch("/api/summary"),
        fetch("/api/daily"),
        fetch("/api/productivity"),
    ]);
    return {
        taxonomy: await statusRes.json(),
        cases: await dataRes.json(),
        summary: await summaryRes.json(),
        daily: await dailyRes.json(),
        productivity: await prodRes.json(),
    };
}

/**
 * Who is signed in to SharePoint, or how far a device login has got.
 * @returns {Promise<{state: string, account: ?string, user_code?: string,
 *   verification_uri?: string, error?: string}>} `state` is one of
 *   "not_configured", "signed_out", "pending" or "signed_in".
 */
export async function getSharePointStatus() {
    const res = await fetch("/api/sharepoint/status");
    return res.json();
}

/**
 * Start a device code sign-in. Returns as soon as Microsoft issues the code;
 * the user then types it in, and {@link getSharePointStatus} reports when they
 * are through.
 * @returns {Promise<ApiResponse>} On success `json` is
 *   `{user_code, verification_uri, expires_in}`; on failure `{error}`.
 */
export async function postSharePointLogin() {
    const res = await fetch("/api/sharepoint/login", { method: "POST" });
    return { ok: res.ok, json: await res.json() };
}

/**
 * Forget the cached SharePoint account.
 * @returns {Promise<ApiResponse>}
 */
export async function postSharePointLogout() {
    const res = await fetch("/api/sharepoint/logout", { method: "POST" });
    return { ok: res.ok, json: await res.json() };
}

/**
 * Write the current aggregates into the report workbook at `url`.
 *
 * Rows already carrying the run date are replaced, so publishing twice in a day
 * updates that day rather than duplicating it.
 *
 * @param {string} url SharePoint link to the report file.
 * @param {string} [runDate] "YYYY-MM-DD"; the server uses today when omitted.
 * @returns {Promise<ApiResponse>} On success `json` is
 *   `{file, web_url, run_date, sheets: [{sheet, deleted, appended}]}`;
 *   on failure `{error}`.
 */
export async function postPublishReport(url, runDate) {
    const body = runDate ? { url, run_date: runDate } : { url };
    const res = await fetch("/api/report/publish", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    return { ok: res.ok, json: await res.json() };
}
