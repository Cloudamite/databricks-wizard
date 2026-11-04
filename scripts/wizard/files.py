"""Writing a file whole, or not at all."""

import os
import tempfile
from pathlib import Path

from wizard.validity import CannotRun


def write(path, text):
    """Replace `path` with `text` whole, or leave it as it was.

    The new file is staged beside the old one, on the same filesystem, and
    renamed over it; a rename is atomic only within one filesystem.
    """
    path = Path(path)
    descriptor, staging = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.",
                                           suffix=".staging")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as staged:
            staged.write(text)
        # `mkstemp` creates the file private to its owner; what is written here is
        # an ordinary file of the repository, and keeps the mode it had.
        os.chmod(staging, path.stat().st_mode if path.exists() else 0o644)
        os.replace(staging, path)
    except OSError as exc:
        Path(staging).unlink(missing_ok=True)
        raise CannotRun(f"{path.name} could not be written, and is as it was: {exc}") from None
