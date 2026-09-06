"""Device code sign-in, driven by a stand-in for MSAL. No network, no browser."""
import json
import os
import stat

import pytest

from sharepoint.auth import GraphAuth, NotConfigured, NotSignedIn


class FakeMsalApp:
    """The four MSAL methods `GraphAuth` uses."""

    def __init__(self, accounts=(), silent=None, flow=None, by_flow=None, cache=None):
        self._accounts = list(accounts)
        self._silent = silent
        self._flow = flow or {"user_code": "ABCD-EFGH",
                              "verification_uri": "https://microsoft.com/devicelogin",
                              "expires_in": 900, "message": "Go and type ABCD-EFGH"}
        self._by_flow = by_flow
        self.token_cache = cache
        self.removed = []

    def get_accounts(self):
        return self._accounts

    def acquire_token_silent(self, scopes, account=None):
        return self._silent

    def initiate_device_flow(self, scopes):
        return self._flow

    def acquire_token_by_device_flow(self, flow):
        return self._by_flow

    def remove_account(self, account):
        self.removed.append(account)
        self._accounts.remove(account)


def auth(tmp_path, app=None, client_id="CLIENT", **kwargs):
    app = app if app is not None else FakeMsalApp()
    return GraphAuth(
        client_id=client_id, tenant_id="organizations", scopes=["Files.ReadWrite.All"],
        cache_path=str(tmp_path / "cache.json"), app_factory=lambda cache: app, **kwargs,
    )


def test_no_account_means_signed_out(tmp_path):
    assert auth(tmp_path).status() == {"state": "signed_out", "account": None}


def test_a_cached_account_that_still_refreshes_is_signed_in(tmp_path):
    app = FakeMsalApp(accounts=[{"username": "qa@contoso.com"}],
                      silent={"access_token": "TOKEN"})

    assert auth(tmp_path, app).status() == {"state": "signed_in", "account": "qa@contoso.com"}


def test_an_account_whose_refresh_token_expired_is_signed_out_again(tmp_path):
    """A stale cache entry must not look like a working sign-in."""
    app = FakeMsalApp(accounts=[{"username": "qa@contoso.com"}], silent=None)

    assert auth(tmp_path, app).status()["state"] == "signed_out"


def test_a_token_is_handed_out_when_one_can_be_refreshed_silently(tmp_path):
    app = FakeMsalApp(accounts=[{"username": "qa@contoso.com"}],
                      silent={"access_token": "TOKEN"})

    assert auth(tmp_path, app).token() == "TOKEN"


def test_asking_for_a_token_while_signed_out_says_to_sign_in(tmp_path):
    with pytest.raises(NotSignedIn, match="[Ss]ign in"):
        auth(tmp_path).token()


def test_starting_a_login_returns_the_code_the_user_has_to_type(tmp_path):
    started = auth(tmp_path).begin_device_login()

    assert started["user_code"] == "ABCD-EFGH"
    assert started["verification_uri"] == "https://microsoft.com/devicelogin"


def test_a_device_flow_microsoft_refuses_to_start_is_reported(tmp_path):
    app = FakeMsalApp(flow={"error": "invalid_client",
                            "error_description": "Application not found"})

    with pytest.raises(RuntimeError, match="Application not found"):
        auth(tmp_path, app).begin_device_login()


def test_completing_a_login_leaves_a_usable_token(tmp_path):
    app = FakeMsalApp(by_flow={"access_token": "TOKEN"})
    signed_in = auth(tmp_path, app)

    signed_in.complete_device_login(signed_in.begin_device_login())

    app._accounts = [{"username": "qa@contoso.com"}]
    app._silent = {"access_token": "TOKEN"}
    assert signed_in.token() == "TOKEN"


def test_a_login_the_user_never_finished_is_reported(tmp_path):
    app = FakeMsalApp(by_flow={"error": "expired_token",
                               "error_description": "The code has expired"})
    graph_auth = auth(tmp_path, app)

    with pytest.raises(RuntimeError, match="expired"):
        graph_auth.complete_device_login(graph_auth.begin_device_login())


def test_signing_out_drops_every_account(tmp_path):
    app = FakeMsalApp(accounts=[{"username": "qa@contoso.com"}],
                      silent={"access_token": "TOKEN"})
    graph_auth = auth(tmp_path, app)

    graph_auth.sign_out()

    assert app.removed == [{"username": "qa@contoso.com"}]
    assert graph_auth.status()["state"] == "signed_out"


# --- configuration and the token cache -------------------------------------

def test_without_a_client_id_the_failure_says_so_plainly(tmp_path):
    graph_auth = auth(tmp_path, client_id="")

    assert graph_auth.status() == {"state": "not_configured", "account": None}
    with pytest.raises(NotConfigured, match="GRAPH_CLIENT_ID"):
        graph_auth.token()


def test_a_saved_cache_is_read_back_on_the_next_run(tmp_path):
    path = tmp_path / "nested" / "cache.json"
    first = GraphAuth(client_id="C", tenant_id="organizations", scopes=["S"],
                      cache_path=str(path), app_factory=FakeMsalApp)

    first._cache.deserialize('{"Account": {}}')
    first._save_cache()

    assert json.loads(path.read_text()) == {"Account": {}}


def test_the_cache_file_is_not_readable_by_anyone_else(tmp_path):
    """It holds a refresh token — treat it like a password file."""
    path = tmp_path / "cache.json"
    graph_auth = GraphAuth(client_id="C", tenant_id="organizations", scopes=["S"],
                           cache_path=str(path), app_factory=FakeMsalApp)

    graph_auth._cache.deserialize('{"Account": {}}')
    graph_auth._save_cache()

    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_an_unreadable_cache_does_not_stop_the_app_from_starting(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("this is not json")

    assert auth(tmp_path).status()["state"] == "signed_out"
