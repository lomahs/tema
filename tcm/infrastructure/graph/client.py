"""A small HTTP client for Microsoft Graph.

Deliberately not the official SDK: the app makes a handful of calls against one
workbook, and a thin layer keeps the transport injectable, which is what lets
every test run offline.
"""
import logging
import time

import requests

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

#: Statuses worth trying again. 429 is throttling; 503/504 are Graph being busy.
RETRY_STATUSES = (429, 503, 504)
MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 5
TIMEOUT = 60


class GraphError(Exception):
    """A non-success reply from Graph, with whatever detail it gave."""

    def __init__(self, status: int, code: str = "", message: str = ""):
        self.status = status
        self.code = code
        self.message = message
        detail = message or code or "no detail given"
        super().__init__(f"Graph returned {status}: {detail}")


class GraphClient:
    """Sends authenticated requests to Graph, retrying the ones worth retrying.

    Args:
        token_provider: Called for each request; returns a bearer token. Passing
            a callable rather than a token means a long-lived client picks up a
            silently refreshed one.
        transport: Anything with `requests`' `.request(method, url, **kwargs)`.
        sleep: Injectable so tests do not actually wait out a retry.
    """

    def __init__(self, token_provider, transport=None, sleep=None):
        self._token = token_provider
        self._transport = transport or requests.Session()
        self._sleep = sleep or time.sleep

    def request(self, method: str, path: str, headers=None, **kwargs):
        """Send one call, retrying throttles. Returns the JSON body, or None for a 204."""
        url = path if path.startswith("http") else f"{GRAPH_BASE}{path}"

        for attempt in range(MAX_RETRIES + 1):
            merged = {"Authorization": f"Bearer {self._token()}", **(headers or {})}
            response = self._transport.request(
                method, url, headers=merged, timeout=TIMEOUT, **kwargs
            )

            if response.status_code in RETRY_STATUSES and attempt < MAX_RETRIES:
                delay = _retry_after(response)
                log.warning("Graph %s on %s %s — retrying in %ss",
                            response.status_code, method, path, delay)
                self._sleep(delay)
                continue

            if response.status_code >= 400:
                raise _error_from(response)

            return _body_of(response)

        raise AssertionError("unreachable: the loop either returns or raises")

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def patch(self, path, **kwargs):
        return self.request("PATCH", path, **kwargs)

    def delete(self, path, **kwargs):
        return self.request("DELETE", path, **kwargs)


def _retry_after(response) -> int:
    try:
        return int(response.headers.get("Retry-After", DEFAULT_RETRY_DELAY))
    except (TypeError, ValueError):
        return DEFAULT_RETRY_DELAY


def _error_from(response) -> GraphError:
    try:
        error = (response.json() or {}).get("error") or {}
    except Exception:
        error = {}
    return GraphError(response.status_code, error.get("code", ""), error.get("message", ""))


def _body_of(response):
    if response.status_code == 204:
        return None
    try:
        return response.json()
    except Exception:
        return None
