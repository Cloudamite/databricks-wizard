#!/usr/bin/env python3
"""Validate a knowledge corpus, an emitted ADR set, an estate declaration, an
exception register, or a live estate declaration.

    uv run --project <skill>/scripts --locked <skill>/scripts/validate.py corpus/
    uv run --project <skill>/scripts --locked <skill>/scripts/validate.py corpus/product-core
    uv run --project <skill>/scripts --locked <skill>/scripts/validate.py platform/adr-set.yaml --json
    uv run --project <skill>/scripts --locked <skill>/scripts/validate.py estate.yaml
    uv run --project <skill>/scripts --locked <skill>/scripts/validate.py exceptions.yaml --estate estate.yaml
    uv run --project <skill>/scripts --locked <skill>/scripts/validate.py live.yaml

The artefact is selected by the argument and never by a flag: a directory is a
corpus, and a file says which of the other four it is by a key its own schema
requires — `adrs` for an ADR set, `roots` for an estate declaration,
`exceptions` for an exception register, `workspaces` for a live estate
declaration. A file carrying none is not a recognised artefact and cannot be
run, and neither can one carrying `workspaces` beside another's key.

A corpus root checks every module under it, and a module's directory that
module alone. A valid ADR set is also compared with the module the skill ships,
and the output says which entries are new, changed or removed since the set
was written. That comparison never changes the exit code: a set written against
an older corpus is still a correct record of what the team decided.

`--estate` applies to a register alone. With it, the register must also name
the declaration's estate and only roots it declares, so a team can check a
change to the register in CI without plans or Terraform.

Exit codes are the contract:

    0  valid
    1  readable and invalid
    2  could not run — bad usage, an unreadable or unparseable file, or a
       missing dependency

*Invalid* and *could not run* never share a code. A CI stage that conflated them
would pass green on a build agent where the dependency is missing, which is
precisely the condition under which nothing was checked at all.

The command makes no network request, invokes no language model, and reads no
clock, hostname or environment variable. Two runs over byte-identical input
produce byte-identical output and the same exit code.
"""

import argparse
import sys
from pathlib import Path

VALID, INVALID, CANNOT_RUN = 0, 1, 2

# The dependency check comes before anything that imports it. A stack trace is
# not an acceptable first encounter with the product, and a build agent without
# PyYAML must be told how to run the script rather than shown a traceback.
try:
    import yaml  # noqa: F401
except ImportError:
    from wizard.environment import missing_yaml
    missing_yaml("read the corpus", CANNOT_RUN)

sys.path.insert(0, str(Path(__file__).resolve().parent))

import importlib  # noqa: E402

from wizard import corpus, currency  # noqa: E402
from wizard.report import render_human, render_json  # noqa: E402
from wizard.validity import CannotRun, artefact_of, read_mapping  # noqa: E402

# The reader each artefact is checked by, named rather than imported. `artefact_of`
# names the artefact and this maps it to the module; neither knows the other's
# business. A skill ships only the readers it needs, so a reader is imported when
# a file of its kind is given, and one the skill does not ship is refused by name.
READERS = {"adr-set": "adr_set", "estate": "estate", "register": "register",
           "live-declaration": "live_declaration"}

# What each artefact is called in a refusal.
KINDS = {"adr-set": "an ADR set", "estate": "an estate declaration",
         "register": "an exception register", "live-declaration": "a live estate declaration"}

# The corpus this skill ships, which a set is compared with.
SHIPPED_CORPUS = Path(__file__).resolve().parent.parent / "corpus"


def reader(mode, path):
    """The module that checks `mode`, or `CannotRun` if this skill does not ship it.

    Only the reader's own absence is refused. An import that fails inside a
    reader that is shipped is a defect, and is raised as one.
    """
    module = f"wizard.{READERS[mode]}"
    try:
        return importlib.import_module(module)
    except ModuleNotFoundError as exc:
        if exc.name != module:
            raise
        raise CannotRun(f"{Path(path).name} is {KINDS[mode]}, which this skill does not "
                        "read") from None


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="validate.py",
        description=(
            "Validate a knowledge corpus (a directory), or an ADR set, estate "
            "declaration, exception register or live estate declaration (a file)."
        ),
    )
    parser.add_argument(
        "path",
        help=("a corpus directory, or an ADR set, estate declaration, exception "
              "register or live estate declaration file"),
    )
    parser.add_argument(
        "--estate",
        dest="estate_path",
        metavar="PATH",
        help="the estate declaration a register must agree with",
    )
    parser.add_argument(
        "--corpus",
        dest="corpus_root",
        metavar="ROOT",
        default=SHIPPED_CORPUS,
        help="the corpus root an ADR set is compared with (default: the one this skill ships)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit the same findings machine-readably on stdout",
    )
    args = parser.parse_args(argv)

    path = Path(args.path)
    notice = absent = object()
    try:
        if path.is_dir():
            mode, failures = "corpus", corpus.validate(path)
        elif path.is_file():
            # Read once to learn what it is, then let the reader read it again.
            # `validate(path)` being self-contained is the contract every caller
            # already has, and the cost is one extra read of a small file.
            mode = artefact_of(read_mapping(path))
            if mode is None:
                raise CannotRun(
                    f"{args.path} declares none of adrs, roots, exceptions and workspaces, "
                    "so it is not an ADR set, an estate declaration, an exception "
                    "register or a live estate declaration"
                )
            failures = reader(mode, path).validate(path)
            if args.estate_path is not None:
                failures += _against(mode, path, args.estate_path)
            if mode == "adr-set" and not failures:
                notice = currency.compare(read_mapping(path), args.corpus_root)
        else:
            raise CannotRun(f"{args.path} is neither a corpus directory nor a file")
    except CannotRun as exc:
        print(f"cannot run: {exc}", file=sys.stderr)
        return CANNOT_RUN

    if notice is absent:
        print((render_json if args.as_json else render_human)(mode, failures))
    elif args.as_json:
        print(render_json(mode, failures, currency=notice))
    else:
        module = read_mapping(path).get("module")
        print("\n".join([render_human(mode, failures), *currency.render(notice, module)]))
    return INVALID if failures else VALID


def _against(mode, path, estate_path):
    """Check a register against its declaration.

    A declaration that is not one, or is defective, cannot run rather than
    reporting the register invalid: a finding about the register would be about
    a file nobody asked to have checked.
    """
    if mode != "register":
        raise CannotRun(f"--estate applies to an exception register; {path.name} is not one")
    declaration = read_mapping(estate_path)
    named = Path(estate_path).name
    if artefact_of(declaration) != "estate":
        raise CannotRun(f"{named} is not an estate declaration")
    if reader("estate", estate_path).validate(estate_path):
        raise CannotRun(f"{named} is a defective estate declaration; validate it on its own")
    return reader("register", path).against(read_mapping(path), declaration, path.name)


if __name__ == "__main__":
    raise SystemExit(main())
