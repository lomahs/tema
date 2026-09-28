/**
 * The Phases & members card: which phases exist, which is active, who is in it.
 *
 * Writes its own DOM, like `editor.js`, and is imported only by `index.js`.
 * Every write answers with the whole overview, which this adopts and redraws;
 * anything that changes what the planner reads (switching or editing the active
 * phase, the roster) is reported through `onChanged`, because reloading the
 * planner, Daily and the Member tab is `index.js`'s job. A write that only changes
 * the list of phases — a new one, a rename — reports through `onListed`, so the
 * phase bar's select is redrawn without reloading every figure. Rows address a phase or
 * a member by index into `data.phases`, never through an attribute holding a name.
 */
import { $, esc } from "../../dom.js";
import {
    deleteMember, deletePhase, postActivatePhase, postMember, postPhase, putPhase,
} from "../../api.js";
import { data } from "./state.js";

let hooks = { onChanged: async () => {}, onListed: () => {} };

const active = () => data.phases.phases.find((p) => p.id === data.phases.active_id);

function error(text) {
    const el = $("#planPhasesError");
    el.textContent = text || "";
    el.hidden = !text;
}

/**
 * Adopt a write's answer.
 * @param {{ok: boolean, json: Object}} res
 * @param {boolean} changed The planner's figures moved and must be reloaded.
 */
async function adopt(res, changed) {
    if (!res.ok) { error(res.json.error); renderPhases(); return; }
    error("");
    data.phases = res.json;
    renderPhases();
    if (changed) await hooks.onChanged();
    else hooks.onListed();
}

/** Draw the card from `data.phases`. */
export function renderPhases() {
    const o = data.phases;
    if (!o) return;
    const only = o.phases.length === 1;
    $("#planPhaseTable").innerHTML = `<thead><tr>
            <th>Name</th><th>Start</th><th>End</th><th class="num">Target</th>
            <th class="num">Members</th><th></th></tr></thead>
        <tbody>${o.phases.map((p, i) => `<tr data-index="${i}"${p.id === o.active_id ? ' class="is-current"' : ""}>
            <td><input class="input" data-field="name" value="${esc(p.name)}" aria-label="Phase name"></td>
            <td><input type="date" class="input input-mono" data-field="phase_start"
                       value="${esc(p.phase_start || "")}" aria-label="Start"></td>
            <td><input type="date" class="input input-mono" data-field="phase_end"
                       value="${esc(p.phase_end || "")}" aria-label="End"></td>
            <td class="num"><input type="number" min="1" class="input input-mono" data-field="daily_target"
                       value="${esc(p.daily_target)}" aria-label="Target per member per day"></td>
            <td class="num">${p.members.length}</td>
            <td class="actions">
                ${p.id === o.active_id ? '<span class="chip">Active</span>'
                  : '<button type="button" class="btn btn-sm" data-act="activate">Make active</button>'}
                <button type="button" class="btn btn-sm btn-quiet" data-act="delete-phase"
                        ${only ? 'disabled title="The last phase cannot be deleted"' : ""}>Delete</button>
            </td></tr>`).join("")}</tbody>`;

    const a = active();
    $("#planMembersHead").textContent = a ? `Members of ${a.name}` : "Members";
    const inPhase = new Set(a ? a.members : []);
    $("#planMembers").innerHTML = o.members.length ? o.members.map((m, i) => `
        <span class="chip plan-member">
            <label class="check">
                <input type="checkbox" data-member="${i}"${inPhase.has(m.name) ? " checked" : ""}>
                <span>${esc(m.name)}</span>
            </label>
            <button type="button" data-act="delete-member" data-member="${i}"
                    aria-label="Remove ${esc(m.name)} from the roster">×</button>
        </span>`).join("")
        : '<p class="empty-note">Nobody on the roster yet. Add people below, or from the names found in the data.</p>';

    $("#planSuggestions").innerHTML = o.suggestions.length ? `
        <span class="label">Found in the data</span>
        ${o.suggestions.map((n, i) => `<button type="button" class="btn btn-sm" data-act="suggest"
            data-suggest="${i}">+ ${esc(n)}</button>`).join("")}
        <button type="button" class="btn btn-sm btn-quiet" data-act="suggest-all">Add all</button>` : "";
}

/** The request body for a phase row, read from its inputs. */
function phaseBody(row) {
    const p = data.phases.phases[Number(row.dataset.index)];
    const field = (f) => row.querySelector(`[data-field="${f}"]`).value;
    return [p, {
        name: field("name"),
        phase_start: field("phase_start") || null,
        phase_end: field("phase_end") || null,
        daily_target: Number(field("daily_target")),
        members: p.members,
    }];
}

/**
 * Wire the card. Call once.
 * @param {{onChanged: () => Promise<void>, onListed: () => void}} opts
 */
export function bindPhases(opts) {
    hooks = { ...hooks, ...opts };
    const card = $("#planPhases");

    // Editing a phase row saves on change, the way the phase bar does.
    card.addEventListener("change", async (ev) => {
        const row = ev.target.closest("#planPhaseTable tr[data-index]");
        if (row && ev.target.dataset.field) {
            const [p, body] = phaseBody(row);
            await adopt(await putPhase(p.id, body), p.id === data.phases.active_id);
            return;
        }
        const box = ev.target.closest("input[data-member]");
        if (box) {
            const a = active();
            const name = data.phases.members[Number(box.dataset.member)].name;
            const members = box.checked ? [...a.members, name] : a.members.filter((n) => n !== name);
            const { id, created_at: _, ...rest } = a;
            await adopt(await putPhase(id, { ...rest, members }), true);
        }
    });

    card.addEventListener("click", async (ev) => {
        const el = ev.target.closest("[data-act]");
        if (!el) return;
        const o = data.phases;
        const row = el.closest("tr[data-index]");
        const phase = row ? o.phases[Number(row.dataset.index)] : null;
        switch (el.dataset.act) {
        case "activate":
            await adopt(await postActivatePhase(phase.id), true);
            break;
        case "delete-phase":
            if (!window.confirm(`Delete ${phase.name} and every day planned in it? This cannot be undone.`)) return;
            await adopt(await deletePhase(phase.id), phase.id === o.active_id);
            break;
        case "create-phase": {
            const res = await postPhase({ name: $("#planNewPhaseName").value });
            if (res.ok) $("#planNewPhaseName").value = "";
            await adopt(res, false);
            break;
        }
        case "add-member": {
            const res = await postMember($("#planNewMember").value, o.active_id);
            if (res.ok) $("#planNewMember").value = "";
            await adopt(res, true);
            break;
        }
        case "delete-member": {
            const m = o.members[Number(el.dataset.member)];
            if (!window.confirm(`Remove ${m.name} from the roster?`)) return;
            await adopt(await deleteMember(m.id), true);
            break;
        }
        case "suggest":
            await adopt(await postMember(o.suggestions[Number(el.dataset.suggest)], o.active_id), true);
            break;
        case "suggest-all": {
            let res = null;
            for (const name of o.suggestions) {
                res = await postMember(name, o.active_id);
                if (!res.ok) break;
            }
            if (res) await adopt(res, true);
            break;
        }
        default: break;
        }
    });
}
