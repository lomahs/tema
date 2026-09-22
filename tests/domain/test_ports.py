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


def test_the_excel_loader_is_a_case_loader():
    from tcm.infrastructure.excel.loader import ExcelCaseLoader
    assert issubclass(ExcelCaseLoader, ports.CaseLoader)


def test_the_memory_store_is_a_case_store():
    from tcm.infrastructure.store.memory import InMemoryCaseStore
    assert issubclass(InMemoryCaseStore, ports.CaseStore)


def test_the_json_repository_is_a_config_repository():
    from tcm.infrastructure.config_repo import JsonFileConfigRepository
    assert issubclass(JsonFileConfigRepository, ports.ConfigRepository)


def test_the_native_dialog_is_a_file_picker():
    from tcm.infrastructure.dialog import NativeDialog
    assert issubclass(NativeDialog, ports.FilePicker)


def test_the_json_plan_repository_is_a_plan_repository():
    from tcm.infrastructure.plan.json_store import JsonPlanRepository
    assert issubclass(JsonPlanRepository, ports.PlanRepository)
