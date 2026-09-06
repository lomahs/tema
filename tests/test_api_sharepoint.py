"""The SharePoint endpoints: signing in, and publishing what is loaded.

Both the auth object and the publish call are replaced with stand-ins, following
the pattern `tests/test_api.py` uses for the file dialog — patch the name as the
routes module imported it.
"""
import pytest

from api import routes
from app import create_app
from parser import models
from report.publisher import SheetMissing
from sharepoint.auth import NotConfigured, NotSignedIn
from sharepoint.client import GraphError


@pytest.fixture
def client(monkeypatch):
    app = create_app()
    app.config.update(TESTING=True)
    routes._data.update({"cases": [], "file_results": [], "source": None})
    routes._reset_login()
    # Run the background sign-in poll inline, so a test never waits on a thread.
    monkeypatch.setattr(routes, "_spawn", lambda fn, *args: fn(*args))
    with app.test_client() as c:
        yield c


class FakeAuth:
    def __init__(self, state="signed_out", account=None, flow=None,
                 begin_error=None, complete_error=None):
        self._status = {"state": state, "account": account}
        self._flow = flow or {"user_code": "ABCD-EFGH", "expires_in": 900,
                              "verification_uri": "https://microsoft.com/devicelogin"}
        self._begin_error = begin_error
        self._complete_error = complete_error
        self.signed_out = False

    def status(self):
        return dict(self._status)

    def token(self):
        if self._status["state"] == "not_configured":
            raise NotConfigured("Set GRAPH_CLIENT_ID")
        if self._status["state"] != "signed_in":
            raise NotSignedIn("Not signed in to SharePoint. Sign in and try again.")
        return "TOKEN"

    def begin_device_login(self):
        if self._begin_error:
            raise self._begin_error
        return self._flow

    def complete_device_login(self, flow):
        if self._complete_error:
            raise self._complete_error
        self._status = {"state": "signed_in", "account": "qa@contoso.com"}
        return {"access_token": "TOKEN"}

    def sign_out(self):
        self.signed_out = True
        self._status = {"state": "signed_out", "account": None}


def use_auth(monkeypatch, auth):
    monkeypatch.setattr(routes, "_auth", auth)
    return auth


def load_a_case():
    routes._data["cases"] = [models.TestCase(
        file_name="TC.xlsx", sheet="Login", device="iPhone", row_num=4, result="OK")]


# --- status ----------------------------------------------------------------

def test_status_reports_a_signed_out_user(client, monkeypatch):
    use_auth(monkeypatch, FakeAuth())

    body = client.get("/api/sharepoint/status").get_json()

    assert body["state"] == "signed_out"


def test_status_names_the_account_that_is_signed_in(client, monkeypatch):
    use_auth(monkeypatch, FakeAuth("signed_in", "qa@contoso.com"))

    body = client.get("/api/sharepoint/status").get_json()

    assert body == {"state": "signed_in", "account": "qa@contoso.com"}


def test_status_says_when_no_app_registration_is_configured(client, monkeypatch):
    use_auth(monkeypatch, FakeAuth("not_configured"))

    assert client.get("/api/sharepoint/status").get_json()["state"] == "not_configured"


# --- signing in ------------------------------------------------------------

def test_starting_a_login_answers_with_the_code_to_type(client, monkeypatch):
    use_auth(monkeypatch, FakeAuth())

    res = client.post("/api/sharepoint/login")

    assert res.status_code == 200
    assert res.get_json()["user_code"] == "ABCD-EFGH"
    assert res.get_json()["verification_uri"] == "https://microsoft.com/devicelogin"


def test_the_login_is_completed_in_the_background(client, monkeypatch):
    """The request returns the code at once; the wait happens off the request thread."""
    use_auth(monkeypatch, FakeAuth())

    client.post("/api/sharepoint/login")

    assert client.get("/api/sharepoint/status").get_json()["state"] == "signed_in"


def test_a_login_that_fails_leaves_the_reason_on_the_status(client, monkeypatch):
    use_auth(monkeypatch, FakeAuth(complete_error=RuntimeError("The code has expired")))

    client.post("/api/sharepoint/login")
    body = client.get("/api/sharepoint/status").get_json()

    assert body["state"] == "signed_out"
    assert "expired" in body["error"]


def test_signing_in_without_a_client_id_is_refused_with_an_explanation(client, monkeypatch):
    use_auth(monkeypatch, FakeAuth(begin_error=NotConfigured("Set GRAPH_CLIENT_ID")))

    res = client.post("/api/sharepoint/login")

    assert res.status_code == 400
    assert "GRAPH_CLIENT_ID" in res.get_json()["error"]


def test_signing_out_forgets_the_account(client, monkeypatch):
    auth = use_auth(monkeypatch, FakeAuth("signed_in", "qa@contoso.com"))

    client.post("/api/sharepoint/logout")

    assert auth.signed_out
    assert client.get("/api/sharepoint/status").get_json()["state"] == "signed_out"


# --- publishing ------------------------------------------------------------

def publishes(monkeypatch, result=None, raises=None):
    """Stand in for the publish, recording the arguments it was handed."""
    seen = {}

    def fake(cases, graph_client, url, run_date=None):
        seen.update(cases=cases, url=url, run_date=run_date)
        if raises:
            raise raises
        return result or {"file": "QA Report.xlsx", "run_date": "2026-09-06",
                          "web_url": "https://contoso.sharepoint.com/r.xlsx",
                          "sheets": [{"sheet": "Summary", "deleted": 0, "appended": 1}]}

    monkeypatch.setattr(routes, "publish_to_url", fake)
    return seen


def test_publishing_writes_what_is_loaded_and_reports_back(client, monkeypatch):
    use_auth(monkeypatch, FakeAuth("signed_in", "qa@contoso.com"))
    seen = publishes(monkeypatch)
    load_a_case()

    res = client.post("/api/report/publish",
                      json={"url": "https://contoso.sharepoint.com/r.xlsx"})

    assert res.status_code == 200
    assert res.get_json()["file"] == "QA Report.xlsx"
    assert res.get_json()["sheets"][0]["appended"] == 1
    assert seen["cases"] == routes._data["cases"]
    assert seen["url"] == "https://contoso.sharepoint.com/r.xlsx"


def test_a_run_date_can_be_named_explicitly(client, monkeypatch):
    use_auth(monkeypatch, FakeAuth("signed_in"))
    seen = publishes(monkeypatch)
    load_a_case()

    client.post("/api/report/publish", json={"url": "https://x/r.xlsx",
                                             "run_date": "2026-09-01"})

    assert seen["run_date"] == "2026-09-01"


def test_publishing_while_signed_out_asks_the_user_to_sign_in(client, monkeypatch):
    use_auth(monkeypatch, FakeAuth())
    publishes(monkeypatch)
    load_a_case()

    res = client.post("/api/report/publish", json={"url": "https://x/r.xlsx"})

    assert res.status_code == 401
    assert "sign in" in res.get_json()["error"].lower()


def test_publishing_without_a_url_says_so(client, monkeypatch):
    use_auth(monkeypatch, FakeAuth("signed_in"))
    load_a_case()

    res = client.post("/api/report/publish", json={})

    assert res.status_code == 400
    assert "url" in res.get_json()["error"].lower()


def test_publishing_before_anything_is_loaded_is_refused(client, monkeypatch):
    """An empty publish would delete the day's rows and write nothing back."""
    use_auth(monkeypatch, FakeAuth("signed_in"))
    publishes(monkeypatch)

    res = client.post("/api/report/publish", json={"url": "https://x/r.xlsx"})

    assert res.status_code == 400
    assert "load" in res.get_json()["error"].lower()


def test_a_layout_the_report_file_does_not_match_is_reported_as_a_bad_request(
        client, monkeypatch):
    use_auth(monkeypatch, FakeAuth("signed_in"))
    publishes(monkeypatch, raises=SheetMissing("The report file has no sheet named 'Daily'"))
    load_a_case()

    res = client.post("/api/report/publish", json={"url": "https://x/r.xlsx"})

    assert res.status_code == 400
    assert "Daily" in res.get_json()["error"]


def test_a_link_that_is_not_a_sharepoint_url_is_a_bad_request(client, monkeypatch):
    use_auth(monkeypatch, FakeAuth("signed_in"))
    publishes(monkeypatch, raises=ValueError("Expected an https link"))
    load_a_case()

    res = client.post("/api/report/publish", json={"url": "C:\\r.xlsx"})

    assert res.status_code == 400


def test_a_failure_from_graph_is_passed_on_as_a_bad_gateway(client, monkeypatch):
    use_auth(monkeypatch, FakeAuth("signed_in"))
    publishes(monkeypatch, raises=GraphError(423, "resourceLocked", "The file is locked"))
    load_a_case()

    res = client.post("/api/report/publish", json={"url": "https://x/r.xlsx"})

    assert res.status_code == 502
    assert "locked" in res.get_json()["error"]
