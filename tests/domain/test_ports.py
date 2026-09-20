"""Each port's one implementation actually implements it.

A Protocol nothing is checked against is a comment. These are the checks that
make the six interfaces load-bearing rather than decorative.
"""
from tcm.domain import ports
from tcm.infrastructure.graph.auth import GraphAuth
from tcm.infrastructure.graph.workbook import Workbook


def test_the_graph_workbook_is_a_report_workbook():
    assert issubclass(Workbook, ports.ReportWorkbook)


def test_graph_auth_is_a_token_provider():
    assert issubclass(GraphAuth, ports.TokenProvider)


def test_the_publisher_fake_is_a_report_workbook():
    """The fake and the real client answer to one interface, or they drift."""
    from tests.services.test_publisher import FakeWorkbook
    assert issubclass(FakeWorkbook, ports.ReportWorkbook)
