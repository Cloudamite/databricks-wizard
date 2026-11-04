#!/usr/bin/env python3
"""Build the live estate declaration from what the team picks.

    uv run --project <skill>/scripts --locked <skill>/scripts/live.py profiles
    uv run --project <skill>/scripts --locked --group audit <skill>/scripts/live.py \\
        workspaces --databricks-profile NAME
    uv run --project <skill>/scripts --locked <skill>/scripts/live.py declare \\
        --set platform/adr-set.yaml --out audit/live.yaml \\
        --workspace NAME[=ENVIRONMENT] ... [--replace]

Three steps, each printing what the skill shows and asking nothing:

- `profiles` lists the Databricks profiles that reach an account console, and
  the AWS profiles, from the configuration files alone. No network.
- `workspaces` lists the workspaces of the account the named profile reaches,
  with one read call, through the reader's own account client.
- `declare` writes the declaration from the workspaces picked, each labelled
  with an environment the set records, or with none. No network.

Exit codes:

    0  printed, or written
    2  could not run — bad usage, a profile not named, a listing that failed, a
       defective set, a label the set does not record, what cannot be a
       declaration, a declaration already there without --replace, or a missing
       dependency

A failed listing prints nothing on stdout, so it cannot be shown as an account
with no workspaces.
"""

import argparse
import json
import os
import sys
from pathlib import Path

CANNOT_RUN = 2

try:
    import yaml
except ImportError:
    from wizard.environment import missing_yaml
    missing_yaml("read the ADR set and write the live estate declaration", CANNOT_RUN)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from wizard import adr_set, live_declaration, profiles  # noqa: E402
from wizard.analysis import Defective, validated  # noqa: E402
from wizard.files import write  # noqa: E402
from wizard.naming import ENVIRONMENTS, listed  # noqa: E402
from wizard.report import render_human  # noqa: E402
from wizard.validity import CannotRun, Refused  # noqa: E402

def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="live.py",
        description="Build the live estate declaration from what the team picks.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("profiles", help="list the profiles the team can pick from")
    listing = commands.add_parser("workspaces", help="list the account's workspaces")
    profiles.add_arguments(listing, ("databricks",))
    declaring = commands.add_parser("declare", help="write the declaration")
    declaring.add_argument("--set", required=True, dest="set_path", metavar="PATH",
                           help="the ADR set the estate is measured against")
    declaring.add_argument("--out", required=True, metavar="PATH",
                           help="where the declaration is written")
    declaring.add_argument("--workspace", action="append", default=[],
                           metavar="NAME[=ENVIRONMENT]",
                           help="a workspace of the estate, and its environment if it holds one")
    declaring.add_argument("--replace", action="store_true",
                           help="replace a declaration already at --out")
    args = parser.parse_args(argv)

    try:
        if args.command == "profiles":
            printed = listed_profiles(os.environ, Path.home())
        elif args.command == "workspaces":
            printed = workspaces(args.databricks_profile)
        else:
            out = declare(args.set_path, args.out, args.workspace, args.replace)
            print(f"live estate declaration written to {out}")
            return 0
    except Defective as exc:
        print("cannot run: the ADR set is defective", file=sys.stderr)
        print(render_human(exc.artefact, exc.failures), file=sys.stderr)
        return CANNOT_RUN
    except (CannotRun, Refused) as exc:
        print(f"cannot run: {exc}", file=sys.stderr)
        return CANNOT_RUN
    print(json.dumps(printed, indent=2, ensure_ascii=False))
    return 0


# --- profiles -------------------------------------------------------------------------


def listed_profiles(environ, home):
    """The account-console Databricks profiles and the AWS profiles, by name."""
    aws_path, _ = profiles.location(environ, home, profiles.AWS)
    databricks_path, _ = profiles.location(environ, home, profiles.DATABRICKS)
    return {
        "aws": profiles.aws_profiles(profiles.sections(aws_path)),
        "databricks": [name for name, reach in
                       profiles.databricks_profiles(profiles.sections(databricks_path))
                       if reach == "account console"],
    }


# --- workspaces -----------------------------------------------------------------------


def workspaces(profile):
    """The account the profile reaches, and its workspaces, sorted by name."""
    # Before the SDK is imported: it reads `os.environ` in this process.
    profiles.act_as(os.environ, databricks=profile)
    profiles.require(os.environ, Path.home(), ("databricks",))
    import snapshot

    through = f"read through profile {profile!r}"
    account = snapshot.account_client(profile, through)
    try:
        listed_workspaces = list(account.workspaces.list())
    except Exception as exc:
        raise CannotRun(f"the account's workspaces could not be listed: "
                        f"{snapshot.reason(exc)}; {through}") from None
    return {
        "account": {"host": account.config.host, "account_id": account.config.account_id},
        "workspaces": sorted(({"name": workspace.workspace_name,
                               "region": workspace.aws_region or workspace.location,
                               "status": _value(workspace.workspace_status)}
                              for workspace in listed_workspaces),
                             key=lambda workspace: workspace["name"]),
    }


def _value(field):
    return getattr(field, "value", field)


# --- declare --------------------------------------------------------------------------


def declare(set_path, out, given, replace):
    """Write the declaration of the workspaces `given`, and return where."""
    document = validated(adr_set, "adr-set", set_path)
    recorded = environments(document)
    picked = _picked(given)
    unrecorded = sorted({label for _, label in picked if label and label not in recorded})
    if unrecorded:
        records = (f"it records {listed(recorded)}" if recorded
                   else "it records no environment")
        raise CannotRun(f"the set does not record {listed(unrecorded)}; {records}")

    declaration = {
        "schema_version": 1,
        "name": Path(set_path).resolve().parent.name,
        "workspaces": [{"name": name, **({"environment": label} if label else {})}
                       for name, label in picked],
    }
    failures = live_declaration.check(declaration, Path(out).name)
    if failures:
        raise CannotRun("the declaration would be defective\n"
                        + render_human("live-declaration", failures))

    out = Path(out)
    if os.path.lexists(out) and not replace:
        raise CannotRun(f"{out} already exists; give --replace to replace it")
    out.parent.mkdir(parents=True, exist_ok=True)
    write(out, yaml.safe_dump(declaration, sort_keys=False, allow_unicode=True))
    return out


def environments(document):
    """The environments the set records, in the order first recorded. Only an adopted
    entry carries parameters: they are asked when an option is chosen."""
    found = []
    for entry in document.get("adrs") or ():
        for environment in (entry.get("parameters") or {}).get(ENVIRONMENTS) or ():
            if environment not in found:
                found.append(environment)
    return found


def _picked(given):
    """`(name, label or None)` for each `--workspace`. A name that is missing, or no
    `--workspace` at all, is the declaration's own validity to refuse; an empty label
    is refused here, since it would otherwise be written as no label."""
    picked, unlabelled = [], []
    for item in given:
        name, separator, label = item.partition("=")
        if separator and not label:
            unlabelled.append(item)
        picked.append((name, label if separator else None))
    if unlabelled:
        raise CannotRun("a --workspace with '=' needs an environment after it: "
                        f"{', '.join(repr(item) for item in unlabelled)}")
    return picked


if __name__ == "__main__":
    raise SystemExit(main())
