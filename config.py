import os

PORT = int(os.environ.get("PORT", 5000))
DEBUG = os.environ.get("DEBUG", "1") not in ("0", "false", "False", "")

# Result -> status taxonomy. Point at your own file to change the vocabulary
# without touching code; falls back to parser/result_status.json.
RESULT_STATUS_CONFIG = os.environ.get(
    "RESULT_STATUS_CONFIG",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "parser", "result_status.json"),
)

_HERE = os.path.dirname(os.path.abspath(__file__))

# Which column of the SharePoint report workbook holds which value. Same idea as
# RESULT_STATUS_CONFIG: point at your own file to match your report's shape.
REPORT_LAYOUT_CONFIG = os.environ.get(
    "REPORT_LAYOUT_CONFIG",
    os.path.join(_HERE, "report", "report_layout.json"),
)

# --- Microsoft Graph -------------------------------------------------------
# Publishing the report needs an Azure app registration with "Allow public
# client flows" enabled; see README.md. Without a client id the SharePoint
# endpoints refuse politely rather than failing deep inside MSAL.
GRAPH_CLIENT_ID = os.environ.get("GRAPH_CLIENT_ID", "")

# "organizations" signs in any work/school account; use your tenant id to
# restrict it to one directory.
GRAPH_TENANT_ID = os.environ.get("GRAPH_TENANT_ID", "organizations")

# Files.ReadWrite.All reaches workbooks on SharePoint sites, not just OneDrive.
# MSAL adds offline_access itself, so the refresh token arrives without asking.
GRAPH_SCOPES = ["Files.ReadWrite.All"]

# Refresh tokens live here between runs, so signing in is a once-in-a-while
# thing. Written 0600 — treat it like a password file.
GRAPH_TOKEN_CACHE = os.path.expanduser(
    os.environ.get("GRAPH_TOKEN_CACHE", "~/.test-management/graph_token_cache.json")
)
