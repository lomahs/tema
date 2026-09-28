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
 * The Member tab is not among them either: its figures are measured against the
 * plan, so it is fetched by `views/member/` whenever the load *or* the plan
 * changes, through the four `getMember*` functions below.
 *
 * @returns {Promise<{taxonomy: Object, summary: Object, daily: Object[]}>}
 */
export async function fetchAll() {
    const [statusRes, summaryRes, dailyRes] = await Promise.all([
        fetch("/api/statuses"),
        fetch("/api/summary"),
        fetch("/api/daily"),
    ]);
    return {
        taxonomy: await statusRes.json(),
        summary: await summaryRes.json(),
        daily: await dailyRes.json(),
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
 * The whole phase: KPIs, the burndown and the day-by-day grid.
 *
 * @param {string} [window] Past phase days the forecast pace is read over:
 *   "3", "5", "10" or "all".
 * @returns {Promise<ApiResponse>} On success `json` is `{today, settings, phase,
 *   kpis, burndown, grid}`; on failure `{error}`.
 */
export async function getPlanPhase(window = "5") {
    const res = await fetch(`/api/plan/phase?window=${encodeURIComponent(window)}`);
    return { ok: res.ok, json: await res.json() };
}

/**
 * One day laid out as file x device slots against members.
 *
 * @param {string} date "YYYY-MM-DD".
 * @returns {Promise<ApiResponse>} On success `json` is `{date, today,
 *   daily_target, entries, slots, cells, load, members, available}`.
 */
export async function getPlanBoard(date) {
    const res = await fetch(`/api/plan/board/${encodeURIComponent(date)}`);
    return { ok: res.ok, json: await res.json() };
}

/**
 * Productivity per member through yesterday, with each member's plan beside it.
 *
 * @returns {Promise<ApiResponse>} On success `json` is `{today, through, rows,
 *   team}`; each row carries the executed statuses, the worked-but-not-executed
 *   ones, `executed`, `worked`, `days`, `productivity`, `ng_rate`, `planned` and
 *   `attainment`.
 */
export async function getMemberProductivity() {
    const res = await fetch("/api/member/productivity");
    return { ok: res.ok, json: await res.json() };
}

/**
 * Each member against the plan through yesterday, and the team.
 *
 * @returns {Promise<ApiResponse>} On success `json` is `{today, through,
 *   members: [{pic, aside, planned, actual, executed, cancel, unplanned, delta,
 *   adherence, attainment}], team}`.
 */
export async function getMemberTotals() {
    const res = await fetch("/api/member/totals");
    return { ok: res.ok, json: await res.json() };
}

/**
 * The Monday-to-Friday weeks the member matrix pages through.
 *
 * @returns {Promise<ApiResponse>} On success `json` is `{today, through,
 *   weeks: [{start, end, days: [{date, in_phase}]}], current}`.
 */
export async function getMemberWeeks() {
    const res = await fetch("/api/member/weeks");
    return { ok: res.ok, json: await res.json() };
}

/**
 * One week of the member matrix.
 *
 * @param {string} monday "YYYY-MM-DD", a Monday.
 * @returns {Promise<ApiResponse>} On success `json` is `{today, through, start,
 *   days, cells: {pic: {date: {state, planned, actual, executed, cancel, delta,
 *   short}}}, team: {date: {planned, actual, delta}}}`; on failure `{error}`.
 */
export async function getMemberWeek(monday) {
    const res = await fetch(`/api/member/week/${encodeURIComponent(monday)}`);
    return { ok: res.ok, json: await res.json() };
}

/**
 * The phase and the daily target, with defaults filled in for what was never set.
 * @returns {Promise<ApiResponse>} `{phase_start, phase_end, daily_target, stored}`.
 */
export async function getPlanSettings() {
    const res = await fetch("/api/plan/settings");
    return { ok: res.ok, json: await res.json() };
}

/**
 * Save the phase and the daily target. A refusal stores nothing.
 * @param {{phase_start: string, phase_end: string, daily_target: number}} settings
 * @returns {Promise<ApiResponse>} On failure `{error}` in the validator's words.
 */
export async function putPlanSettings(settings) {
    const res = await fetch("/api/plan/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
    });
    return { ok: res.ok, json: await res.json() };
}

// --- snapshots and phases -----------------------------------------------------

/**
 * A JSON request for the endpoints below. Like the helpers above, a 4xx is an
 * answer, not an exception.
 * @returns {Promise<ApiResponse>}
 */
async function call(url, method = "GET", body) {
    const init = { method };
    if (body !== undefined) {
        init.headers = { "Content-Type": "application/json" };
        init.body = JSON.stringify(body);
    }
    const res = await fetch(url, init);
    return { ok: res.ok, json: await res.json() };
}

/**
 * What is loaded now — including a snapshot the server restored at startup.
 * @returns {Promise<ApiResponse>} `{loaded, file_count, file_results, source, origin}`.
 */
export const getWorkspace = () => call("/api/workspace");

/**
 * The snapshot history, newest first, and the one on screen.
 * @returns {Promise<ApiResponse>} `{snapshots: [{id, taken_at, label, source,
 *   case_count, file_count}], origin}`.
 */
export const getSnapshots = () => call("/api/snapshots");

/** Keep what is loaded now. @param {string} label */
export const postSnapshot = (label) => call("/api/snapshots", "POST", { label });

/** Put a snapshot on screen. Answers like {@link getWorkspace}. @param {number} id */
export const postOpenSnapshot = (id) => call(`/api/snapshots/${id}/open`, "POST");

/** @param {number} id */
export const deleteSnapshot = (id) => call(`/api/snapshots/${id}`, "DELETE");

/**
 * What changed from `base` to `head`.
 * @returns {Promise<ApiResponse>} `{base, head, totals, total, rows, transitions, unchanged}`.
 */
export const getSnapshotCompare = (base, head) =>
    call(`/api/snapshots/compare?base=${encodeURIComponent(base)}&head=${encodeURIComponent(head)}`);

/**
 * Phases and the roster. Every write below answers with the same shape.
 * @returns {Promise<ApiResponse>} `{phases, active_id, members, suggestions}`.
 */
export const getPhases = () => call("/api/phases");
export const postPhase = (body) => call("/api/phases", "POST", body);
export const putPhase = (id, body) => call(`/api/phases/${id}`, "PUT", body);
export const deletePhase = (id) => call(`/api/phases/${id}`, "DELETE");
export const postActivatePhase = (id) => call(`/api/phases/${id}/activate`, "POST");

/**
 * Put someone on the roster.
 * @param {string} name
 * @param {?number} [phaseId] Also put them on this phase.
 */
export const postMember = (name, phaseId = null) =>
    call("/api/members", "POST", { name, phase_id: phaseId });
export const deleteMember = (id) => call(`/api/members/${id}`, "DELETE");
