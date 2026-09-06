"""Publish a report to SharePoint from the command line.

Runs the same code path as `POST /api/report/publish`, so it verifies the Graph
side end to end without opening the UI.

Usage:
    export GRAPH_CLIENT_ID=... GRAPH_TENANT_ID=...
    python -m tools.publish_report --folder samples/generated --url "<SharePoint link>"
    python -m tools.publish_report --folder ... --url ... --run-date 2026-09-01
"""
import argparse
import logging
import sys

import config
from parser.excel_reader import load_from_folder, load_from_files
from report.publisher import SheetMissing, publish_to_url
from sharepoint.auth import GraphAuth, NotConfigured, NotSignedIn
from sharepoint.client import GraphClient, GraphError

log = logging.getLogger(__name__)


def sign_in(auth: GraphAuth):
    """Make sure someone is signed in, prompting on the terminal if not."""
    status = auth.status()
    if status["state"] == "signed_in":
        log.info("Signed in as %s", status["account"])
        return

    flow = auth.begin_device_login()
    # MSAL's own `message` already spells out the URL and the code.
    log.info("%s", flow.get("message")
             or f"Open {flow['verification_uri']} and enter {flow['user_code']}")
    auth.complete_device_login(flow)
    log.info("Signed in as %s", auth.status()["account"])


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--folder", help="Folder of .xlsx test case files to read")
    source.add_argument("--files", nargs="+", help="Explicit .xlsx paths to read")
    p.add_argument("--url", required=True, help="SharePoint link to the report file")
    p.add_argument("--run-date", help='Day to publish as, "YYYY-MM-DD" (default: today)')
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    cases, file_results = (load_from_folder(args.folder) if args.folder
                           else load_from_files(args.files))
    for result in file_results:
        if result["status"] != "OK":
            log.warning("  %s: %s", result["file"], result.get("error"))
    log.info("Read %d test case(s) from %d file(s)", len(cases), len(file_results))

    if not cases:
        p.error("no test cases were read — publishing would only clear the day's rows")

    auth = GraphAuth(
        client_id=config.GRAPH_CLIENT_ID,
        tenant_id=config.GRAPH_TENANT_ID,
        scopes=config.GRAPH_SCOPES,
        cache_path=config.GRAPH_TOKEN_CACHE,
    )

    try:
        sign_in(auth)
        result = publish_to_url(cases, GraphClient(auth.token), args.url,
                                run_date=args.run_date)
    except (NotConfigured, NotSignedIn, SheetMissing, ValueError) as e:
        log.error("%s", e)
        return 1
    except GraphError as e:
        log.error("%s", e)
        log.error("Nothing may have been written, or only some sheets. Publishing "
                  "again replaces the same day's rows rather than duplicating them.")
        return 1

    log.info("Published to %s for %s", result["file"], result["run_date"])
    for sheet in result["sheets"]:
        log.info("  %-12s appended %-4d replaced %d",
                 sheet["sheet"], sheet["appended"], sheet["deleted"])
    if result["web_url"]:
        log.info("%s", result["web_url"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
