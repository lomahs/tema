import json

import pytest

from parser.status import STATUS, StatusSet

MINIMAL = {
    "statuses": [
        {"key": "OK", "match": ["OK", "PASS"]},
        {"key": "NYS", "empty": True},
        {"key": "Other", "fallback": True},
    ],
    "needs_reason": ["Other"],
}


def test_known_results_map_to_their_status():
    assert STATUS.classify("OK") == "OK"
    assert STATUS.classify("NG") == "NG"
    assert STATUS.classify("NG-OK") == "NG-OK"
    assert STATUS.classify("保留") == "Pending"
    assert STATUS.classify("対象外") == "Cancel"


def test_matching_ignores_case_and_surrounding_whitespace():
    assert STATUS.classify("  ok  ") == "OK"
    assert STATUS.classify("ng-ok") == "NG-OK"


def test_blank_results_are_not_yet_started():
    assert STATUS.classify(None) == "NYS"
    assert STATUS.classify("") == "NYS"
    assert STATUS.classify("   ") == "NYS"


def test_unrecognised_results_fall_back_instead_of_vanishing():
    assert STATUS.classify("TBD") == "Other"
    assert STATUS.classify("OK?") == "Other"


def test_executed_statuses_are_the_ones_flagged_in_the_config():
    """Productivity counts these; the rest (Pending, Cancel, NYS) are not work done."""
    assert STATUS.executed == ["OK", "NG", "NG-OK"]


def test_a_config_that_flags_nothing_has_no_executed_statuses():
    assert StatusSet.from_dict(MINIMAL).executed == []


def test_executed_keys_travel_with_the_taxonomy():
    assert STATUS.to_dict()["executed"] == ["OK", "NG", "NG-OK"]


def test_issue_statuses_are_the_ones_flagged_in_the_config():
    """The report's Issues sheet lists these; OK and NYS are not problems."""
    assert STATUS.issue == ["NG", "Pending", "Cancel"]


def test_a_config_that_flags_nothing_has_no_issue_statuses():
    assert StatusSet.from_dict(MINIMAL).issue == []


def test_issue_keys_travel_with_the_taxonomy():
    assert STATUS.to_dict()["issue"] == ["NG", "Pending", "Cancel"]


def test_zero_counts_covers_every_status():
    counts = STATUS.zero_counts()
    assert set(counts) == set(STATUS.keys)
    assert set(counts.values()) == {0}


def test_a_custom_config_changes_the_mapping(tmp_path):
    path = tmp_path / "custom.json"
    path.write_text(json.dumps(MINIMAL), encoding="utf-8")
    custom = StatusSet.load(str(path))

    assert custom.classify("PASS") == "OK"
    assert custom.classify("NG") == "Other"        # not configured here
    assert custom.keys == ["OK", "NYS", "Other"]
    assert custom.needs_reason == ["Other"]


def test_label_and_badge_default_to_sensible_values():
    custom = StatusSet.from_dict(MINIMAL)
    ok = custom.statuses[0]
    assert ok.label == "OK"
    assert ok.badge == "bg-secondary"


def test_text_colour_falls_back_to_the_badge_when_unset():
    config = {
        "statuses": [
            {"key": "OK", "match": ["OK"], "badge": "bg-success"},
            {"key": "NYS", "empty": True, "badge": "bg-secondary"},
            {"key": "Other", "fallback": True},
        ],
    }
    text = {s.key: s.text for s in StatusSet.from_dict(config).statuses}
    assert text == {"OK": "text-success", "NYS": "", "Other": ""}


def test_an_explicit_empty_text_keeps_the_default_body_colour():
    config = dict(MINIMAL)
    config["statuses"] = [
        {**MINIMAL["statuses"][0], "badge": "bg-success", "text": ""},
        *MINIMAL["statuses"][1:],
    ]
    assert StatusSet.from_dict(config).statuses[0].text == ""


def test_statuses_sharing_a_badge_can_differ_in_text_colour():
    text = {s.key: s.text for s in STATUS.statuses}
    assert text["OK"] == text["NG-OK"] == "text-success"
    assert text["NG"] == "text-danger"
    assert text["Pending"] == "text-warning-emphasis"
    assert text["Cancel"] == "text-secondary"
    assert text["NYS"] == ""


@pytest.mark.parametrize("mutate, message", [
    (lambda c: c["statuses"].append({"key": "Extra", "fallback": True}), "fallback"),
    (lambda c: c["statuses"].append({"key": "Extra", "empty": True}), "empty"),
    (lambda c: c["statuses"].append({"key": "OK"}), "duplicate"),
    (lambda c: c["statuses"].append({"key": "Extra", "match": ["PASS"]}), "matched by both"),
    (lambda c: c.__setitem__("needs_reason", ["Nope"]), "unknown status"),
    (lambda c: c.__setitem__("statuses", []), "non-empty list"),
    (lambda c: c["statuses"].append(
        {"key": "Extra", "derive": {"from": "Nope", "when": "no_pic"}}), "unknown status"),
    (lambda c: c["statuses"].append(
        {"key": "Extra", "derive": {"from": "OK", "when": "no_moon"}}), "unknown condition"),
    (lambda c: c["statuses"].append(
        {"key": "Extra", "derive": {"from": "OK"}}), "unknown condition"),
    (lambda c: c["statuses"].append(
        {"key": "Extra", "derive": {"when": "no_pic"}}), "needs a 'from'"),
    (lambda c: c["statuses"].append(
        {"key": "Extra", "derive": "OK"}), "not an object"),
    (lambda c: c["statuses"].append({"key": "Extra", "match": ["SKIP"],
                                     "derive": {"from": "OK", "when": "no_pic"}}), "cannot also set"),
    (lambda c: c["statuses"].extend([
        {"key": "Mid", "derive": {"from": "OK", "when": "no_pic"}},
        {"key": "End", "derive": {"from": "Mid", "when": "no_pic"}}]), "itself derived"),
    (lambda c: c["statuses"].extend([
        {"key": "One", "derive": {"from": "OK", "when": "no_pic"}},
        {"key": "Two", "derive": {"from": "OK", "when": "no_pic"}}]), "both derive from"),
    (lambda c: (c["statuses"].append({"key": "Skip", "excluded": True}),
                c.__setitem__("needs_reason", ["Skip"])), "owes nobody an explanation"),
    (lambda c: c["statuses"].append(
        {"key": "Skip", "excluded": True, "review": True}), "not work to review"),
])
def test_invalid_configs_are_rejected(mutate, message):
    cfg = json.loads(json.dumps(MINIMAL))
    mutate(cfg)
    with pytest.raises(ValueError, match=message):
        StatusSet.from_dict(cfg)


def test_tone_derives_from_the_badge_when_unset():
    """A config written before tones existed still gets sensible colours.

    The UI paints badges, number cells and charts from one semantic tone, so a
    status that only names a Bootstrap badge has its tone inferred from it.
    """
    config = dict(MINIMAL)
    config["statuses"] = [
        {"key": "OK", "match": ["OK"], "badge": "bg-success"},
        {"key": "NG", "match": ["NG"], "badge": "bg-danger"},
        {"key": "Hold", "match": ["HOLD"], "badge": "bg-warning text-dark"},
        {"key": "Skip", "match": ["SKIP"], "badge": "bg-secondary"},
        {"key": "NYS", "empty": True},
        {"key": "Other", "fallback": True, "badge": "bg-dark"},
    ]
    tone = {s.key: s.tone for s in StatusSet.from_dict(config).statuses}
    assert tone == {"OK": "success", "NG": "danger", "Hold": "warn",
                    "Skip": "neutral", "NYS": "neutral", "Other": "muted"}


def test_the_shipped_taxonomy_names_a_tone_for_every_status():
    tone = {s.key: s.tone for s in STATUS.statuses}
    assert tone == {"OK": "success", "NG": "danger", "NG-OK": "warn",
                    "Pending": "warn", "Cancel": "neutral", "NYS": "neutral",
                    "OOS": "muted", "Other": "muted"}


def test_an_explicit_tone_wins_over_the_badge():
    config = dict(MINIMAL)
    config["statuses"] = [
        {**MINIMAL["statuses"][0], "badge": "bg-success", "tone": "warn"},
        *MINIMAL["statuses"][1:],
    ]
    assert StatusSet.from_dict(config).statuses[0].tone == "warn"


def test_an_unknown_tone_is_rejected():
    config = dict(MINIMAL)
    config["statuses"] = [
        {**MINIMAL["statuses"][0], "tone": "chartreuse"},
        *MINIMAL["statuses"][1:],
    ]
    with pytest.raises(ValueError, match="tone"):
        StatusSet.from_dict(config)


def test_tone_defaults_to_neutral_without_a_badge():
    custom = StatusSet.from_dict(MINIMAL)
    assert custom.statuses[0].tone == "neutral"


def test_tone_is_served_to_the_ui():
    assert all("tone" in s for s in STATUS.to_dict()["statuses"])


# --- Derived statuses ------------------------------------------------------
# A status the Result cell alone cannot name. `classify` answers "what does this
# text mean"; `classify_case` answers "what is this row", and only the second can
# see that a Cancel naming no PIC was never in the plan.

def _case(result, pic=None):
    from parser import models
    return models.TestCase(file_name="TC.xlsx", sheet="Login", device="iPhone",
                           result=result, pic=pic)


def test_a_cancelled_case_with_no_pic_is_out_of_scope():
    assert STATUS.classify_case(_case("対象外", pic=None)) == "OOS"


def test_a_cancelled_case_with_a_pic_stays_cancelled():
    """The PIC is what separates a decision someone made from a case nobody owns."""
    assert STATUS.classify_case(_case("対象外", pic="lee")) == "Cancel"


def test_only_the_derived_status_reacts_to_a_missing_pic():
    for result in ("OK", "NG", "NG-OK", "保留", "TBD", None):
        assert STATUS.classify_case(_case(result, pic=None)) == STATUS.classify(result)


def test_classify_still_reads_the_result_cell_alone():
    """`classify` must stay pure: the sample generator and the config rely on it."""
    assert STATUS.classify("対象外") == "Cancel"


def test_the_excluded_statuses_are_the_complement_of_the_counted_ones():
    assert STATUS.excluded == ["OOS"]
    assert set(STATUS.counted).isdisjoint(STATUS.excluded)
    assert set(STATUS.counted) | set(STATUS.excluded) == set(STATUS.keys)


def test_counted_keeps_taxonomy_order():
    assert STATUS.counted == [k for k in STATUS.keys if k not in STATUS.excluded]


def test_an_excluded_status_still_gets_a_zero_count():
    """It owns a column, so it must never be missing from a row."""
    assert set(STATUS.zero_counts()) == set(STATUS.keys)
    assert STATUS.zero_counts()["OOS"] == 0


def test_an_excluded_status_is_never_asked_for_a_reason():
    assert "OOS" not in STATUS.needs_reason


def test_has_derivation_names_the_statuses_that_can_still_change():
    assert STATUS.has_derivation("Cancel")
    assert not STATUS.has_derivation("OOS")
    assert not STATUS.has_derivation("NG")


def test_the_taxonomy_is_published_with_its_excluded_statuses():
    assert STATUS.to_dict()["excluded"] == ["OOS"]


def test_a_config_without_derivations_classifies_a_case_by_its_result_alone():
    plain = StatusSet.from_dict(MINIMAL)
    assert plain.excluded == []
    assert plain.counted == plain.keys
    assert plain.classify_case(_case("OK", pic=None)) == "OK"


# --- Review statuses -------------------------------------------------------
# What the Detail view lists: everything that is not a clean pass, not
# unstarted and not outside the plan.

def test_the_review_statuses_are_the_ones_worth_looking_at():
    assert STATUS.review == ["NG", "NG-OK", "Pending", "Cancel"]


def test_a_clean_pass_and_an_unstarted_case_are_not_for_review():
    for key in ("OK", "NYS"):
        assert key not in STATUS.review


def test_an_out_of_scope_case_is_not_for_review():
    """It is not work outstanding, so it is not work to review."""
    assert "OOS" not in STATUS.review
    assert set(STATUS.review).isdisjoint(STATUS.excluded)


def test_review_keeps_taxonomy_order():
    assert STATUS.review == [k for k in STATUS.keys if k in set(STATUS.review)]


def test_the_taxonomy_is_published_with_its_review_statuses():
    assert STATUS.to_dict()["review"] == STATUS.review


def test_a_config_naming_no_review_statuses_is_allowed():
    assert StatusSet.from_dict(MINIMAL).review == []
