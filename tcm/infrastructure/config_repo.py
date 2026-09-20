"""Reading and writing the editable config files on disk.

The write is atomic because a half-written result_status.json does not make the
taxonomy wrong -- it stops the app booting, since the vocabularies load at
import. So the text goes to a temp file beside the target and os.replace swaps
it in, which is one filesystem operation. The temp file must be in the same
directory because os.replace is only atomic within a filesystem (a cross-device
link will raise OSError).
"""
import os
import tempfile


class JsonFileConfigRepository:
    """Config files as JSON on the local filesystem."""

    def read_text(self, path: str) -> str:
        with open(path, encoding="utf-8") as f:
            return f.read()

    def write_text(self, path: str, text: str) -> None:
        directory = os.path.dirname(os.path.abspath(path))
        fd, temp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(temp, path)
        except BaseException:
            if os.path.exists(temp):
                os.unlink(temp)
            raise
