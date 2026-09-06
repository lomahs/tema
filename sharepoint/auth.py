"""Signing in to Microsoft Graph with the device code flow.

The app is a public client: it holds no secret, and it acts as whoever signed
in, so writes to SharePoint carry that person's name and obey their permissions.
Signing in means reading a short code off the screen and typing it into
microsoft.com/devicelogin — no redirect URI, and nothing for this local Flask
app to serve.

The refresh token is cached on disk, so the code is only needed once in a while.
"""
import json
import logging
import os

import msal

log = logging.getLogger(__name__)

AUTHORITY = "https://login.microsoftonline.com"


class NotConfigured(Exception):
    """No Azure app registration was configured, so signing in is impossible."""


class NotSignedIn(Exception):
    """Nobody is signed in, or the cached sign-in has expired."""


class GraphAuth:
    """Holds the signed-in identity and hands out access tokens.

    Args:
        client_id: Application (client) id of the Azure app registration.
        tenant_id: Directory to sign in against; "organizations" allows any.
        scopes: Delegated permissions to ask for.
        cache_path: Where the token cache is kept between runs.
        app_factory: Builds the MSAL app around a cache. Injectable for tests.
    """

    def __init__(self, client_id: str, tenant_id: str, scopes: list[str],
                 cache_path: str, app_factory=None):
        self._client_id = client_id
        self._tenant_id = tenant_id
        self._scopes = list(scopes)
        self._cache_path = cache_path
        self._app_factory = app_factory or self._build_msal_app
        self._cache = msal.SerializableTokenCache()
        self._load_cache()
        self._app = None

    # --- state ------------------------------------------------------------

    @property
    def configured(self) -> bool:
        return bool(self._client_id)

    def status(self) -> dict:
        """Who is signed in, if anyone. Safe to call before anything is set up."""
        if not self.configured:
            return {"state": "not_configured", "account": None}

        account = self._account()
        if account is None or self._silent_token(account) is None:
            return {"state": "signed_out", "account": None}
        return {"state": "signed_in", "account": account.get("username")}

    def token(self) -> str:
        """A bearer token for Graph, refreshed silently when it can be.

        Raises:
            NotConfigured: No client id was configured.
            NotSignedIn: Nobody has signed in, or the cached sign-in has expired.
        """
        if not self.configured:
            raise NotConfigured(
                "No Azure app registration configured. Set GRAPH_CLIENT_ID "
                "(see README.md) before publishing to SharePoint."
            )

        account = self._account()
        result = self._silent_token(account) if account else None
        if not result:
            raise NotSignedIn("Not signed in to SharePoint. Sign in and try again.")
        return result["access_token"]

    # --- signing in and out -----------------------------------------------

    def begin_device_login(self) -> dict:
        """Ask Microsoft for a device code. Returns it for the UI to display."""
        if not self.configured:
            raise NotConfigured(
                "No Azure app registration configured. Set GRAPH_CLIENT_ID "
                "(see README.md) before signing in."
            )

        flow = self._msal().initiate_device_flow(scopes=self._scopes)
        if "user_code" not in flow:
            raise RuntimeError(_describe(flow, "Microsoft would not start the sign-in"))
        return flow

    def complete_device_login(self, flow: dict) -> dict:
        """Wait for the user to finish typing the code in. Blocks until they do.

        Call this off the request thread: it polls until the user finishes or
        the code expires, which can be minutes.
        """
        result = self._msal().acquire_token_by_device_flow(flow) or {}
        self._save_cache()
        if "access_token" not in result:
            raise RuntimeError(_describe(result, "Sign-in did not complete"))
        return result

    def sign_out(self):
        """Forget every cached account, so the next publish asks to sign in again."""
        if not self.configured:
            return
        app = self._msal()
        for account in app.get_accounts():
            app.remove_account(account)
        self._save_cache()

    # --- internals --------------------------------------------------------

    def _msal(self):
        if self._app is None:
            self._app = self._app_factory(cache=self._cache)
        return self._app

    def _build_msal_app(self, cache):
        return msal.PublicClientApplication(
            self._client_id,
            authority=f"{AUTHORITY}/{self._tenant_id}",
            token_cache=cache,
        )

    def _account(self):
        accounts = self._msal().get_accounts()
        return accounts[0] if accounts else None

    def _silent_token(self, account):
        result = self._msal().acquire_token_silent(self._scopes, account=account)
        self._save_cache()
        return result

    def _load_cache(self):
        """Read the cache, treating an unreadable one as simply "not signed in"."""
        try:
            with open(self._cache_path, encoding="utf-8") as f:
                self._cache.deserialize(f.read())
        except FileNotFoundError:
            pass
        except Exception as e:
            log.warning("Ignoring unreadable token cache '%s': %s", self._cache_path, e)

    def _save_cache(self):
        """Persist the cache 0600 — it holds a refresh token."""
        try:
            directory = os.path.dirname(self._cache_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            # Create it private before anything is written, rather than
            # narrowing the permissions after the secret is already on disk.
            fd = os.open(self._cache_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(self._cache.serialize())
            os.chmod(self._cache_path, 0o600)
        except Exception as e:
            log.warning("Could not save the token cache '%s': %s", self._cache_path, e)


def _describe(payload: dict, prefix: str) -> str:
    detail = (payload or {}).get("error_description") or (payload or {}).get("error")
    return f"{prefix}: {detail or json.dumps(payload)}"
