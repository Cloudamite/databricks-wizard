"""The live estate declaration's validity table, implemented.

The one file a team writes by hand for an audit: the workspaces of the account
that make up the estate, by the names the account gives them, each labelled
with the environment it holds where it holds one.

It names workspaces and nothing else about them. The account is the one the
SDK's configuration names, so a key this table does not carry — a host, an id,
a token — is defective rather than ignored: a file that carried one and was
accepted would say the reader used it.

Nothing here reads the ADR set. Which environments exist is the set's to
record, and a label no set records is not defective here, as for the estate
declaration.
"""

from pathlib import Path

from wizard.report import render_human
from wizard.validity import LIVE_RULES, CannotRun, Failure, is_stated, read_mapping

TOP_LEVEL_KEYS = ("schema_version", "name", "workspaces")
WORKSPACE_KEYS = ("name", "environment", "note")

# Where a top-level key sits, when a failure names it.
TOP_LEVEL = "top level"


def validate(path):
    return check(read_mapping(path), Path(path).name)


def check(document, file="live.yaml"):
    """The failures of a declaration held in memory, named as if read from `file`:
    what `live.py declare` checks before it writes one."""
    failures = []

    def failure(key, entries=()):
        return Failure(LIVE_RULES[key], list(entries), file)

    version = document.get("schema_version")
    # A boolean is an integer in Python, and `true` is not version 1.
    if version != 1 or isinstance(version, bool):
        failures.append(failure("schema_version"))

    if not is_stated(document.get("name")):
        failures.append(failure("name"))

    failures += [failure("keys", [TOP_LEVEL, key])
                 for key in _unknown(document, TOP_LEVEL_KEYS)]

    workspaces = document.get("workspaces")
    if not isinstance(workspaces, list) or not workspaces:
        failures.append(failure("workspaces"))
        return failures

    seen, duplicated = set(), []
    for index, workspace in enumerate(workspaces):
        if not isinstance(workspace, dict) or not is_stated(workspace.get("name")):
            # A workspace with no name has nothing to be named by but its place.
            failures.append(failure("workspace_name", [f"workspaces[{index}]"]))
            if not isinstance(workspace, dict):
                continue
            where = f"workspaces[{index}]"
        else:
            where = workspace["name"]
            if where in seen and where not in duplicated:
                duplicated.append(where)
            seen.add(where)

        if "environment" in workspace and not is_stated(workspace["environment"]):
            failures.append(failure("workspace_environment", [where]))
        failures += [failure("keys", [where, key])
                     for key in _unknown(workspace, WORKSPACE_KEYS)]

    if duplicated:
        # One failure for the set, naming each shared name once: a duplicate is
        # a property of the list, not of either workspace on its own.
        failures.append(failure("workspace_names_unique", duplicated))

    return failures


def _unknown(mapping, allowed):
    """The keys `mapping` carries that `allowed` does not, sorted."""
    return sorted(str(key) for key in mapping if key not in allowed)


def read(path):
    """The declaration, validated, or `CannotRun` naming every rule it broke.

    For the commands that take one: they halt on a
    defective declaration before they read anything else. A file that is
    another artefact fails the table too — it carries no `workspaces`, or
    carries keys the table does not name.
    """
    failures = validate(path)
    if failures:
        raise CannotRun("the live estate declaration is defective\n"
                        + render_human("live-declaration", failures))
    return read_mapping(path)
