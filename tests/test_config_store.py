"""The Config view's backend: validate a config edit, write it, apply it live.

Every test here mutates module-level singletons (`STATUS`, `SCOPES`, `LABELS`,
`LAYOUT`) the way a real save does, so `restore_configs` puts them back. Without
it one test's taxonomy would be the next test's starting point.
"""
import json

import pytest

import config_store
from parser.scope import SCOPES
from parser.sheet_labels import LABELS
from parser.status import STATUS
from report.layout import LAYOUT

#: Every test here writes a config and mutates the live singletons.
pytestmark = pytest.mark.usefixtures("restore_configs")


def taxonomy(**overrides):
    """A minimal valid taxonomy: one match, one empty, one fallback."""
    raw = {
        "statuses": [
            {"key": "OK", "label": "OK", "match": ["OK"], "executed": True, "tone": "success"},
            {"key": "NYS", "label": "NYS", "empty": True, "tone": "neutral"},
            {"key": "Other", "label": "Other", "fallback": True, "tone": "muted"},
        ],
        "needs_reason": [],
    }
    raw.update(overrides)
    return raw


class Case:
    """The two attributes `classify_case` reads."""

    def __init__(self, result, pic=""):
        self.result = result
        self.pic = pic


# --- writing ---------------------------------------------------------------

def test_saving_a_taxonomy_writes_it_to_the_configured_path(config_paths):
    config_store.save("statuses", taxonomy())

    written = json.loads(config_paths["statuses"].read_text(encoding="utf-8"))
    assert [s["key"] for s in written["statuses"]] == ["OK", "NYS", "Other"]


def test_an_invalid_taxonomy_is_refused_and_leaves_the_file_untouched(config_paths):
    before = config_paths["statuses"].read_text(encoding="utf-8")

    # Two statuses claiming "fallback" is one of the invariants `StatusSet`
    # enforces; the point here is that the refusal happens before the write.
    broken = taxonomy(statuses=[
        {"key": "A", "label": "A", "empty": True, "fallback": True},
        {"key": "B", "label": "B", "fallback": True},
    ])

    with pytest.raises(ValueError, match="exactly one status must set"):
        config_store.save("statuses", broken)

    assert config_paths["statuses"].read_text(encoding="utf-8") == before


def test_an_invalid_sheet_labels_save_leaves_the_file_untouched(config_paths):
    before = config_paths["sheet_labels"].read_text(encoding="utf-8")

    with pytest.raises(ValueError):
        config_store.save("sheet_labels", {"header": {}, "result_columns": {}})

    assert config_paths["sheet_labels"].read_text(encoding="utf-8") == before


def test_an_unknown_config_name_is_refused(config_paths):
    with pytest.raises(KeyError):
        config_store.save("report_layout", {})


# --- applying live ---------------------------------------------------------

def test_saving_the_taxonomy_reaches_an_already_imported_STATUS(config_paths):
    """`from parser.status import STATUS` binds the object, so it is mutated.

    Five modules hold that binding. If `save` built a new StatusSet instead of
    changing this one, four of them would go on classifying by the old rules.
    """
    assert STATUS.classify_case(Case("PASS")) == "Other"

    config_store.save("statuses", taxonomy(statuses=[
        {"key": "OK", "label": "OK", "match": ["OK", "PASS"], "tone": "success"},
        {"key": "NYS", "label": "NYS", "empty": True, "tone": "neutral"},
        {"key": "Other", "label": "Other", "fallback": True, "tone": "muted"},
    ]))

    assert STATUS.classify_case(Case("PASS")) == "OK"
    assert STATUS.keys == ["OK", "NYS", "Other"]


def test_saving_a_taxonomy_rebuilds_the_report_layout_columns(config_paths):
    """`{"expand": "statuses"}` is materialised when the layout is built.

    That happens once, at import, so a taxonomy edit that changes `counted`
    would otherwise keep publishing the old set of columns.
    """
    summary = next(s for s in LAYOUT.sheets if s.dataset == "summary")
    before = [c.field for c in summary.columns if c.is_status]
    assert before != ["OK", "NYS", "Other"]

    config_store.save("statuses", taxonomy())

    summary = next(s for s in LAYOUT.sheets if s.dataset == "summary")
    assert [c.field for c in summary.columns if c.is_status] == ["OK", "NYS", "Other"]


def test_an_excluded_status_still_gets_no_report_column(config_paths):
    config_store.save("statuses", taxonomy(statuses=[
        {"key": "OK", "label": "OK", "match": ["OK"], "tone": "success"},
        {"key": "NYS", "label": "NYS", "empty": True, "tone": "neutral"},
        {"key": "OOS", "label": "Out Of Scope", "excluded": True, "tone": "muted"},
        {"key": "Other", "label": "Other", "fallback": True, "tone": "muted"},
    ]))

    summary = next(s for s in LAYOUT.sheets if s.dataset == "summary")
    assert [c.field for c in summary.columns if c.is_status] == ["OK", "NYS", "Other"]


def test_saving_scope_groups_reaches_an_already_imported_SCOPES(config_paths):
    config_store.save("scopes", {
        "groups": [{"key": "VN", "label": "VN", "match": ["VN", "Vietnam"]}],
        "fallback": {"key": "Rest", "label": "Rest"},
    })

    assert SCOPES.classify("Vietnam") == "VN"
    assert SCOPES.classify("FPT") == "Rest"
    assert SCOPES.keys == ["VN", "Rest"]


def test_saving_sheet_labels_reaches_an_already_imported_LABELS(config_paths):
    assert not LABELS.matches_header("test_no_col", "Item")

    config_store.save("sheet_labels", {
        "max_header_scan_rows": 50,
        "device_row_window": 4,
        "device_keywords": ["tablet"],
        "header": {"test_no_col": ["Item"], "scope_col": ["Owner"]},
        "result_columns": {
            "result_col": ["Status"],
            "test_date_col": ["Date"],
            "pic_col": ["Tester"],
            "ticket_id_col": ["Ticket"],
            "note_col": ["Note"],
        },
    })

    assert LABELS.matches_header("test_no_col", "Item")
    assert LABELS.is_device("Tablet(Flex)")
    assert LABELS.max_header_scan_rows == 50


# --- reading ---------------------------------------------------------------

def test_read_all_returns_each_file_with_its_contents(config_paths):
    got = config_store.read_all()

    assert set(got["configs"]) == {"statuses", "scopes", "devices", "sheet_labels"}
    assert got["configs"]["statuses"]["path"] == str(config_paths["statuses"])
    assert got["configs"]["scopes"]["data"]["fallback"]["key"] == "Other"


def test_read_all_reports_the_vocabularies_the_form_needs(config_paths):
    """The editor must not name a tone or a condition itself.

    Same rule as the status keys: the vocabulary is the config module's, so it
    is served rather than written into the JS.
    """
    vocab = config_store.read_all()["vocabulary"]

    assert vocab["tones"] == ["success", "danger", "warn", "neutral", "muted"]
    assert vocab["derive_conditions"] == ["no_pic"]
    assert vocab["header_fields"] == ["test_no_col", "scope_col"]
    assert vocab["result_columns"] == [
        "result_col", "test_date_col", "pic_col", "ticket_id_col", "note_col",
    ]


def test_read_all_reflects_what_was_just_saved(config_paths):
    config_store.save("statuses", taxonomy())

    data = config_store.read_all()["configs"]["statuses"]["data"]
    assert [s["key"] for s in data["statuses"]] == ["OK", "NYS", "Other"]


def test_a_refusal_names_the_file_without_its_whole_path(config_paths):
    """The message is read in a card that already shows the path.

    `from_dict` labels its errors with whatever source it is given, and an
    absolute temp path in front of every message buries the half that says what
    is actually wrong.
    """
    with pytest.raises(ValueError) as raised:
        config_store.save("statuses", taxonomy(statuses=[
            {"key": "A", "match": ["OK"], "empty": True},
            {"key": "B", "match": ["ok"], "fallback": True},
        ]))

    message = str(raised.value)
    assert message.startswith("result_status.json:")
    assert str(config_paths["statuses"].parent) not in message


# --- device families -------------------------------------------------------

def test_saving_device_families_changes_how_a_device_is_classified(config_paths):
    from parser.device import DEVICES

    assert DEVICES.classify("Galaxy S24") == "Galaxy S24"

    config_store.save("devices", {"families": [
        {"key": "Galaxy", "label": "Galaxy", "match": ["Galaxy"]},
    ]})

    assert DEVICES.classify("Galaxy S24") == "Galaxy"
    # Adopted in place, not rebound: eight modules hold this by name.
    assert DEVICES.classify("iPhone Min size") == "iPhone Min size"


def test_an_invalid_device_config_is_refused_and_leaves_the_file_untouched(config_paths):
    before = config_paths["devices"].read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="already matched by"):
        config_store.save("devices", {"families": [
            {"key": "Phone", "match": ["Phone"]},
            {"key": "iPhone", "match": ["iPhone"]},
        ]})

    assert config_paths["devices"].read_text(encoding="utf-8") == before
