"""Reading and writing the editable config files.

`tcm/settings.py` says *where* each config file is; this says how to read one,
how to check an edit, how to write it without being able to leave a broken file
behind, and how to make it take effect in a running app. The Config view is the
only caller, and `/api/config` is a `jsonify` wrapper around these two functions
— the same arrangement as `tcm/services/aggregation.py` and
`tcm/services/preparation.py`, for the same reason: the rules live here, and
what stays in the route is the request.

Three things are worth knowing.

**Validation is not written twice.** An edit is checked by building a throwaway
instance through the config class's own `from_dict`, so every invariant already
documented there — exactly one `empty` status and one `fallback`, `needs_reason`
not naming an excluded status, a derivation being one step, no two scope groups
matching the same string — applies to an edit made from the browser without a
second copy of the rules that could drift from the first.

**A write is atomic.** A half-written `result_status.json` does not make the
taxonomy wrong, it makes the app refuse to start: `_load_default` raises at
import. So the new text goes to a temp file beside the target and `os.replace`
swaps it in, which is one filesystem operation.

**An applied edit mutates the live object rather than replacing it.** Five
modules hold `from tcm.domain.status import STATUS`, and rebinding the name in
`tcm.domain.status` would reach none of them. `adopt` is what makes one save reach
all of them; see `StatusSet.adopt`.

Saving the taxonomy also rebuilds the report layout. `{"expand": "statuses"}` is
materialised into columns when the layout is *built*, so without that a taxonomy
edit would leave the publisher writing the column set the old taxonomy had.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Callable

import tcm.settings as config
from tcm.domain.device import DEVICES, DeviceSet
from tcm.domain.scope import SCOPES, ScopeSet
from tcm.domain.sheet_labels import HEADER_FIELDS, LABELS, RESULT_FIELDS, SheetLabels
from tcm.domain.status import DERIVE_CONDITIONS, STATUS, TONES, StatusSet
from tcm.infrastructure.config_repo import JsonFileConfigRepository
from tcm.infrastructure.report.layout import LAYOUT, ReportLayout

log = logging.getLogger(__name__)

_repo = JsonFileConfigRepository()


def _adopt_statuses(new: StatusSet) -> None:
    STATUS.adopt(new)
    # The report's status columns were expanded against the taxonomy as it was
    # when the layout was built. Rebuild it so the next publish writes the
    # columns the taxonomy now has.
    LAYOUT.adopt(ReportLayout.load(config.REPORT_LAYOUT_CONFIG, status_set=STATUS))


@dataclass(frozen=True)
class ConfigFile:
    """One editable config: where it lives, how to check it, how to apply it."""

    #: Attribute on `tcm.settings` holding the path. Read at call time rather than
    #: captured here, so pointing the app at another file — or a test at a
    #: temp copy — takes effect without rebuilding this table.
    setting: str
    #: `from_dict` of the class that owns this file. Raises `ValueError`.
    build: Callable[[dict, str], object]
    #: Make the validated value the one the running app uses.
    apply: Callable[[object], None]


#: The files the Config view may edit. `config/report_layout.json` is not here:
#: its columns are the geometry of someone's report workbook rather than a
#: vocabulary, and it is rebuilt from disk whenever the taxonomy changes.
CONFIGS: dict[str, ConfigFile] = {
    "statuses": ConfigFile(
        setting="RESULT_STATUS_CONFIG",
        build=StatusSet.from_dict,
        apply=_adopt_statuses,
    ),
    "scopes": ConfigFile(
        setting="SCOPE_GROUPS_CONFIG",
        build=ScopeSet.from_dict,
        apply=SCOPES.adopt,
    ),
    "devices": ConfigFile(
        setting="DEVICE_GROUPS_CONFIG",
        build=DeviceSet.from_dict,
        apply=DEVICES.adopt,
    ),
    "sheet_labels": ConfigFile(
        setting="SHEET_LABELS_CONFIG",
        build=SheetLabels.from_dict,
        apply=LABELS.adopt,
    ),
}


def path_of(name: str) -> str:
    """Where `name`'s file currently lives."""
    return getattr(config, CONFIGS[name].setting)


def read_all() -> dict:
    """Every editable config, plus the vocabularies the editor needs.

    The vocabularies are served rather than written into the JS for the reason
    status keys are: `TONES` and `DERIVE_CONDITIONS` are this module's closed
    sets, and an editor that listed its own copy would offer a tone the
    validator refuses the moment either list changed.
    """
    configs = {}
    for name in CONFIGS:
        path = path_of(name)
        try:
            text = _repo.read_text(path)
            data = json.loads(text)
            error = None
        except Exception as e:
            # A config the app started with cannot be unreadable, but one
            # hand-edited since can be. Reporting it beats an empty form that
            # would overwrite the file with nothing on the first save.
            data, error = None, str(e)
        configs[name] = {"path": path, "data": data, "error": error}

    return {
        "configs": configs,
        "vocabulary": {
            "tones": list(TONES),
            "derive_conditions": sorted(DERIVE_CONDITIONS),
            "header_fields": list(HEADER_FIELDS),
            "result_columns": list(RESULT_FIELDS),
        },
    }


def save(name: str, raw: dict) -> dict:
    """Validate `raw`, write it to `name`'s file, and apply it to this process.

    Raises `KeyError` for an unknown config and `ValueError` — carrying the
    config class's own message — for one that does not validate. Neither
    reaches the filesystem: the file is written only once the value is known to
    be good, so a refused edit leaves the app exactly as it was.

    Returns the freshly re-read config, so the caller redraws from what is on
    disk rather than from what it hoped it sent.
    """
    spec = CONFIGS[name]
    if not isinstance(raw, dict):
        raise ValueError("The config must be a JSON object")

    path = path_of(name)
    # Labelled with the basename, not the path: this message is read in a card
    # that already shows where the file is, and an absolute path in front of
    # every refusal buries the half that says what is wrong with the edit.
    value = spec.build(raw, os.path.basename(path))  # ValueError if invalid

    _repo.write_text(path, json.dumps(raw, indent=2, ensure_ascii=False) + "\n")
    spec.apply(value)
    log.info("Saved %s config to %s", name, path)

    return read_all()["configs"][name]
