"""`/api/config` — what the Config view reads and writes.

The endpoints are `jsonify` wrappers around `config_store`, so what is asserted
here is the request-shaped part: the vocabularies reaching the browser, the
validator's own message surviving as a 400, and a save actually changing what
the other endpoints answer.
"""
import json

import pytest

from app import create_app

#: Every test here saves a config, which mutates the live singletons.
pytestmark = pytest.mark.usefixtures("restore_configs")


@pytest.fixture
def client():
    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


TAXONOMY = {
    "statuses": [
        {"key": "OK", "label": "OK", "match": ["OK", "PASS"], "executed": True,
         "tone": "success"},
        {"key": "NYS", "label": "NYS", "empty": True, "tone": "neutral"},
        {"key": "Other", "label": "Other", "fallback": True, "tone": "muted"},
    ],
    "needs_reason": [],
}


def test_get_config_serves_every_editable_file(client, config_paths):
    res = client.get("/api/config")

    assert res.status_code == 200
    configs = res.get_json()["configs"]
    assert set(configs) == {"statuses", "scopes", "devices", "sheet_labels"}
    assert configs["sheet_labels"]["data"]["device_keywords"] == ["pad", "phone"]


def test_get_config_serves_the_vocabularies_the_form_needs(client, config_paths):
    vocab = client.get("/api/config").get_json()["vocabulary"]

    assert "success" in vocab["tones"]
    assert "no_pic" in vocab["derive_conditions"]
    assert "scope_col" in vocab["header_fields"]


def test_saving_the_taxonomy_changes_what_api_statuses_answers(client, config_paths):
    res = client.put("/api/config/statuses", json={"data": TAXONOMY})

    assert res.status_code == 200
    keys = [s["key"] for s in client.get("/api/statuses").get_json()["statuses"]]
    assert keys == ["OK", "NYS", "Other"]


def test_saving_the_taxonomy_writes_the_file(client, config_paths):
    client.put("/api/config/statuses", json={"data": TAXONOMY})

    written = json.loads(config_paths["statuses"].read_text(encoding="utf-8"))
    assert written["statuses"][0]["match"] == ["OK", "PASS"]


def test_an_invalid_taxonomy_comes_back_as_the_validators_own_message(client, config_paths):
    before = config_paths["statuses"].read_text(encoding="utf-8")

    res = client.put("/api/config/statuses", json={"data": {
        "statuses": [
            {"key": "OK", "label": "OK", "match": ["OK"], "empty": True, "fallback": True},
            {"key": "Dup", "label": "Dup", "match": ["OK"]},
        ],
    }})

    assert res.status_code == 400
    assert "matched by both" in res.get_json()["error"]
    assert config_paths["statuses"].read_text(encoding="utf-8") == before


def test_needs_reason_naming_an_excluded_status_is_refused(client, config_paths):
    """The taxonomy's own rule, reached through the editor rather than the file."""
    res = client.put("/api/config/statuses", json={"data": {
        "statuses": [
            {"key": "OK", "label": "OK", "match": ["OK"]},
            {"key": "NYS", "label": "NYS", "empty": True},
            {"key": "OOS", "label": "Out Of Scope", "excluded": True},
            {"key": "Other", "label": "Other", "fallback": True},
        ],
        "needs_reason": ["OOS"],
    }})

    assert res.status_code == 400
    assert "owes nobody an explanation" in res.get_json()["error"]


def test_an_unknown_config_name_is_a_404(client, config_paths):
    res = client.put("/api/config/report_layout", json={"data": {}})

    assert res.status_code == 404
    assert "report_layout" in res.get_json()["error"]


def test_a_request_with_no_data_object_is_refused(client, config_paths):
    res = client.put("/api/config/statuses", json={})

    assert res.status_code == 400
    assert "data" in res.get_json()["error"]
