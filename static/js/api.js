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
 * Cases are deliberately **not** among them. Every screen here draws figures,
 * which the aggregates already carry; the rows behind a figure are fetched one
 * status at a time by {@link getCases}, when somebody clicks it. Pulling them
 * all eagerly meant every load carried every case of every workbook before
 * anyone had looked at one.
 *
 * @returns {Promise<{taxonomy: Object, summary: Object, daily: Object[],
 *   productivity: Object[]}>}
 */
export async function fetchAll() {
    const [statusRes, summaryRes, dailyRes, prodRes] = await Promise.all([
        fetch("/api/statuses"),
        fetch("/api/summary"),
        fetch("/api/daily"),
        fetch("/api/productivity"),
    ]);
    return {
        taxonomy: await statusRes.json(),
        summary: await summaryRes.json(),
        daily: await dailyRes.json(),
        productivity: await prodRes.json(),
    };
}

/**
 * The loaded cases of one status: the rows behind a status figure.
 *
 * One status per request, because that is the unit Detail caches — click NG and
 * the NGs arrive once and are kept, click it again and nothing is fetched. The
 * slices partition the load, so two statuses chosen at once are a union with no
 * case counted twice and none unreachable.
 *
 * Covers every scope group, including one the plan excludes: Detail draws a
 * card for it that the reader may deliberately press, and each case names the
 * group it belongs to so the view can leave it out until they do.
 *
 * @param {string} status A status key from the taxonomy.
 * @returns {Promise<ApiResponse>} On success `json` is the case list; a key the
 *   taxonomy no longer names is a 400 with `{error}`.
 */
export async function getCases(status) {
    const res = await fetch(`/api/cases?status=${encodeURIComponent(status)}`);
    return { ok: res.ok, json: await res.json() };
}

/**
 * One workbook, sheet by sheet: the drill-in behind a file name.
 *
 * Deliberately not part of {@link fetchAll}. Every load would otherwise carry
 * per-sheet rows and every case of every file whether or not anybody opened
 * one; fetched here, the cost is proportional to the file actually clicked.
 *
 * @param {string} name Basename of the workbook, as the rows spell it.
 * @returns {Promise<ApiResponse>} On success `json` is `{file, rows, cases}`;
 *   a name nothing loaded answers to is a 404 with `{error}`.
 */
export async function getFile(name) {
    const res = await fetch(`/api/file?name=${encodeURIComponent(name)}`);
    return { ok: res.ok, json: await res.json() };
}

/**
 * The result taxonomy on its own.
 *
 * `fetchAll` also pulls it, but the prepare panel needs its status keys before
 * anything has been loaded — the drawer opens on an empty app.
 *
 * @returns {Promise<Object>} The `/api/statuses` body.
 */
export async function getStatuses() {
    const res = await fetch("/api/statuses");
    return res.json();
}

/**
 * The loaded source's workbooks, and whether each already describes itself.
 * @returns {Promise<ApiResponse>} On success `json` is `{files: [{file, path,
 *   has_tool_data, blocks, error?}]}`; on failure `{error}`.
 */
export async function getPrepareFiles() {
    const res = await fetch("/api/prepare/files");
    return { ok: res.ok, json: await res.json() };
}

/**
 * Detect the TOOL_DATA layout of each workbook, and optionally write it in.
 *
 * Previews unless `apply` is true — a workbook that already has a TOOL_DATA
 * sheet comes back with a `diff` rather than a silent overwrite.
 *
 * @param {string[]} files Server-side paths, as `getPrepareFiles` reported them.
 * @param {boolean} [apply] Write the detected sheet into the workbooks.
 * @returns {Promise<ApiResponse>} On success `json` is `{results: [{file, path,
 *   detected, unresolved, diff, written, error?}]}`; on failure `{error}`.
 */
export async function postPrepareToolData(files, apply = false) {
    const res = await fetch("/api/prepare/tool-data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ files, apply }),
    });
    return { ok: res.ok, json: await res.json() };
}

/**
 * Plan — or carry out — emptying each workbook's result cells.
 *
 * @param {string[]} files Server-side paths.
 * @param {string[]} keep Status keys to carry into the next round.
 * @param {boolean} [apply] Blank the planned cells instead of only reporting them.
 * @returns {Promise<ApiResponse>} On success `json` is `{results: [{file, path,
 *   plan, applied, error?}]}`; on failure `{error}`.
 */
export async function postPrepareClear(files, keep, apply = false) {
    const res = await fetch("/api/prepare/clear", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ files, keep, apply }),
    });
    return { ok: res.ok, json: await res.json() };
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

/**
 * Every editable config file, plus the vocabularies the editor draws from.
 *
 * The tones, the derive conditions and the sheet-label field names come down
 * with the data rather than being listed in `views/config.js`, for the same
 * reason status keys never are: they are the backend's closed sets, and a
 * second copy here would offer choices the validator refuses.
 *
 * @returns {Promise<{configs: Object, vocabulary: Object}>}
 */
export async function getConfig() {
    const res = await fetch("/api/config");
    return res.json();
}

/**
 * Save one config file.
 *
 * A rejected edit changes nothing — the server validates before it writes — so
 * a failed call leaves both the file and the running app as they were, and the
 * form can simply show `json.error` and stay as the user left it.
 *
 * @param {string} name One of the keys `getConfig` returned under `configs`.
 * @param {Object} data The whole config object to write.
 * @returns {Promise<ApiResponse>} On success `json` is `{path, data, error}`
 *   re-read from disk; on failure `{error}` in the validator's own words.
 */
export async function putConfig(name, data) {
    const res = await fetch(`/api/config/${encodeURIComponent(name)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data }),
    });
    return { ok: res.ok, json: await res.json() };
}

/**
 * The plan calendar: one line per day, planned against what was done.
 *
 * Days worked but never planned are included, so the calendar reports what
 * happened rather than only what was intended.
 *
 * @param {{from?: string, to?: string}} [range] Bounds, as "YYYY-MM-DD".
 * @returns {Promise<ApiResponse>} On success `json` is
 *   `{days, planned_total, actual_total}`; on failure `{error}`.
 */
export async function getPlanCalendar(range = {}) {
    const q = new URLSearchParams();
    if (range.from) q.set("from", range.from);
    if (range.to) q.set("to", range.to);
    const res = await fetch(`/api/plan${q.toString() ? `?${q}` : ""}`);
    return { ok: res.ok, json: await res.json() };
}

/**
 * One day's plan, each row joined to what that person actually ran.
 *
 * Rows with an `actual` but no `planned` are work nobody scheduled; they are
 * included deliberately, because a table of a day that hid work done would be
 * wrong rather than tidy.
 *
 * @param {string} date "YYYY-MM-DD".
 * @returns {Promise<ApiResponse>} On success `json` is `{date, rows,
 *   planned_total, actual_total, baseline_total, has_baseline, baseline_at}`.
 */
export async function getPlanDay(date) {
    const res = await fetch(`/api/plan/${encodeURIComponent(date)}`);
    return { ok: res.ok, json: await res.json() };
}

/**
 * Replace one day's rows.
 *
 * The whole day goes at once, the way a config file does: a plan is rearranged
 * as a block, and a refused edit leaves the stored plan exactly as it was.
 *
 * @param {string} date "YYYY-MM-DD".
 * @param {Array<{pic: string, file: string, device: string, planned: number}>} entries
 * @returns {Promise<ApiResponse>} On success `json` is the day view; on failure
 *   `{error}` in the validator's own words.
 */
export async function putPlanDay(date, entries) {
    const res = await fetch(`/api/plan/${encodeURIComponent(date)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entries }),
    });
    return { ok: res.ok, json: await res.json() };
}

/**
 * Judge the day against the plan as it stands now.
 *
 * The baseline is otherwise frozen on the first edit made on or after the day
 * itself; this is the way back from a first edit that was a typo.
 *
 * @param {string} date "YYYY-MM-DD".
 * @returns {Promise<ApiResponse>}
 */
export async function postPlanBaseline(date) {
    const res = await fetch(`/api/plan/${encodeURIComponent(date)}/baseline`,
                            { method: "POST" });
    return { ok: res.ok, json: await res.json() };
}

/**
 * One person across every day they were planned for or worked on.
 * @param {string} pic
 * @returns {Promise<ApiResponse>} On success `json` is
 *   `{pic, rows, planned_total, actual_total}`.
 */
export async function getPlanPerson(pic) {
    const res = await fetch(`/api/plan/person/${encodeURIComponent(pic)}`);
    return { ok: res.ok, json: await res.json() };
}

/**
 * Where a freed-up tester could go: blocks with cases nobody has run.
 *
 * What the day's plan has already handed out is subtracted and named, so two
 * people are not sent to the same block, and `date` is required for exactly
 * that reason — without it the work would read as entirely free.
 *
 * @param {string} date "YYYY-MM-DD".
 * @param {string} [deviceFamily] Narrow to one family, as the rows spell it.
 * @returns {Promise<ApiResponse>} On success `json` is `{date, rows}`, each row
 *   `{file, device, device_family, remaining, total, assigned, free, assigned_to}`.
 */
export async function getPlanSuggest(date, deviceFamily) {
    const q = new URLSearchParams({ date });
    if (deviceFamily) q.set("device_family", deviceFamily);
    const res = await fetch(`/api/plan/suggest?${q}`);
    return { ok: res.ok, json: await res.json() };
}
