"""The CaseLoader port, answered by the Excel reader."""
from tcm.infrastructure.excel import reader


class ExcelCaseLoader:
    """Reads test cases out of .xlsx workbooks."""

    def load_from_folder(self, folder_path):
        return reader.load_from_folder(folder_path)

    def load_from_files(self, file_paths):
        return reader.load_from_files(file_paths)

    def find_workbooks(self, folder_path):
        return reader.find_workbooks(folder_path)
