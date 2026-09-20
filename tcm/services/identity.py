"""Who is signed in to Microsoft Graph, and how far a sign-in has got.

The device flow takes as long as the user takes to type a code into a browser,
which is minutes -- far too long to hold a request open on a single-threaded
dev server. So `begin_login` answers as soon as Microsoft hands back a code and
waits for the rest on a background thread, leaving the outcome where `status`
can report it.

`spawn` is injected so tests run the wait inline.
"""
import logging
import threading

from tcm.domain.ports import TokenProvider

log = logging.getLogger(__name__)


def _thread(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()


class IdentityService:
    """One Graph identity, and at most one sign-in in progress."""

    def __init__(self, auth: TokenProvider, spawn=_thread):
        self._auth = auth
        self._spawn = spawn
        self._lock = threading.Lock()
        self._login = {}
        self._reset()

    def _reset(self):
        with self._lock:
            self._login.clear()
            self._login.update({"state": "idle", "user_code": None,
                                "verification_uri": None, "error": None})

    def token(self) -> str:
        return self._auth.token()

    def status(self) -> dict:
        """Who is signed in, or how far a sign-in has got."""
        status = self._auth.status()
        with self._lock:
            pending = self._login["state"] == "pending"
            snapshot = dict(self._login)

        if status["state"] == "signed_in":
            return status
        if pending:
            return {**status, "state": "pending",
                    "user_code": snapshot["user_code"],
                    "verification_uri": snapshot["verification_uri"]}
        if snapshot["error"]:
            return {**status, "error": snapshot["error"]}
        return status

    def begin_login(self):
        """Start a device-code sign-in. Returns `(body, http_status)`."""
        flow = self._auth.begin_device_login()

        with self._lock:
            self._login.update({"state": "pending", "error": None,
                                "user_code": flow.get("user_code"),
                                "verification_uri": flow.get("verification_uri")})

        self._spawn(self._await_login, flow)

        return {
            "user_code": flow.get("user_code"),
            "verification_uri": flow.get("verification_uri"),
            "expires_in": flow.get("expires_in"),
        }, 200

    def sign_out(self) -> dict:
        self._auth.sign_out()
        self._reset()
        return self._auth.status()

    def _await_login(self, flow):
        """Wait out the flow, leaving the outcome where `status` can see it."""
        try:
            self._auth.complete_device_login(flow)
        except Exception as e:
            log.warning("Device login did not complete: %s", e)
            with self._lock:
                self._login.update({"state": "failed", "error": str(e)})
            return
        self._reset()
