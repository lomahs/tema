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
    """Otherwise the tables would not add up to every case that was loaded."""
    assert SCOPES.classify("Vendor") == "Other"


def test_a_blank_scope_is_not_a_case_at_all():
    """A spreadsheet section heading carries no scope, so it is not work."""
    for blank in (None, "", "   "):
        assert SCOPES.is_unscoped(blank) is True


def test_any_scope_text_at_all_makes_a_case():
    """Including one no group names -- that is what the fallback table is for."""
    for scope in ("FPT", "JP", "Vendor"):
        assert SCOPES.is_unscoped(scope) is False


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
        {"key": "FPT", "label": "FPT", "counted": True},
        # JP work is reported but not committed to — see `scope_groups.json`.
        {"key": "JP", "label": "JP", "counted": False},
        {"key": "Other", "label": "Other", "counted": True},
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


def test_a_group_counts_toward_the_total_unless_it_says_otherwise():
    """Every config that predates the field keeps every group in the plan."""
    plain = ScopeSet.from_dict(MINIMAL)
    assert plain.counted == ["FPT", "JP", "Other"]
    assert plain.excluded == []


def test_an_excluded_group_keeps_its_place_but_leaves_the_counted_list():
    """It still has a table to be drawn in; it is only out of the figures."""
    custom = ScopeSet.from_dict({
        "groups": [
            {"key": "FPT", "match": ["FPT"]},
            {"key": "JP", "match": ["JP"], "excluded": True},
        ],
        "fallback": {"key": "Other"},
    })
    assert custom.keys == ["FPT", "JP", "Other"]
    assert custom.counted == ["FPT", "Other"]
    assert custom.excluded == ["JP"]


def test_is_counted_answers_for_a_raw_scope_cell_the_way_classify_does():
    custom = ScopeSet.from_dict({
        "groups": [
            {"key": "FPT", "match": ["FPT"]},
            {"key": "JP", "match": ["JP"], "excluded": True},
        ],
        "fallback": {"key": "Other"},
    })
    assert custom.is_counted("FPT") is True
    assert custom.is_counted("  jp ") is False
    assert custom.is_counted("Vendor") is True, "the fallback always counts"


def test_the_fallback_group_may_not_be_excluded():
    """It is where a typo'd scope lands. Excluding it would let a mistake vanish
    from every figure, which is the opposite of what the fallback is for."""
    with pytest.raises(ValueError, match="fallback"):
        ScopeSet.from_dict({
            "groups": [{"key": "FPT", "match": ["FPT"]}],
            "fallback": {"key": "Other", "excluded": True},
        })


def test_to_dict_tells_the_view_which_groups_the_figures_include():
    assert ScopeSet.from_dict({
        "groups": [
            {"key": "FPT", "match": ["FPT"]},
            {"key": "JP", "match": ["JP"], "excluded": True},
        ],
        "fallback": {"key": "Other"},
    }).to_dict() == {"groups": [
        {"key": "FPT", "label": "FPT", "counted": True},
        {"key": "JP", "label": "JP", "counted": False},
        {"key": "Other", "label": "Other", "counted": True},
    ]}
