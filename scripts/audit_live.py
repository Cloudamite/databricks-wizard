#!/usr/bin/env python3
"""Audit the live account in one command: read it, then measure what was read.

    cd <ADR monorepo>
    uv run --project <skill>/scripts --locked --group audit <skill>/scripts/audit_live.py \\
        --databricks-profile NAME (--aws-profile NAME | --no-storage) \\
        [--set PATH] [--declaration PATH] [--snapshot PATH] [--report PATH]

It runs `snapshot.py` and then `audit.py`, and adds nothing to either: the
snapshot, the report, what is printed and the exit code are theirs. What the
files alone refuse — a defective declaration, a defective set, a label the set
does not record — is refused before the account is read, since the audit would
refuse it after the read anyway. A read that fails measures nothing. Where there
is no declaration, one is written for the team to fill in, and nothing is read
but the account's list of workspaces.

The files are where the published skill keeps them, relative to the directory it
is run from, unless named:

    --set          platform/adr-set.yaml
    --declaration  audit/live.yaml
    --snapshot     audit/snapshot.json
    --report       audit/audit.json

The profiles are never defaulted: a profile is who reads the account.

Exit codes, as the audit's:

    0  no deviation was found
    1  one or more were — a measurement, not a build verdict
    2  could not run, and nothing was measured
"""

import argparse
import os
import sys
from pathlib import Path

import audit
import live
import snapshot
from wizard import adr_set, profiles
from wizard.analysis import validated
from wizard.files import write
from wizard.naming import set_environments
from wizard.validity import CannotRun, Refused

CANNOT_RUN = 2

DEFAULTS = {
    "set_path": "platform/adr-set.yaml",
    "declaration": "audit/live.yaml",
    "snapshot": "audit/snapshot.json",
    "report": "audit/audit.json",
}


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="audit_live.py",
        description="Read the live account, then measure it against the ADR set.",
    )
    parser.add_argument("--set", dest="set_path", default=DEFAULTS["set_path"], metavar="PATH",
                        help=f"the ADR set to measure against (default {DEFAULTS['set_path']})")
    for name, what in (("declaration", "the live estate declaration"),
                       ("snapshot", "where the snapshot is written"),
                       ("report", "where the structured report is written")):
        parser.add_argument(f"--{name}", default=DEFAULTS[name], metavar="PATH",
                            help=f"{what} (default {DEFAULTS[name]})")
    profiles.add_arguments(parser, ("databricks",))
    storage = parser.add_mutually_exclusive_group()
    storage.add_argument("--aws-profile", metavar="NAME",
                         help="the AWS configuration profile to read the buckets through; a "
                              "profile, never a credential")
    storage.add_argument("--no-storage", action="store_true",
                         help="read no bucket: PRE-001 is then reported unevaluated")
    args = parser.parse_args(argv)

    if not os.path.lexists(args.declaration):
        return no_declaration(args)
    try:
        audit.checked(args.set_path, args.declaration)
    except audit.REFUSALS as exc:
        audit.refuse(exc)
        return CANNOT_RUN

    read = snapshot.main(["--declaration", args.declaration, "--out", args.snapshot,
                          *_given("--databricks-profile", args.databricks_profile),
                          *_given("--aws-profile", args.aws_profile),
                          *(["--no-storage"] if args.no_storage else [])])
    if read != 0:
        return read
    return audit.main(["--set", args.set_path, "--declaration", args.declaration,
                       "--snapshot", args.snapshot, "--report", args.report])


def no_declaration(args):
    """Exit 2, measuring nothing, with a declaration written at `args.declaration`
    for the team to fill in: the set's entries with their names empty, and the
    account's workspaces, or why they could not be listed, in a comment."""
    try:
        document = validated(adr_set, "adr-set", args.set_path)
    except audit.REFUSALS as exc:
        audit.refuse(exc)
        return CANNOT_RUN
    names, why = [], "no --databricks-profile was given to list them with"
    if args.databricks_profile is not None:
        try:
            names = [workspace["name"]
                     for workspace in live.workspaces(args.databricks_profile)["workspaces"]]
            why = "the account lists no workspace"
        except (CannotRun, Refused) as exc:
            why = str(exc)
    out = Path(args.declaration)
    out.parent.mkdir(parents=True, exist_ok=True)
    write(out, declaration_text(Path(args.set_path).resolve().parent.name,
                                names or None, why, topology_entries(document)))
    print(f"cannot run: no live estate declaration at {out}, so one was written there.\n"
          "Fill in the workspace names and run the audit again.", file=sys.stderr)
    return CANNOT_RUN


# DEC-001a's options under which every environment shares a workspace.
SHARED_TOPOLOGIES = ("unit", "single")


def topology_entries(document):
    """The environment of each workspace a declaration of the set needs, `None`
    for one that holds none: one per environment the set records, unless its
    DEC-001a shares a workspace between environments, or it records none. Only an
    adopted entry can have a shared option chosen: a declined one's is `declined`."""
    for adr in document.get("adrs") or ():
        if adr.get("corpus_entry") == "DEC-001a":
            chosen = [option.get("key") for option in adr.get("options") or ()
                      if option.get("status") == "chosen"]
            if chosen and chosen[0] in SHARED_TOPOLOGIES:
                return [None]
    return set_environments(document) or [None]


def declaration_text(name, workspaces, why, environments):
    """A declaration to fill in: the account's `workspaces` in a comment, or `why`
    there are none, and an entry with an empty name for each of `environments`.
    Text, since YAML's writer writes no comments; workspace names are only ever in
    comments."""
    if workspaces:
        listing = ["# The account's workspaces:", *(f"#   {each}" for each in workspaces)]
    else:
        listing = ["# The account's workspaces could not be listed:",
                   *(f"#   {line}" for line in why.splitlines())]
    lines = ["schema_version: 1", f"name: {name}", *listing, "workspaces:"]
    for environment in environments:
        if environment is None:
            lines.append("  - name:  # <fill here the name of a workspace of the estate>")
        else:
            lines += [f"  - name:  # <fill here the name of the workspace for {environment}>",
                      f"    environment: {environment}"]
    return "\n".join(lines) + "\n"


def _given(flag, value):
    return [flag, value] if value is not None else []


if __name__ == "__main__":
    raise SystemExit(main())
