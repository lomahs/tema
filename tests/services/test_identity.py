"""The device-code flow, without Microsoft."""
import pytest

from tcm.services.identity import IdentityService


class FakeAuth:
    """A TokenProvider that plays back scripted answers."""

    def __init__(self, flow=None, begin_error=None, complete_error=None):
        self.flow = flow or {"user_code": "ABC-123",
                             "verification_uri": "https://microsoft.com/devicelogin",
                             "expires_in": 900}
        self.begin_error = begin_error
        self.complete_error = complete_error
        self.signed_out = False
        self.state = "signed_out"

    def status(self):
        return {"state": self.state}

    def token(self):
        return "token"

    def begin_device_login(self):
        if self.begin_error:
            raise self.begin_error
        return self.flow

    def complete_device_login(self, flow):
        if self.complete_error:
            raise self.complete_error
        self.state = "signed_in"
        return {"ok": True}

    def sign_out(self):
        self.signed_out = True
        self.state = "signed_out"


def inline(fn, *args):
    """Stand-in for the background thread: run it now."""
    fn(*args)


def test_a_login_in_progress_shows_the_code_to_type():
    auth = FakeAuth()
    # Never complete, so the flow stays pending and status can be inspected.
    service = IdentityService(auth, spawn=lambda fn, *a: None)

    body, status = service.begin_login()

    assert status == 200
    assert body["user_code"] == "ABC-123"
    assert service.status()["state"] == "pending"
    assert service.status()["user_code"] == "ABC-123"


def test_a_completed_login_stops_being_pending():
    auth = FakeAuth()
    service = IdentityService(auth, spawn=inline)

    service.begin_login()

    assert auth.state == "signed_in"
    assert service.status()["state"] == "signed_in"


def test_a_failed_login_is_reported_on_the_next_status():
    auth = FakeAuth(complete_error=RuntimeError("expired"))
    service = IdentityService(auth, spawn=inline)

    service.begin_login()

    assert service.status()["error"] == "expired"


def test_signing_out_clears_a_failed_login():
    auth = FakeAuth(complete_error=RuntimeError("expired"))
    service = IdentityService(auth, spawn=inline)
    service.begin_login()

    service.sign_out()

    assert auth.signed_out
    assert "error" not in service.status()
