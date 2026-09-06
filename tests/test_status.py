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
])
def test_invalid_configs_are_rejected(mutate, message):
    cfg = json.loads(json.dumps(MINIMAL))
    mutate(cfg)
    with pytest.raises(ValueError, match=message):
        StatusSet.from_dict(cfg)
