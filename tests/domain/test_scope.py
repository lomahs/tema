"""The scope-group taxonomy that splits Summary into one table per commitment."""
import json

import pytest

from tcm.domain.scope import SCOPES, ScopeSet

MINIMAL = {
    "groups": [
        {"key": "FPT", "match": ["FPT", "FPT (JM Support)"]},
        {"key": "JP", "match": ["JP"]},
    ],
    "fallback": {"key": "Other", "label": "Other"},
}


def test_configured_scopes_map_to_their_group():
    groups = ScopeSet.from_dict(MINIMAL)
    assert groups.classify("FPT") == "FPT"
    assert groups.classify("FPT (JM Support)") == "FPT"
    assert groups.classify("JP") == "JP"


def test_matching_ignores_case_and_surrounding_space():
    groups = ScopeSet.from_dict(MINIMAL)
    assert groups.classify("  fpt (JM support) ") == "FPT"
    assert groups.classify("jp") == "JP"


def test_an_unconfigured_scope_falls_back_instead_of_vanishing():
    """Otherwise the tables would not add up to every case that was loaded.

    Asserted against a config this test owns: which spellings are configured is
    the shipped file's business and changes when somebody edits it, whereas
    *something unconfigured reaching the fallback* is the property.
    """
    groups = ScopeSet.from_dict(MINIMAL)
    assert groups.classify("Vendor") == "Other"


def test_a_blank_scope_is_not_a_case_at_all():
    """A spreadsheet section heading carries no scope, so it is not work."""
    for blank in (None, "", "   "):
        assert SCOPES.is_unscoped(blank) is True


def test_any_scope_text_at_all_makes_a_case():
    """Including one no group names -- that is what the fallback table is for."""
    for scope in ("FPT", "JP", "Vendor"):
        assert SCOPES.is_unscoped(scope) is False


def test_the_fallback_group_is_last():
    groups = ScopeSet.from_dict(MINIMAL)
    assert groups.keys == ["FPT", "JP", "Other"]
    assert groups.keys[-1] == groups.classify("something nobody configured")


def test_a_group_labels_itself_by_key_when_unlabelled():
    labels = {g.key: g.label for g in ScopeSet.from_dict(MINIMAL).groups}
    assert labels == {"FPT": "FPT", "JP": "JP", "Other": "Other"}


def test_the_shipped_config_labels_every_group():
    assert all(g.label for g in SCOPES.groups)


def test_the_shipped_config_holds_what_summary_needs_to_draw_three_tables():
    """An invariant over the shipped file, not a copy of its contents.

    `parser/scope_groups.json` is editable from the Config view, so asserting
    which groups are in it asserts that nobody has used that feature. What must
    hold whatever anybody configures is this: every group tells the view its
    key, label and both roles; exactly one is the fallback; it sorts last and
    never counts; and something else does, or every figure reads zero.
    """
    groups = SCOPES.to_dict()["groups"]

    assert groups, "at least one group"
    for g in groups:
        assert set(g) == {"key", "label", "counted", "fallback"}

    fallbacks = [g for g in groups if g["fallback"]]
    assert len(fallbacks) == 1
    assert groups[-1] is fallbacks[0], "the fallback sorts last"
    assert fallbacks[0]["counted"] is False
    assert any(g["counted"] for g in groups), "something must count"


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
    """Every configured group keeps its place in the plan; the fallback never has one."""
    plain = ScopeSet.from_dict(MINIMAL)
    assert plain.counted == ["FPT", "JP"]
    assert plain.excluded == ["Other"]


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
    assert custom.counted == ["FPT"]
    # Two groups leave the figures for different reasons: JP because the config
    # says so, the fallback because it is the fallback.
    assert custom.excluded == ["JP", "Other"]


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
    assert custom.is_counted("Vendor") is False, "the fallback never counts"


def test_excluding_the_fallback_is_redundant_rather_than_refused():
    """It never counts either way, so the config saying so changes nothing.

    This reverses an earlier rule. The fallback used to be the group that was
    forbidden from being excluded, on the grounds that a typo'd scope must not
    vanish from every figure; it is now the group that is *always* excluded,
    and Summary's third table is where those cases stay visible instead.
    """
    marked = ScopeSet.from_dict({
        "groups": [{"key": "FPT", "match": ["FPT"]}],
        "fallback": {"key": "Other", "excluded": True},
    })
    plain = ScopeSet.from_dict({
        "groups": [{"key": "FPT", "match": ["FPT"]}],
        "fallback": {"key": "Other"},
    })
    assert marked.counted == plain.counted == ["FPT"]
    assert marked.excluded == plain.excluded == ["Other"]


def test_some_group_other_than_the_fallback_must_count():
    """The guarantee the old fallback rule was really making.

    With the fallback counted, at least one group always did. Now that it never
    does, a config excluding every configured group would leave `counted` empty
    and every figure in the app reading zero — so it is refused at the door
    rather than discovered on screen.
    """
    with pytest.raises(ValueError, match="at least one group"):
        ScopeSet.from_dict({
            "groups": [{"key": "FPT", "match": ["FPT"], "excluded": True}],
            "fallback": {"key": "Other"},
        })


def test_to_dict_tells_the_view_which_groups_the_figures_include():
    assert ScopeSet.from_dict({
        "groups": [
            {"key": "FPT", "match": ["FPT"]},
            {"key": "JP", "match": ["JP"], "excluded": True},
        ],
        "fallback": {"key": "Other"},
    }).to_dict() == {"groups": [
        {"key": "FPT", "label": "FPT", "counted": True, "fallback": False},
        {"key": "JP", "label": "JP", "counted": False, "fallback": False},
        {"key": "Other", "label": "Other", "counted": False, "fallback": True},
    ]}
