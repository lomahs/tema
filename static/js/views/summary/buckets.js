/**
 * Summary's row transforms: `/api/summary` rows in, one bucket's table rows
 * out.
 *
 * Nothing here writes to the DOM — `document` does not appear in this file.
 * The one read is `filtered()`, which reads the shared Device/File
 * `<select>`s through `$(...)`; that is an input, not a write, so it stays
 * here rather than moving to render.js.
 */
import { $ } from "../../dom.js";
import { groupPath } from "../../groupedTable.js";
import { sumRows } from "../../taxonomy.js";
import {
    BUCKETS, chosenScopes, getFamilies, getGrouping, getGroups, getScopes,
} from "./state.js";

/** The shared filters, applied. */
export function filtered() {
    const device = $("#summaryFilterDevice").value;
    const file = $("#summaryFilterFile").value;
    return getGroups().filter((r) => (!device || r.device === device) && (!file || r.file === file));
}

/**
 * Collapse a scope group's rows to one per file.
 *
 * The Device cell then reports how many devices were summed rather than naming
 * one — a cell reading "iPad" on a row that also counts an iPhone would be a
 * lie, and an empty one would look like missing data.
 *
 * @param {Object[]} rows
 * @returns {Object[]}
 */
function combine(rows) {
    const byFile = new Map();
    rows.forEach((r) => {
        if (!byFile.has(r.file)) byFile.set(r.file, []);
        byFile.get(r.file).push(r);
    });
    return [...byFile.entries()].map(([file, sub]) => {
        const devices = new Set(sub.map((r) => r.device).filter(Boolean)).size;
        return {
            ...sumRows(sub),
            file,
            device: devices ? `${devices} device${devices === 1 ? "" : "s"}` : "—",
        };
    });
}

/**
 * Collapse a scope group's rows to one per (file, device family).
 *
 * The rows arrive already carrying `device_family` — the backend classifies a
 * device name once, so the merged rows here and the published report cannot
 * disagree about which block is which handset. A device no family claims is its
 * own family, keyed by its own name, so this hides nothing: the rows still add
 * up to exactly what Split shows.
 *
 * The Device cell reads the family's configured label and says how many devices
 * it merged when it merged more than one — unlike `combine`, naming the family
 * is not a lie, but "iPhone" standing for two blocks is worth knowing.
 *
 * @param {Object[]} rows
 * @returns {Object[]}
 */
function combineByFamily(rows) {
    const byKey = new Map();
    rows.forEach((r) => {
        const key = groupPath(r.file, r.device_family ?? r.device);
        if (!byKey.has(key)) byKey.set(key, []);
        byKey.get(key).push(r);
    });
    return [...byKey.values()].map((sub) => {
        const family = sub[0].device_family ?? sub[0].device;
        const label = getFamilies().find((f) => f.key === family)?.label || family;
        const devices = new Set(sub.map((r) => r.device).filter(Boolean)).size;
        return {
            ...sumRows(sub),
            file: sub[0].file,
            device_family: family,
            device: devices > 1 ? `${label} (${devices} devices)` : label,
        };
    });
}

/**
 * The scope keys a bucket is currently showing.
 *
 * What a figure drawn on that card was counted over, which is what a drill-in
 * from it has to narrow to. An unknown key answers with every pressed group, so
 * a stale attribute widens the destination rather than emptying it.
 *
 * @param {string} bucketKey
 * @returns {string[]}
 */
export function pressedScopes(bucketKey) {
    const bucket = BUCKETS.find((b) => b.key === bucketKey);
    const groups = bucket ? groupsOf(bucket) : getScopes();
    return groups.filter((g) => chosenScopes.has(g.key)).map((g) => g.key);
}

/** The configured groups belonging to one bucket, in config order. */
export function groupsOf(bucket) {
    return getScopes().filter(bucket.pick);
}

/**
 * Sum a bucket's rows to one row per (file, device).
 *
 * `/api/summary` serves one row per (file, device, scope), which is what let
 * each scope group have its own table. A bucket may hold several groups — two
 * counted commitments, say — and this table has no Scope column to tell them
 * apart, so leaving them unmerged would show two rows that look like duplicates
 * of each other. Summing is the only reading that keeps a row identifiable by
 * what it displays.
 *
 * It is the same collapse the report publisher performs by calling
 * `summary_rows(by_scope=False)`, which is why the screen and the published
 * sheet still agree on what one row means.
 *
 * `device_family` rides across untouched: every row being merged shares a
 * (file, device), so they all carry the same family, and the Rows toggle needs
 * it afterwards.
 *
 * @param {Object[]} rows
 * @returns {Object[]}
 */
function mergeByDevice(rows) {
    const byKey = new Map();
    rows.forEach((r) => {
        const key = groupPath(r.file, r.device);
        if (!byKey.has(key)) byKey.set(key, []);
        byKey.get(key).push(r);
    });
    return [...byKey.values()].map((sub) => ({
        ...sumRows(sub),
        file: sub[0].file,
        device: sub[0].device,
        device_family: sub[0].device_family,
    }));
}

/**
 * One bucket's rows: its pressed groups, merged, then grouped as Rows says.
 *
 * @param {Object} bucket
 * @param {Object[]} rows Every row under the shared Device/File filters.
 * @returns {Object[]}
 */
export function bucketRows(bucket, rows) {
    const keys = new Set(groupsOf(bucket).filter((g) => chosenScopes.has(g.key))
        .map((g) => g.key));
    return regroup(mergeByDevice(rows.filter((r) => keys.has(r.scope))));
}

/** One scope group's rows at the granularity the Rows button is set to. */
function regroup(rows) {
    if (getGrouping() === "combined") return combine(rows);
    if (getGrouping() === "family") return combineByFamily(rows);
    return rows;
}
