#!/usr/bin/env python3
"""Measure the live account against the ADR set.

    uv run --project <skill>/scripts --locked <skill>/scripts/audit.py \
        --set docs/decisions/adr-set.yaml --declaration live.yaml \
        --snapshot snapshot.json --report audit.json

It reads files only: the snapshot `snapshot.py` wrote, never the account. It
gates the set as the analyzer does, evaluates every rule against the account's
own objects with the audit's evaluators, and reports in the
analyzer's vocabulary — PASS, FAIL and UNEVALUATED, the four causes, a
four-component deviation identity. Terraform plays no part.

Exit codes, as the analyzer's:

    0  no deviation was found
    1  one or more were — a measurement, not a build verdict
    2  could not run — bad usage, a defective or absent set, a defective
       declaration, a snapshot that cannot be read or does not describe the
       declaration, or a missing dependency

The structured report is written to `--report` and a rendering of it printed.
It makes no network request and reads no clock and no environment variable.
"""

import argparse
import json
import sys
from pathlib import Path

CANNOT_RUN = 2

try:
    import yaml  # noqa: F401
except ImportError:
    from wizard.environment import missing_yaml
    missing_yaml("read the ADR set and the live estate declaration", CANNOT_RUN)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from wizard import adr_set, live, live_declaration, rules  # noqa: E402
from wizard.analysis import ARTEFACTS, Defective, validated  # noqa: E402
from wizard.files import write  # noqa: E402
from wizard.live.estate import Estate, mismatches, read_snapshot  # noqa: E402
from wizard.live.evaluation import evaluate  # noqa: E402
from wizard.divergence import LIVE  # noqa: E402
from wizard.live.report import report  # noqa: E402
from wizard.live.storage import unread_buckets  # noqa: E402
from wizard.rendering import render  # noqa: E402
from wizard.report import render_human  # noqa: E402
from wizard.validity import CannotRun  # noqa: E402

NO_DEVIATION, DEVIATIONS_FOUND = 0, 1


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="audit.py",
        description="Measure the live account, as a snapshot read it, against the ADR set.",
    )
    parser.add_argument("--set", required=True, dest="set_path", metavar="PATH",
                        help="the ADR set to measure against")
    parser.add_argument("--declaration", required=True, metavar="PATH",
                        help="the live estate declaration naming the estate's workspaces")
    parser.add_argument("--snapshot", required=True, metavar="PATH",
                        help="the snapshot snapshot.py wrote")
    parser.add_argument("--report", required=True, metavar="PATH",
                        help="where the structured report is written")
    args = parser.parse_args(argv)

    try:
        audited = audit(args.set_path, args.declaration, args.snapshot)
        write(args.report, json.dumps(audited, indent=2, ensure_ascii=False) + "\n")
    except Defective as exc:
        print(f"cannot audit: the {ARTEFACTS[exc.artefact]} is defective", file=sys.stderr)
        print(render_human(exc.artefact, exc.failures), file=sys.stderr)
        return CANNOT_RUN
    except CannotRun as exc:
        print(f"cannot run: {exc}", file=sys.stderr)
        return CANNOT_RUN

    print(render(audited))
    return DEVIATIONS_FOUND if audited["counts"]["deviations"] else NO_DEVIATION


def audit(set_path, declaration_path, snapshot_path):
    """The report of one audit, or a refusal before anything is measured.

    The declaration first, then the set, then
    the snapshot and whether it describes the declaration: one run reports one
    thing, the earliest wrong.
    """
    declaration = live_declaration.read(declaration_path)
    document = validated(adr_set, "adr-set", set_path)
    snapshot = read_snapshot(snapshot_path)
    found = mismatches(snapshot, declaration)
    if found:
        raise CannotRun(f"the snapshot {Path(snapshot_path).name} does not describe the "
                        f"declaration:\n  " + "\n  ".join(found))
    estate = Estate(declaration, snapshot)
    found = unread_buckets(estate)
    if found:
        raise CannotRun(f"the snapshot {Path(snapshot_path).name} holds what the reader never "
                        "writes, so no rule can read it; read the account again:\n"
                        + "\n".join(found))
    compiled = rules.compile_rules(document, estate.clouds(), LIVE, answers=live.answers)
    return report(document, estate, evaluate(compiled, estate))


if __name__ == "__main__":
    raise SystemExit(main())
