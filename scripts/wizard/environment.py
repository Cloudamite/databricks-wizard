"""What an entry point says when it runs outside the skill's environment.

The skill's dependencies live in an environment uv builds from the lockfile
beside the scripts. A script run by an
interpreter without them exits with the uv command that runs it inside that
environment — never a pip command, since installing into the interpreter that
lacked the dependency is what the environment exists to avoid. Standard library
only: it runs precisely when a dependency is missing.
"""

import sys
from pathlib import Path


def missing_yaml(purpose, code):
    """Report that PyYAML, needed to *purpose*, is missing, and exit *code*."""
    script = Path(sys.argv[0]).resolve()
    print(
        f"PyYAML is required to {purpose} and is not available to this interpreter.\n"
        "uv installs it into the skill's own environment; run the script through uv:\n"
        f"  uv run --project {script.parent} --locked {script} …",
        file=sys.stderr,
    )
    raise SystemExit(code)


def missing_sdk(code, sdk="The Databricks SDK", purpose="read the account"):
    """Report that an SDK the account reader alone imports is missing.

    The Databricks SDK and the AWS SDK are both in the `audit` dependency group,
    which only the reader's invocation asks for, so the command that runs it
    names the group.
    """
    script = Path(sys.argv[0]).resolve()
    print(
        f"{sdk} is required to {purpose} and is not available to this interpreter.\n"
        "It is in the skill's `audit` dependency group; run the reader through uv "
        "with that group:\n"
        f"  uv run --project {script.parent} --locked --group audit {script} …",
        file=sys.stderr,
    )
    raise SystemExit(code)
