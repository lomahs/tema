"""The scope-group taxonomy that splits Summary into one table per commitment."""
import json

import pytest

from parser.scope import SCOPES, ScopeSet

MINIMAL = {
    "groups": [
        {"key": "FPT", "match": ["FPT", "FPT (JM Support)"]},
        {"key": "JP", "match": ["JP"]},
    ],
    "fallback": {"key": "Other", "label": "Other"},
}


def test_configured_scopes_map_to_their_group():
    assert SCOPES.classify("FPT") == "FPT"
    assert SCOPES.classify("FPT (JM Support)") == "FPT"
    assert SCOPES.classify("JP") == "JP"


def test_matching_ignores_case_and_surrounding_space():
    assert SCOPES.classify("  fpt (JM support) ") == "FPT"
    assert SCOPES.classify("jp") == "JP"


def test_an_unconfigured_scope_falls_back_instead_of_vanishing():
    """Otherwise the three tables would not add up to what was loaded."""
    assert SCOPES.classify("Vendor") == "Other"


def test_a_blank_scope_falls_back_too():
    """Spreadsheet section headings carry no scope; they still have to land."""
    for blank in (None, "", "   "):
        assert SCOPES.classify(blank) == "Other"


def test_the_fallback_group_is_last():
    assert SCOPES.keys == ["FPT", "JP", "Other"]
    assert SCOPES.keys[-1] == SCOPES.classify("something nobody configured")


def test_a_group_labels_itself_by_key_when_unlabelled():
    labels = {g.key: g.label for g in ScopeSet.from_dict(MINIMAL).groups}
    assert labels == {"FPT": "FPT", "JP": "JP", "Other": "Other"}


def test_the_shipped_config_labels_every_group():
    assert all(g.label for g in SCOPES.groups)


def test_to_dict_carries_what_the_view_needs_to_title_its_tables():
    assert SCOPES.to_dict() == {"groups": [
        {"key": "FPT", "label": "FPT"},
        {"key": "JP", "label": "JP"},
        {"key": "Other", "label": "Other"},
    ]}


def test_a_custom_config_changes_the_split():
    custom = ScopeSet.from_dict({
        "groups": [{"key": "Vendor", "match": ["Acme", "Globex"]}],
        "fallback": {"key": "Internal"},
    })
    assert custom.classify("Acme") == "Vendor"
    assert custom.classify("FPT") == "Internal"
    assert custom.keys == ["Vendor", "Internal"]


@pytest.mark.parametrize("mutate, message", [
    (lambda c: c.__setitem__("groups", []), "non-empty list"),
    (lambda c: c.__setitem__("groups", "FPT"), "non-empty list"),
    (lambda c: c["groups"].append({"key": "FPT", "match": ["X"]}), "duplicate"),
    (lambda c: c["groups"].append({"key": "Extra", "match": ["JP"]}), "matched by both"),
    (lambda c: c["groups"].append({"key": "Extra"}), "non-empty 'match'"),
    (lambda c: c["groups"].append({"key": "Extra", "match": []}), "non-empty 'match'"),
    (lambda c: c["groups"].append({"key": "Extra", "match": [""]}), "empty 'match' value"),
    (lambda c: c["groups"].append({"match": ["X"]}), "non-empty 'key'"),
    (lambda c: c.pop("fallback"), "must be an object"),
    (lambda c: c.__setitem__("fallback", {"label": "x"}), "needs a non-empty 'key'"),
    (lambda c: c.__setitem__("fallback", {"key": "FPT"}), "duplicates a configured group"),
    (lambda c: c.__setitem__("fallback", {"key": "JP"}), "duplicates a configured group"),
])
def test_invalid_configs_are_rejected(mutate, message):
    cfg = json.loads(json.dumps(MINIMAL))
    mutate(cfg)
    with pytest.raises(ValueError, match=message):
        ScopeSet.from_dict(cfg)


def test_the_error_message_names_the_file_it_came_from(tmp_path):
    path = tmp_path / "scopes.json"
    path.write_text(json.dumps({"groups": []}), encoding="utf-8")
    with pytest.raises(ValueError, match=str(path)):
        ScopeSet.load(str(path))
