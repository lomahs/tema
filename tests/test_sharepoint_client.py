"""The Graph HTTP layer, driven by a fake transport. Nothing here touches the network."""
import pytest

from sharepoint.client import GraphClient, GraphError
from sharepoint.links import share_url_to_item


class Reply:
    """Just enough of a `requests.Response` for the client to work with."""

    def __init__(self, status_code=200, json_body=None, headers=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._json = json_body

    def json(self):
        if self._json is None:
            raise ValueError("no json body")
        return self._json


class FakeTransport:
    """Hands back queued replies and records what was asked of it."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.replies.pop(0)


def client(*replies, **kwargs):
    transport = FakeTransport(*replies)
    return GraphClient(lambda: "TOKEN", transport=transport, sleep=lambda _s: None,
                       **kwargs), transport


def test_a_request_is_sent_to_graph_with_the_bearer_token():
    graph, transport = client(Reply(200, {"value": []}))

    graph.get("/me/drive")

    call = transport.calls[0]
    assert call["url"] == "https://graph.microsoft.com/v1.0/me/drive"
    assert call["headers"]["Authorization"] == "Bearer TOKEN"


def test_the_json_body_of_a_successful_call_is_returned():
    graph, _ = client(Reply(200, {"id": "abc"}))

    assert graph.get("/me/drive")["id"] == "abc"


def test_a_204_answers_none_rather_than_failing_to_parse_an_empty_body():
    """Graph replies 204 to range/delete and closeSession."""
    graph, _ = client(Reply(204))

    assert graph.post("/whatever") is None


def test_a_throttled_call_is_retried_after_the_delay_graph_asks_for():
    graph, transport = client(
        Reply(429, headers={"Retry-After": "2"}),
        Reply(200, {"id": "abc"}),
    )

    assert graph.get("/me/drive")["id"] == "abc"
    assert len(transport.calls) == 2


def test_the_retry_delay_honours_the_retry_after_header():
    slept = []
    transport = FakeTransport(Reply(503, headers={"Retry-After": "7"}), Reply(200, {}))
    graph = GraphClient(lambda: "TOKEN", transport=transport, sleep=slept.append)

    graph.get("/me/drive")

    assert slept == [7]


def test_retrying_gives_up_and_surfaces_the_error():
    graph, transport = client(*[Reply(429, headers={"Retry-After": "0"})] * 4)

    with pytest.raises(GraphError) as excinfo:
        graph.get("/me/drive")

    assert excinfo.value.status == 429
    assert len(transport.calls) == 4       # the first try plus three retries


def test_a_client_error_is_not_retried():
    graph, transport = client(Reply(400, {"error": {"code": "invalidRequest",
                                                    "message": "Bad range"}}))

    with pytest.raises(GraphError):
        graph.get("/me/drive")

    assert len(transport.calls) == 1


def test_a_graph_error_carries_the_code_and_message_graph_gave():
    graph, _ = client(Reply(404, {"error": {"code": "itemNotFound",
                                            "message": "The sheet was not found"}}))

    with pytest.raises(GraphError) as excinfo:
        graph.get("/drives/x/items/y/workbook/worksheets/Nope")

    error = excinfo.value
    assert error.status == 404
    assert error.code == "itemNotFound"
    assert "The sheet was not found" in str(error)


def test_an_error_without_a_json_body_still_raises_something_readable():
    graph, _ = client(Reply(500))

    with pytest.raises(GraphError, match="500"):
        graph.get("/me/drive")


def test_extra_headers_travel_alongside_the_bearer_token():
    graph, transport = client(Reply(200, {}))

    graph.get("/me/drive", headers={"Workbook-Session-Id": "S1"})

    headers = transport.calls[0]["headers"]
    assert headers["Workbook-Session-Id"] == "S1"
    assert headers["Authorization"] == "Bearer TOKEN"


# --- resolving a pasted SharePoint link ------------------------------------

ITEM = {
    "id": "01ITEM",
    "name": "Report.xlsx",
    "webUrl": "https://contoso.sharepoint.com/sites/qa/Shared%20Documents/Report.xlsx",
    "parentReference": {"driveId": "b!DRIVE"},
}


def test_a_shared_url_is_resolved_to_the_drive_item_behind_it():
    graph, transport = client(Reply(200, ITEM))

    ref = share_url_to_item(graph, "https://contoso.sharepoint.com/:x:/r/sites/qa/doc.xlsx")

    assert (ref.drive_id, ref.item_id, ref.name) == ("b!DRIVE", "01ITEM", "Report.xlsx")
    assert "/shares/u!" in transport.calls[0]["url"]


def test_the_url_is_encoded_the_unpadded_base64url_way_graph_requires():
    graph, transport = client(Reply(200, ITEM))

    share_url_to_item(graph, "https://contoso.sharepoint.com/a?b=c")

    token = transport.calls[0]["url"].split("/shares/")[1].split("/")[0]
    assert token.startswith("u!")
    assert "=" not in token and "+" not in token and "/" not in token


def test_a_url_that_is_not_a_link_at_all_is_refused_before_any_call_is_made():
    graph, transport = client()

    with pytest.raises(ValueError, match="https"):
        share_url_to_item(graph, "C:\\Reports\\Report.xlsx")

    assert transport.calls == []


def test_an_item_without_a_drive_is_reported_as_such():
    graph, _ = client(Reply(200, {"id": "01ITEM", "name": "R.xlsx", "parentReference": {}}))

    with pytest.raises(ValueError, match="drive"):
        share_url_to_item(graph, "https://contoso.sharepoint.com/a")
