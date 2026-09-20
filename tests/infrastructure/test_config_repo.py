"""Tests for the atomic config file write and cleanup on failure."""
import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from tcm.infrastructure.config_repo import JsonFileConfigRepository


def test_cleanup_on_write_failure(tmp_path):
    """The temp file is cleaned up if write fails, and the target is unchanged.

    The except BaseException clause is the only thing that prevents a leftover
    temp file when the write fails. This test would pass if the cleanup were
    removed, but it verifies that cleanup happens.
    """
    repo = JsonFileConfigRepository()

    # Create an initial file with known content
    target = tmp_path / "config.json"
    original_content = '{"original": "content"}\n'
    target.write_text(original_content, encoding="utf-8")

    # Patch os.fdopen to make the write fail after opening
    original_fdopen = os.fdopen

    def failing_fdopen(fd, mode, encoding=None):
        """Wrapper that makes write() raise an exception."""
        original_file = original_fdopen(fd, mode, encoding=encoding)
        original_write = original_file.write

        def failing_write(text):
            # Fail partway through
            original_write(text[:5])
            raise IOError("Simulated write failure")

        original_file.write = failing_write
        return original_file

    # Attempt to write new content; it should fail
    with patch("os.fdopen", side_effect=failing_fdopen):
        with pytest.raises(IOError, match="Simulated write failure"):
            repo.write_text(str(target), '{"new": "content"}\n')

    # Assert the target file is unchanged
    assert target.read_text(encoding="utf-8") == original_content

    # Assert no leftover temp file in the directory
    temp_files = list(tmp_path.glob("*.tmp"))
    assert len(temp_files) == 0, f"Leftover temp files found: {temp_files}"
