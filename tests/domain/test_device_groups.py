"""The device families that let Summary merge "iPhone Min size" into "iPhone"."""
import json

import pytest

from tcm.domain.device import DEVICES, DeviceSet

MINIMAL = {
    "families": [
        {"key": "iPhone", "match": ["iPhone"]},
        {"key": "iPad", "match": ["iPad"]},
    ],
}


def test_a_device_whose_name_contains_the_token_joins_that_family():
    """The whole point: two sizes of one phone are one phone."""
    assert DEVICES.classify("iPhone Min size") == "iPhone"
    assert DEVICES.classify("iPhone Max size") == "iPhone"
    assert DEVICES.classify("iPad Pro") == "iPad"


def test_matching_ignores_case_and_surrounding_space():
    assert DEVICES.classify("  IPHONE 15 pro ") == "iPhone"


def test_an_unmatched_device_is_its_own_family():
    """Nothing is hidden behind a catch-all, so the merged table still adds up."""
    assert DEVICES.classify("Android 14") == "Android 14"
    assert DEVICES.classify("  Windows  ") == "Windows"


def test_a_blank_device_is_its_own_family_too():
    """A device block with no name is one thing, not every nameless thing."""
    assert DEVICES.classify(None) == ""
    assert DEVICES.classify("   ") == ""


def test_the_first_matching_family_wins():
    """Order is meaningful, which is what the Config view's arrows are for."""
    custom = DeviceSet.from_dict({"families": [
        {"key": "Tablet", "match": ["iPad mini"]},
        {"key": "iPad", "match": ["iPad"]},
    ]})
    assert custom.classify("iPad mini 6") == "Tablet"
    assert custom.classify("iPad Pro") == "iPad"


def test_a_family_labels_itself_by_key_when_unlabelled():
    labels = {f.key: f.label for f in DeviceSet.from_dict(MINIMAL).families}
    assert labels == {"iPhone": "iPhone", "iPad": "iPad"}


def test_the_shipped_config_labels_every_family():
    assert all(f.label for f in DEVICES.families)


def test_to_dict_carries_what_the_view_needs_to_title_its_rows():
    assert DEVICES.to_dict() == {"families": [
        {"key": "iPhone", "label": "iPhone"},
        {"key": "iPad", "label": "iPad"},
    ]}


def test_an_empty_family_list_is_allowed_and_merges_nothing():
    """Switching the mode off is a config edit, not a code change."""
    none = DeviceSet.from_dict({"families": []})
    assert none.classify("iPhone Min size") == "iPhone Min size"
    assert none.to_dict() == {"families": []}


@pytest.mark.parametrize("mutate, message", [
    (lambda c: c.__setitem__("families", "iPhone"), "must be a list"),
    (lambda c: c["families"].append({"key": "iPhone", "match": ["X"]}), "duplicate"),
    (lambda c: c["families"].append({"key": "Extra"}), "non-empty 'match'"),
    (lambda c: c["families"].append({"key": "Extra", "match": []}), "non-empty 'match'"),
    (lambda c: c["families"].append({"key": "Extra", "match": [""]}), "empty 'match' value"),
    (lambda c: c["families"].append({"match": ["X"]}), "non-empty 'key'"),
    (lambda c: c["families"].append({"key": "Extra", "match": ["iPad"]}), "already matched by"),
    (lambda c: c["families"].append({"key": "Extra", "match": ["iPad Pro"]}), "already matched by"),
])
def test_invalid_configs_are_rejected(mutate, message):
    cfg = json.loads(json.dumps(MINIMAL))
    mutate(cfg)
    with pytest.raises(ValueError, match=message):
        DeviceSet.from_dict(cfg)


def test_a_token_shadowed_by_an_earlier_one_is_refused_rather_than_left_dead():
    """Everything containing "iPhone" contains "Phone", so the second rule could
    never fire. A rule that cannot match is a typo, not a configuration."""
    with pytest.raises(ValueError, match="already matched by"):
        DeviceSet.from_dict({"families": [
            {"key": "Phone", "match": ["Phone"]},
            {"key": "iPhone", "match": ["iPhone"]},
        ]})


def test_the_error_message_names_the_file_it_came_from(tmp_path):
    path = tmp_path / "devices.json"
    path.write_text(json.dumps({"families": "no"}), encoding="utf-8")
    with pytest.raises(ValueError, match=str(path)):
        DeviceSet.load(str(path))
