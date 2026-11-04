#!/usr/bin/env python3
"""Post-install: have uv build the skill's locked environment.

The skill's dependencies are locked in `uv.lock` beside this file and live in an
environment uv builds there, never in the team's interpreter.
This hook builds it at install time, so a
missing uv or an unresolvable lock fails the install rather than the team's first
workflow. Standard library only: it runs under the installer's interpreter,
before any environment exists.

A failure here fails the install. The installer builds its closing summary
from this script's exit code, so exiting 0 after a failure makes it print
"Installation complete!" over an install that cannot run.
"""

import shutil
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
UV_INSTALL = "https://docs.astral.sh/uv/getting-started/installation/"


def main():
    if shutil.which("uv") is None:
        print(
            "databricks-wizard runs in an environment uv builds, and uv is not on PATH.\n"
            f"Install uv ({UV_INSTALL}), then install the skill again.",
            file=sys.stderr,
        )
        return 1

    command = ["uv", "sync", "--project", str(PROJECT), "--locked"]
    if subprocess.run(command).returncode != 0:
        print(
            "databricks-wizard's environment could not be built. Run it by hand to see why:\n"
            f"  {' '.join(command)}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
