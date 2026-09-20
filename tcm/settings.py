import os

PORT = int(os.environ.get("PORT", 5000))
DEBUG = os.environ.get("DEBUG", "1") not in ("0", "false", "False", "")

# The repository root: this file lives at <root>/tcm/settings.py.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_DIR = os.path.join(_ROOT, "config")

# Result -> status taxonomy. Point at your own file to change the vocabulary
# without touching code; falls back to config/result_status.json.
RESULT_STATUS_CONFIG = os.environ.get(
    "RESULT_STATUS_CONFIG",
    os.path.join(_CONFIG_DIR, "result_status.json"),
)

# Which Scope values belong to which Summary table. Same idea as
# RESULT_STATUS_CONFIG: the vocabulary is data, so renaming a scope or adding a
# third table is a config edit, not a code change.
SCOPE_GROUPS_CONFIG = os.environ.get(
    "SCOPE_GROUPS_CONFIG",
    os.path.join(_CONFIG_DIR, "scope_groups.json"),
)

# Which device names belong to which device family, for Summary's "By device
# type" rows: "iPhone Min size" and "iPhone Max size" are two device blocks in
# the workbook but one handset to anyone reading the totals. Same idea as
# SCOPE_GROUPS_CONFIG — testing a new model is a config edit, not a code change.
DEVICE_GROUPS_CONFIG = os.environ.get(
    "DEVICE_GROUPS_CONFIG",
    os.path.join(_CONFIG_DIR, "device_groups.json"),
)

# Which column of the SharePoint report workbook holds which value. Same idea as
# RESULT_STATUS_CONFIG: point at your own file to match your report's shape.
REPORT_LAYOUT_CONFIG = os.environ.get(
    "REPORT_LAYOUT_CONFIG",
    os.path.join(_CONFIG_DIR, "report_layout.json"),
)

# The labels TOOL_DATA detection looks for when reading a sheet's layout. Point
# at your own file if your test case sheets are headed differently ("Status"
# rather than "結果", and so on).
SHEET_LABELS_CONFIG = os.environ.get(
    "SHEET_LABELS_CONFIG",
    os.path.join(_CONFIG_DIR, "sheet_labels.json"),
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
