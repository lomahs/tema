/**
 * Config: the three data files the rest of the app is driven by, as forms.
 *
 * The taxonomy, the scope groups and the sheet labels have always been "data,
 * not code" — but the only way to change them was to find the JSON on disk.
 * This is the screen that closes that gap, and it is a view rather than a panel
 * because all three are always editable: unlike the prepare controls, none of
 * them needs anything to be loaded first.
 *
 * Three rules shape it.
 *
 * **It names no vocabulary of its own.** The tones, the derive conditions and
 * the sheet-label field names all come from `/api/config`'s `vocabulary`, the
 * same rule that keeps status keys out of the JS. A form offering a tone the
 * validator refuses would be worse than no form.
 *
 * **It edits the file, not a model of the file.** Each row holds the raw object
 * it was drawn from and mutates only the fields it owns, so keys this form does
 * not know about — the legacy `badge` and `text` a pre-tone config carries —
 * survive a save instead of being quietly dropped.
 *
 * **The server is the only validator.** Every invariant lives in `StatusSet`,
 * `ScopeSet` and `SheetLabels`, and a save that breaks one comes back as that
 * class's own message. This form prevents the easy mistakes; it does not own
 * the rules, so the two cannot drift.
 *
 * Like the panels, it knows nothing about the other views. Saving the taxonomy
 * changes what every figure on screen means, so `main.js` — which owns the
 * views — is handed that consequence through `onSaved`.
 */
import { $, esc } from "../dom.js";
import { getConfig, putConfig } from "../api.js";

/** Runs after a successful save, with the name of the config that changed. */
let onSaved = async () => {};

/** The closed sets the backend serves: tones, derive conditions, field names. */
let vocabulary = { tones: [], derive_conditions: [], header_fields: [], result_columns: [] };

/**
 * The working copy of each config, one per card.
 *
 * `data` is what a Save would send and what the form mutates; `saved` is the
 * JSON text last known to be on disk, which is what "has anything changed?" is
 * answered against. Comparing serialised text rather than walking the objects
 * keeps key order part of the answer — reordering statuses *is* a change.
 */
const state = {
    statuses: { data: null, saved: "", path: "", error: null },
    scopes: { data: null, saved: "", path: "", error: null },
    devices: { data: null, saved: "", path: "", error: null },
    sheet_labels: { data: null, saved: "", path: "", error: null },
};

/**
 * Which card each config draws into, and where its reorderable rows live.
 *
 * `list` is named rather than assumed because the row buttons — add, remove,
 * move — are one handler over every card: each config calls its list something
 * different, and `sheet_labels` has no list at all.
 */
const CARDS = {
    statuses: { body: "#configStatuses", render: renderStatuses, list: (d) => d.statuses },
    scopes: { body: "#configScopes", render: renderScopes, list: (d) => d.groups },
    devices: { body: "#configDevices", render: renderDevices, list: (d) => d.families },
    sheet_labels: { body: "#configSheetLabels", render: renderSheetLabels, list: () => null },
};

/**
 * Wire up the view. Call once, at startup.
 * @param {Object} opts
 * @param {(name: string) => Promise<void>} opts.onSaved Runs after a save
 *   succeeds. The taxonomy decides what every status column counts, so the
 *   caller redraws whatever is loaded.
 */
export function initConfigView({ onSaved: saved }) {
    onSaved = saved;

    Object.keys(CARDS).forEach((name) => {
        $(`#configSave-${name}`).addEventListener("click", () => save(name));
        $(`#configRevert-${name}`).addEventListener("click", () => revert(name));
        // One listener per card: rows are redrawn on every edit that changes
        // the shape of the form, so per-control binding would not survive.
        const card = $(`#configCard-${name}`);
        card.addEventListener("input", (e) => onEdit(name, e));
        card.addEventListener("change", (e) => onEdit(name, e));
        card.addEventListener("click", (e) => onCardClick(name, e));
    });

    refreshConfig();
}

/** Re-read every config from disk and redraw. */
export async function refreshConfig() {
    let got;
    try {
        got = await getConfig();
    } catch (e) {
        Object.keys(CARDS).forEach((name) =>
            setStatus(name, `Could not read the config: ${e.message}`, "is-error"));
        return;
    }

    vocabulary = got.vocabulary;
    Object.entries(got.configs).forEach(([name, entry]) => adopt(name, entry));
}

/** Take one config's server state as the new starting point. */
function adopt(name, entry) {
    if (!state[name]) return;
    state[name] = {
        data: entry.data,
        saved: JSON.stringify(entry.data),
        path: entry.path,
        error: entry.error,
    };
    draw(name);
    setStatus(name, "");
}

// --- drawing ---------------------------------------------------------------

/** Redraw one card's form and its footer. */
function draw(name) {
    const card = state[name];
    const target = $(CARDS[name].body);

    $(`#configPath-${name}`).textContent = card.path;

    if (card.error) {
        target.innerHTML = `<p class="empty-note is-error">This file could not be read:
            ${esc(card.error)}. Fix it on disk, then reload the page — saving from
            here would overwrite it with nothing.</p>`;
    } else {
        target.innerHTML = CARDS[name].render(card.data);
    }

    updateDirty(name);
}

/**
 * One row per status.
 *
 * Order is load-bearing — it sets the report's column order and the step of the
 * charts' shading — so the rows carry move buttons rather than being sorted.
 */
function renderStatuses(data) {
    const statuses = data.statuses || [];
    const needs = new Set(data.needs_reason || []);
    const keys = statuses.map((s) => s.key);

    return `<div class="scroll-x scroll-x--flush config-pane">
    <table class="ledger config-grid">
        <thead><tr>
            <th></th><th>Key</th><th>Label</th><th>Matches</th><th>Tone</th>
            <th>Counts as</th><th>Derives from</th><th></th>
        </tr></thead>
        <tbody>${statuses.map((s, i) => `<tr data-row="${i}">
            <td class="config-move">
                <button type="button" class="btn btn-sm" data-act="up" data-row="${i}"
                        title="Move up"${i === 0 ? " disabled" : ""}>↑</button>
                <button type="button" class="btn btn-sm" data-act="down" data-row="${i}"
                        title="Move down"${i === statuses.length - 1 ? " disabled" : ""}>↓</button>
            </td>
            <td><input class="input input-mono config-key" data-field="key" data-row="${i}"
                       value="${esc(s.key)}"></td>
            <td><input class="input" data-field="label" data-row="${i}"
                       value="${esc(s.label)}"></td>
            <td><input class="input" data-field="match" data-row="${i}"
                       value="${esc((s.match || []).join(", "))}"
                       placeholder="${matchHint(s)}"
                       ${s.derive || s.empty || s.fallback ? "disabled" : ""}></td>
            <td>${toneSelect(s, i)}</td>
            <td><div class="config-flags">
                ${flag(i, "executed", "exec", s.executed, "Counts as work carried out")}
                ${flag(i, "issue", "issue", s.issue, "Reaches the report's Issues sheet")}
                ${flag(i, "review", "review", s.review, "Listed in the Review view")}
                ${flag(i, "excluded", "excl.", s.excluded, "Left out of the total, and of the report's columns")}
                ${flag(i, "needs_reason", "reason", needs.has(s.key), "Must carry a ticket id or a note")}
            </div></td>
            <td>${deriveCell(s, i, keys)}</td>
            <td class="actions">
                <button type="button" class="btn btn-sm" data-act="remove" data-row="${i}"
                        title="Remove this status">✕</button>
            </td>
        </tr>`).join("")}</tbody>
    </table></div>
    <div class="config-add">
        <button type="button" class="btn btn-sm" data-act="add">Add status</button>
        <span class="muted">Order sets the report's column order and the charts' shading.</span>
    </div>
    <div class="config-catchalls">
        ${catchAll("empty", "A blank result cell is", statuses,
                   "Every cell nobody has filled in yet lands here.")}
        ${catchAll("fallback", "A result nothing matches is", statuses,
                   "What a typo, or a result nobody has configured, becomes — so every case "
                 + "lands in exactly one column.")}
    </div>`;
}

/**
 * One of the two statuses that is picked once for the whole taxonomy.
 *
 * Exactly one status may be the blank one and exactly one the fallback, which
 * is a fact about the table rather than about any row in it. As a column it was
 * eight radios of which one mattered; as a select it is the single choice it
 * actually is, and the table is two columns narrower for it.
 */
function catchAll(field, label, statuses, note) {
    const current = statuses.find((s) => s[field]);
    const options = statuses.map((s) =>
        `<option value="${esc(s.key)}"${s === current ? " selected" : ""}>` +
        `${esc(s.label || s.key)}</option>`).join("");

    return `<div class="field">
        <label for="cfg-${field}">${esc(label)}</label>
        <select id="cfg-${field}" class="select" data-field="${field}">${options}</select>
        <span class="muted">${esc(note)}</span>
    </div>`;
}

/**
 * What the Matches box says when it is empty.
 *
 * Three statuses match nothing on purpose and the box is disabled for each, so
 * the placeholder has to say *which* reason rather than suggest a value: a
 * greyed "OK, PASS" on the blank-cell status reads as a setting someone
 * deleted.
 */
function matchHint(status) {
    if (status.derive) return "derived — never read off a result cell";
    if (status.empty) return "every blank result cell";
    if (status.fallback) return "every result nothing else matched";
    return "OK, PASS";
}

/** The tone select, with a live badge so the choice is legible as itself. */
function toneSelect(status, i) {
    const options = vocabulary.tones.map((t) =>
        `<option value="${esc(t)}"${t === status.tone ? " selected" : ""}>${esc(t)}</option>`).join("");
    return `<span class="config-tone">
        <span class="badge" data-tone="${esc(status.tone)}">${esc(status.label || status.key)}</span>
        <select class="select" data-field="tone" data-row="${i}">${options}</select>
    </span>`;
}

/**
 * The derivation: which status this one *becomes*, and when.
 *
 * A derived status is never read off a result cell, which is why picking a
 * source here disables the Matches box beside it.
 */
function deriveCell(status, i, keys) {
    const from = status.derive ? status.derive.from : "";
    const when = status.derive ? status.derive.when : (vocabulary.derive_conditions[0] || "");

    const sources = [`<option value="">—</option>`].concat(
        keys.filter((k) => k !== status.key).map((k) =>
            `<option value="${esc(k)}"${k === from ? " selected" : ""}>${esc(k)}</option>`)).join("");
    const conditions = vocabulary.derive_conditions.map((c) =>
        `<option value="${esc(c)}"${c === when ? " selected" : ""}>${esc(c)}</option>`).join("");

    return `<span class="config-derive">
        <select class="select" data-field="derive_from" data-row="${i}">${sources}</select>
        <select class="select" data-field="derive_when" data-row="${i}"
                ${from ? "" : "disabled"}>${conditions}</select>
    </span>`;
}

/** One flag checkbox, labelled short because there are five per row. */
function flag(i, field, label, on, title) {
    return `<label class="check" title="${esc(title)}">
        <input type="checkbox" data-field="${field}" data-row="${i}"${on ? " checked" : ""}>
        <span>${esc(label)}</span>
    </label>`;
}

/**
 * One row per scope group, and the fallback on its own.
 *
 * The fallback is separate because it is not one of the groups: it is what an
 * unrecognised scope becomes, it always sorts last, and it matches nothing by
 * name — which a row with an empty Matches box would not say.
 */
function renderScopes(data) {
    const groups = data.groups || [];
    const fallback = data.fallback || {};

    return `<div class="scroll-x scroll-x--flush config-pane">
    <table class="ledger config-grid">
        <thead><tr><th></th><th>Key</th><th>Label</th><th>Matches these scopes</th><th></th></tr></thead>
        <tbody>${groups.map((g, i) => `<tr data-row="${i}">
            <td class="config-move">
                <button type="button" class="btn btn-sm" data-act="up" data-row="${i}"
                        title="Move up"${i === 0 ? " disabled" : ""}>↑</button>
                <button type="button" class="btn btn-sm" data-act="down" data-row="${i}"
                        title="Move down"${i === groups.length - 1 ? " disabled" : ""}>↓</button>
            </td>
            <td><input class="input input-mono config-key" data-field="key" data-row="${i}"
                       value="${esc(g.key)}"></td>
            <td><input class="input" data-field="label" data-row="${i}" value="${esc(g.label)}"></td>
            <td><input class="input" data-field="match" data-row="${i}"
                       value="${esc((g.match || []).join(", "))}"
                       placeholder="FPT, FPT (JM Support)"></td>
            <td class="actions">
                <button type="button" class="btn btn-sm" data-act="remove" data-row="${i}"
                        title="Remove this group">✕</button>
            </td>
        </tr>`).join("")}</tbody>
    </table></div>
    <div class="config-add">
        <button type="button" class="btn btn-sm" data-act="add">Add group</button>
        <span class="muted">Summary draws one table per group, in this order.</span>
    </div>
    <div class="config-fallback">
        <span class="eyebrow">Catch-all group</span>
        <p class="muted">Where a scope nobody configured lands, so the tables always add up to
           every case loaded. Always drawn last, and it matches nothing by name.</p>
        <div class="row">
            <div class="field">
                <label for="cfgFallbackKey">Key</label>
                <input id="cfgFallbackKey" class="input input-mono" data-field="fallback_key"
                       value="${esc(fallback.key || "")}">
            </div>
            <div class="field">
                <label for="cfgFallbackLabel">Label</label>
                <input id="cfgFallbackLabel" class="input" data-field="fallback_label"
                       value="${esc(fallback.label || "")}">
            </div>
        </div>
    </div>`;
}

/**
 * One row per device family, and no fallback row — deliberately.
 *
 * A device no family claims is its own family, named by itself, so the merged
 * table still accounts for every device. That is the one way this differs from
 * the scope groups above, and it is why the caption talks about order instead:
 * matching is by *substring*, so the first family whose word appears in the
 * device name wins, and "iPad mini" above "iPad" is a meaningful thing to set.
 */
function renderDevices(data) {
    const families = data.families || [];

    return `<div class="scroll-x scroll-x--flush config-pane">
    <table class="ledger config-grid">
        <thead><tr><th></th><th>Key</th><th>Label</th><th>Device name contains</th><th></th></tr></thead>
        <tbody>${families.map((f, i) => `<tr data-row="${i}">
            <td class="config-move">
                <button type="button" class="btn btn-sm" data-act="up" data-row="${i}"
                        title="Move up"${i === 0 ? " disabled" : ""}>↑</button>
                <button type="button" class="btn btn-sm" data-act="down" data-row="${i}"
                        title="Move down"${i === families.length - 1 ? " disabled" : ""}>↓</button>
            </td>
            <td><input class="input input-mono config-key" data-field="key" data-row="${i}"
                       value="${esc(f.key)}"></td>
            <td><input class="input" data-field="label" data-row="${i}" value="${esc(f.label || "")}"></td>
            <td><input class="input" data-field="match" data-row="${i}"
                       value="${esc((f.match || []).join(", "))}"
                       placeholder="iPhone"></td>
            <td class="actions">
                <button type="button" class="btn btn-sm" data-act="remove" data-row="${i}"
                        title="Remove this family">✕</button>
            </td>
        </tr>`).join("")}</tbody>
    </table></div>
    <div class="config-add">
        <button type="button" class="btn btn-sm" data-act="add">Add family</button>
        <span class="muted">The first family whose word appears in the device name wins, so
           put the more specific one higher. A device no family names keeps its own row.</span>
    </div>`;
}

/**
 * The labels TOOL_DATA detection matches sheet cells against.
 *
 * Each group is captioned with *how* its labels are matched, because that is
 * the part the JSON does not say and the part that decides whether a label
 * works: "No." must not also find "Note", but "チケット" should find
 * "チケットNo." without anyone configuring the second spelling.
 */
function renderSheetLabels(data) {
    const header = data.header || {};
    const columns = data.result_columns || {};

    return `
    <div class="config-group">
        <span class="eyebrow">Shared columns · matched exactly</span>
        <p class="muted">The two columns every device block on a sheet shares. An exact match,
           so "No." finds a "No." column and never a "Note" one.</p>
        ${vocabulary.header_fields.map((f) => keywordField(`header.${f}`, f, header[f])).join("")}
    </div>
    <div class="config-group">
        <span class="eyebrow">Result columns · matched as a prefix</span>
        <p class="muted">The five columns each device block carries of its own. Matched on the
           start of the cell, so "チケット" also finds "チケットNo.".</p>
        ${vocabulary.result_columns.map((f) => keywordField(`result_columns.${f}`, f, columns[f])).join("")}
    </div>
    <div class="config-group">
        <span class="eyebrow">Devices · matched anywhere in the cell</span>
        <p class="muted">A device cell reads "Pad(Flex)" or "27系Phone", never a bare "Pad", so
           these match as a substring and ignore case.</p>
        ${keywordField("device_keywords", "device_keywords", data.device_keywords)}
    </div>
    <div class="config-group">
        <span class="eyebrow">How far detection looks</span>
        <div class="row">
            <div class="field">
                <label for="cfgScanRows">Header scan rows</label>
                <input id="cfgScanRows" type="number" min="1" step="1"
                       class="input input-mono" data-field="max_header_scan_rows"
                       value="${esc(data.max_header_scan_rows)}">
                <span class="muted">Rows from the top searched for the header.</span>
            </div>
            <div class="field">
                <label for="cfgDeviceWindow">Device row window</label>
                <input id="cfgDeviceWindow" type="number" min="1" step="1"
                       class="input input-mono" data-field="device_row_window"
                       value="${esc(data.device_row_window)}">
                <span class="muted">Rows above the header a device name may sit in.</span>
            </div>
        </div>
    </div>`;
}

/** One comma-separated keyword list. */
function keywordField(path, label, values) {
    const id = `cfg-${path.replace(/\./g, "-")}`;
    return `<div class="field">
        <label for="${id}" class="mono">${esc(label)}</label>
        <input id="${id}" class="input" data-field="labels" data-path="${esc(path)}"
               value="${esc((values || []).join(", "))}">
    </div>`;
}

// --- editing ---------------------------------------------------------------

/** Split a comma-separated input into trimmed, non-empty values. */
function readList(value) {
    return value.split(",").map((v) => v.trim()).filter(Boolean);
}

/**
 * Set or remove a boolean flag.
 *
 * Removed rather than set to `false`, because the config's own spelling is
 * "absent means no" — writing `"executed": false` into every status would
 * treble the file's width to say nothing.
 */
function setFlag(obj, field, on) {
    if (on) obj[field] = true;
    else delete obj[field];
}

/** Apply one control's new value to the working copy, then redraw if needed. */
function onEdit(name, event) {
    const el = event.target;
    const field = el.dataset.field;
    if (!field) return;

    const card = state[name];
    if (!card.data) return;

    if (name === "statuses") editStatuses(card.data, el, field);
    else if (name === "scopes") editScopes(card.data, el, field);
    else if (name === "devices") editDevices(card.data, el, field);
    else editSheetLabels(card.data, el, field);

    // The fields that change the *shape* of the form — a key other rows refer
    // to, a tone with a badge to repaint, a derivation that disables a box —
    // need the row redrawn. The rest must not be, or the caret would jump to
    // the end of the box on every keystroke.
    if (["tone", "derive_from", "empty", "fallback"].includes(field)) draw(name);
    else updateDirty(name);
}

function editStatuses(data, el, field) {
    if (field === "empty" || field === "fallback") {
        // Exactly one status may hold each, so setting it is also taking it
        // from whoever had it. That is the whole edit, and it belongs to no row.
        data.statuses.forEach((s) => delete s[field]);
        const chosen = data.statuses.find((s) => s.key === el.value);
        if (chosen) chosen[field] = true;
        return;
    }

    const row = data.statuses[Number(el.dataset.row)];
    if (!row) return;

    switch (field) {
        case "key": {
            const before = row.key;
            row.key = el.value.trim();
            // `needs_reason` and any `derive.from` name statuses by key, so a
            // rename has to follow through or the save is refused for naming a
            // status that no longer exists.
            data.needs_reason = (data.needs_reason || []).map((k) => (k === before ? row.key : k));
            data.statuses.forEach((s) => {
                if (s.derive && s.derive.from === before) s.derive.from = row.key;
            });
            break;
        }
        case "label": row.label = el.value; break;
        case "match": row.match = readList(el.value); break;
        case "tone": row.tone = el.value; break;
        case "executed": case "issue": case "review": case "excluded":
            setFlag(row, field, el.checked);
            break;
        case "needs_reason": {
            const keys = new Set(data.needs_reason || []);
            if (el.checked) keys.add(row.key); else keys.delete(row.key);
            // Kept in taxonomy order rather than click order: this list is read
            // by a person as often as by the validator.
            data.needs_reason = data.statuses.map((s) => s.key).filter((k) => keys.has(k));
            break;
        }

        case "derive_from":
            if (el.value) {
                row.derive = { from: el.value, when: row.derive ? row.derive.when
                                                                : vocabulary.derive_conditions[0] };
                // A derived status is never read off a result cell.
                delete row.match;
            } else {
                delete row.derive;
            }
            break;
        case "derive_when":
            if (row.derive) row.derive.when = el.value;
            break;
    }
}

function editDevices(data, el, field) {
    const row = data.families[Number(el.dataset.row)];
    if (!row) return;
    if (field === "key") row.key = el.value.trim();
    else if (field === "label") row.label = el.value;
    else if (field === "match") row.match = readList(el.value);
}


function editScopes(data, el, field) {
    if (field === "fallback_key" || field === "fallback_label") {
        data.fallback = data.fallback || {};
        data.fallback[field === "fallback_key" ? "key" : "label"] = el.value.trim();
        return;
    }

    const row = data.groups[Number(el.dataset.row)];
    if (!row) return;
    if (field === "key") row.key = el.value.trim();
    else if (field === "label") row.label = el.value;
    else if (field === "match") row.match = readList(el.value);
}

function editSheetLabels(data, el, field) {
    if (field === "labels") {
        const [head, tail] = el.dataset.path.split(".");
        if (tail) {
            data[head] = data[head] || {};
            data[head][tail] = readList(el.value);
        } else {
            data[head] = readList(el.value);
        }
        return;
    }
    // The two integers. An empty box stays empty rather than becoming 0: the
    // validator refuses both, and NaN would be the less obvious refusal.
    const n = parseInt(el.value, 10);
    data[field] = Number.isNaN(n) ? el.value : n;
}

/** Add, remove and reorder — the buttons that change the list itself. */
function onCardClick(name, event) {
    const btn = event.target.closest("button[data-act]");
    if (!btn || btn.disabled) return;

    const card = state[name];
    if (!card.data) return;

    const list = CARDS[name].list(card.data);
    if (!list) return;
    const i = Number(btn.dataset.row);

    switch (btn.dataset.act) {
        case "add":
            list.push(name === "statuses"
                ? { key: "", label: "", match: [], tone: vocabulary.tones.at(-1) }
                : { key: "", label: "", match: [] });
            break;
        case "remove": {
            const [gone] = list.splice(i, 1);
            if (name === "statuses" && gone) {
                card.data.needs_reason =
                    (card.data.needs_reason || []).filter((k) => k !== gone.key);
                card.data.statuses.forEach((s) => {
                    if (s.derive && s.derive.from === gone.key) delete s.derive;
                });
            }
            break;
        }
        case "up":
            if (i > 0) list.splice(i - 1, 0, ...list.splice(i, 1));
            break;
        case "down":
            if (i < list.length - 1) list.splice(i + 1, 0, ...list.splice(i, 1));
            break;
        default:
            return;
    }
    draw(name);
}

// --- saving ----------------------------------------------------------------

/** Whether the working copy differs from what is on disk. */
function isDirty(name) {
    const card = state[name];
    return card.data != null && JSON.stringify(card.data) !== card.saved;
}

/** Light up Save and Revert only when there is something to save or revert. */
function updateDirty(name) {
    const dirty = isDirty(name);
    $(`#configSave-${name}`).disabled = !dirty;
    $(`#configRevert-${name}`).disabled = !dirty;
    $(`#configDirty-${name}`).hidden = !dirty;
}

/** Throw the working copy away and redraw from what was last read. */
function revert(name) {
    state[name].data = JSON.parse(state[name].saved);
    draw(name);
    setStatus(name, "");
}

/**
 * Send one config, and report what came back.
 *
 * On success the server's freshly re-read copy replaces the working one, so the
 * form shows what is on disk rather than what was sent — the two differ
 * whenever a value was normalised on the way through.
 */
async function save(name) {
    const btn = $(`#configSave-${name}`);
    btn.disabled = true;
    setStatus(name, "Saving…");

    let res;
    try {
        res = await putConfig(name, state[name].data);
    } catch (e) {
        setStatus(name, `Could not reach the server: ${e.message}`, "is-error");
        updateDirty(name);
        return;
    }

    if (!res.ok) {
        // The message is the config class's own: it names the invariant that
        // was broken. Nothing was written, so the form stays as it is.
        setStatus(name, res.json.error, "is-error");
        updateDirty(name);
        return;
    }

    adopt(name, res.json);
    setStatus(name, "Saved. Applied to the running app — no restart needed.", "is-ok");
    await onSaved(name);
}

/** Write one line of feedback under a card. */
function setStatus(name, text, cls = "") {
    const line = $(`#configStatus-${name}`);
    line.className = `status-line ${cls}`.trim();
    line.textContent = text || "";
}
