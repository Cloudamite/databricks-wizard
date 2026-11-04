#!/usr/bin/env python3
"""Drive a wizard run across separate processes (the `describe` transport).

    uv run --project <skill>/scripts --locked <skill>/scripts/session.py modules --corpus <root>
    uv run --project <skill>/scripts --locked <skill>/scripts/session.py start --corpus <root> --module <name> --repository <dir>
    uv run --project <skill>/scripts --locked <skill>/scripts/session.py answer --key single
    uv run --project <skill>/scripts --locked <skill>/scripts/session.py write

`Run` is an in-memory cursor. A front end that holds it in a single process —
the terminal spike, a future web server — needs none of this. A front end that
does not, because each turn is a fresh process, needs the run to survive between
turns, and this is how.

**Replay, not serialisation.** The walk derives its order from the corpus and
recomputes applicability after every answer, so the corpus plus the answers
given is a complete description of a run. A journal of answers is therefore the
whole state, and every command reconstructs the run by replaying it:

    run = run_module.start(corpus, repository)
    for key, rationale in journal["answers"]:
        run.answer(key, rationale)

Serialising `Run` instead would introduce a second description of the cursor's
state, which can disagree with the cursor. Replaying cannot: the engine computes
the same thing it always computes. The corpus is nine entries, so the cost is
nothing.

**This is not a renderer.** It emits the card as JSON and never produces prose.
The renderer is whatever reads that JSON — Claude, following SKILL.md, today.
`card.py` explains why the seam is there; putting text here would close it.

**The journal never lives in the target repository.** An abandoned run must
leave the repository as it was, and a half-finished run is exactly such an
abandoned run. Nothing enters the repository before `write`.

Exit codes extend the validator's contract, rather than inventing a second
one:

    0  fine
    1  the answer was refused — retryable, the run is unchanged and still in hand
    2  could not run — a defective corpus, bad usage, a missing dependency

A refusal and a halt never share a code. One means *ask again*, the other means
*stop*, and a front end that conflated them would re-prompt forever against a
corpus that will never validate.
"""

import argparse
import dataclasses
import datetime
import hashlib
import json
import os
import sys
from pathlib import Path

OK, REFUSED, CANNOT_RUN = 0, 1, 2

# The dependency check comes before anything that imports it, for the reason
# `validate.py` states: a stack trace is not an acceptable first encounter with
# the product.
try:
    import yaml  # noqa: F401
except ImportError:
    from wizard.environment import missing_yaml
    missing_yaml("read the corpus", CANNOT_RUN)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from wizard import append as append_module  # noqa: E402
from wizard import built_on as built_on_module  # noqa: E402
from wizard import closing as closing_module  # noqa: E402
from wizard import modules as modules_module  # noqa: E402
from wizard import run as run_module  # noqa: E402
from wizard import target as target_module  # noqa: E402
from wizard import write as write_module  # noqa: E402
from wizard.adr_set import set_digest  # noqa: E402
from wizard.validity import CannotRun, read_mapping  # noqa: E402
from wizard.walk import AnswerRefused  # noqa: E402

JOURNAL_VERSION = 1


def state_root():
    """Where journals live — outside every repository, by construction.

    `XDG_STATE_HOME` if the platform sets it, else a dotted directory under the
    home directory. A run in progress is the user's, not the repository's.
    """
    configured = os.environ.get("XDG_STATE_HOME")
    base = Path(configured) if configured else Path.home() / ".local" / "state"
    return base / "databricks-wizard"


def journal_path(repository, override=None):
    """The journal for a repository, keyed by its resolved path.

    Two runs against two repositories must not collide, and the same repository
    must be resumable by naming nothing but itself. The digest keeps a path
    with separators in it usable as a filename.
    """
    if override:
        return Path(override)
    key = hashlib.sha256(str(Path(repository).resolve()).encode("utf-8")).hexdigest()[:16]
    return state_root() / f"{key}.json"


def load_journal(path):
    try:
        journal = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CannotRun(
            f"no run in progress for this repository ({path} does not exist) — "
            "start one with `session.py start`"
        ) from None
    except (OSError, ValueError) as exc:
        raise CannotRun(f"{path} is not a readable journal: {exc}") from None
    if journal.get("version") != JOURNAL_VERSION:
        raise CannotRun(
            f"{path} was written by a different version of this script "
            f"(found {journal.get('version')!r}, expected {JOURNAL_VERSION})"
        )
    return journal


def save_journal(path, journal):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(journal, indent=2) + "\n", encoding="utf-8")


def replay(journal):
    """Rebuild the run the journal describes.

    The gate runs on every replay, which is deliberate: a corpus that was edited
    mid-run is a corpus the team has not fully answered, and finding that at the
    next card is better than finding it at the write.
    """
    folder = journal.get("folder", target_module.SET_DIRECTORY)
    appended = journal.get("set_digest")
    if appended is not None and _digest_of_set(journal["repository"], folder) != appended:
        # The new entries were walked against the answers the set recorded when
        # the append began. If it has changed since, they may no longer hold.
        raise CannotRun(
            f"the set in {target_module.record_path(journal['repository'], folder)} has "
            "changed since this append started, so the new entries may rest on answers it "
            "no longer records — start the walk again with `session.py start --restart`"
        )
    expected = journal.get("built_on_digest")
    if expected is not None and built_on_module.digest_at(journal["repository"]) != expected:
        # The team was shown options the set built on allowed when the walk
        # began. If it has changed since, some answers may no longer be open.
        raise CannotRun(
            f"the set in {built_on_module.record_path(journal['repository'])} has changed "
            "since this walk started, so answers already given may rest on options it no "
            "longer allows — start the walk again with `session.py start --restart`"
        )
    run = run_module.start(journal["corpus"], journal["repository"], folder,
                           journal.get("product"))
    if appended is not None and (run.recorded is None or run.recorded.digest != appended):
        raise CannotRun("the set this append adds to changed while it was being read — "
                        "start the walk again with `session.py start --restart`")
    if expected is not None and run.built_on.digest != expected:
        raise CannotRun("the set this walk builds on changed while it was being read — "
                        "start the walk again with `session.py start --restart`")
    for answer in journal["answers"]:
        run.answer(answer["key"], answer["rationale"], answer.get("parameters"))
    return run


def _digest_of_set(repository, folder):
    """The digest of the set in `folder`, or `None` if there is none to read."""
    path = target_module.record_path(repository, folder)
    try:
        return set_digest(read_mapping(path)) if path.is_file() else None
    except CannotRun:
        return None


def card_json(card):
    """The card as data, exactly as the engine built it.

    `asdict` walks the nested `Vendor`, `Check`, `Option`, `NotOffered` and
    `Advice` records without this script naming any of their fields — so a field
    added to a card reaches the renderer without an edit here.
    """
    return dataclasses.asdict(card)


def state_of(run, journal, path):
    """What a command prints once it has a run in hand."""
    if run.current is None:
        return {
            "done": True,
            "settled": len(run.settled),
            "inapplicable": [record.entry for record in run.inapplicable],
            "journal": str(path),
            "repository": journal["repository"],
        }
    return {
        "done": False,
        "answered": len(journal["answers"]),
        "journal": str(path),
        "card": card_json(run.current),
    }


def jsonable(value):
    """Dates reach the card as `datetime.date`, and JSON has no date.

    `Vendor.checked` is annotated `str`, but PyYAML resolves an unquoted
    `2026-09-14` to a `date` before any of this product sees it, and the
    annotation is not enforced. ISO-8601 is what the YAML held, so a renderer
    receives the characters the corpus author wrote.
    """
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    raise TypeError(f"cannot serialise {value.__class__.__name__} to JSON")


def emit(payload):
    print(json.dumps(payload, indent=2, default=jsonable))


def chosen_module(args):
    """`(module directory, folder, product)` for the walk `start` was asked for.

    With `--module` or `--type`, `--corpus` is the corpus root, every manifest
    under it is checked, and the set lands in the module's folder of the ADR
    monorepo. With neither, it is one module's directory and the set lands
    where it did before modules: the estate skill's walk, until that skill reads
    its set from the monorepo. Every refusal here comes before an entry or
    another set is read.
    """
    if args.module is None and args.type is None:
        if args.product is not None:
            raise CannotRun("--product names the product of a product module's set; "
                            "name the module with --module")
        return Path(args.corpus), target_module.SET_DIRECTORY, None

    manifests = modules_module.catalog(args.corpus)
    if args.module is None:
        offered = [m["module"] for m in modules_module.listing(manifests, args.type)]
        raise CannotRun(f"--type narrows the modules to choose from, and none was chosen; "
                        f"name one with --module: {', '.join(offered) or 'none'}")
    manifest = modules_module.choose(manifests, args.module, args.type)

    if manifest["type"] == modules_module.PLATFORM:
        if args.product is not None:
            raise CannotRun(f"{args.module} is a platform module, and a platform set "
                            "belongs to no product; leave out --product")
    elif not modules_module.is_product_name(args.product):
        asked = ("a product name is needed" if args.product is None
                 else f"{args.product!r} cannot be a product name")
        raise CannotRun(f"{asked}: {modules_module.PRODUCT_NAME_RULE}")

    folder = modules_module.folder_for(manifest["type"], args.product)
    return Path(args.corpus) / args.module, folder, args.product


def do_modules(args):
    emit(modules_module.listing(modules_module.catalog(args.corpus), args.type))
    return OK


def do_start(args):
    path = journal_path(args.repository, args.state)
    if Path(path).exists() and not args.restart:
        raise CannotRun(
            f"a run is already in progress for this repository ({path}) — "
            "resume it with `session.py card`, or discard it with "
            "`session.py abandon`"
        )
    module, folder, product = chosen_module(args)
    journal = {
        "version": JOURNAL_VERSION,
        "corpus": str(module.resolve()),
        "repository": str(Path(args.repository).resolve()),
        "answers": [],
    }
    if folder != target_module.SET_DIRECTORY:
        journal["folder"] = folder.as_posix()
    if product is not None:
        journal["product"] = product
    run = replay(journal)  # the gate, before a journal exists to resume
    if run.built_on is not None:
        # What the walk was shown, pinned: every later command compares it.
        journal["built_on_digest"] = run.built_on.digest
    if run.recorded is not None:
        # The set the append adds to, pinned the same way.
        journal["set_digest"] = run.recorded.digest
    save_journal(path, journal)
    state = state_of(run, journal, path)
    if run.recorded is not None:
        state["append"] = append_module.notice_of(run.recorded, run.built_on)
    emit(state)
    return OK


def do_card(args):
    path = journal_path(args.repository, args.state)
    journal = load_journal(path)
    emit(state_of(replay(journal), journal, path))
    return OK


def parameters_given(raw):
    """The `--parameters` argument as the engine takes it.

    A malformed document is a refusal rather than a halt, because it is
    something the team can type again — the same class as an answer the card
    does not offer.
    """
    if not raw:
        return None
    try:
        given = json.loads(raw)
    except ValueError as exc:
        raise AnswerRefused(f"--parameters is not readable JSON: {exc}") from exc
    if not isinstance(given, dict):
        raise AnswerRefused("--parameters must be a JSON object of name to list of names")
    return given


def do_answer(args):
    path = journal_path(args.repository, args.state)
    journal = load_journal(path)
    run = replay(journal)
    if run.current is None:
        raise CannotRun("every entry is settled — there is nothing to answer")

    try:
        run.answer(args.key, args.rationale, parameters_given(args.parameters))
    except AnswerRefused as exc:
        # The journal is untouched, so the card is still in hand and the team
        # can answer it again. This is the whole reason a refusal is not a halt.
        print(f"answer refused: {exc}", file=sys.stderr)
        emit({"refused": str(exc), "card": card_json(run.current)})
        return REFUSED

    journal["answers"].append({
        "key": args.key,
        "rationale": args.rationale,
        # Absent rather than null where nothing was supplied, so a journal
        # written by this version replays through one that predates parameters
        # and a journal written by that one replays here.
        **({"parameters": parameters_given(args.parameters)} if args.parameters else {}),
    })
    save_journal(path, journal)
    emit(state_of(run, journal, path))
    return OK


def do_write(args):
    path = journal_path(args.repository, args.state)
    journal = load_journal(path)
    run = replay(journal)
    if run.current is not None:
        raise CannotRun(
            f"{run.current.corpus_entry} is still unanswered — a partial target "
            "state is worse than none, so nothing is written"
        )

    try:
        record = write_module.write_set(run)
    except write_module.WriteRefused as exc:
        print(f"nothing was written: {exc}", file=sys.stderr)
        return CANNOT_RUN

    Path(path).unlink(missing_ok=True)
    # The closing report, built from what landed rather than from the
    # run that produced it. The card carries the entry count, so nothing is
    # emitted beside it that would restate what it already says.
    emit({
        "written": str(record),
        "card": card_json(closing_module.report_for(
            record, run.advice,
            [adr["id"] for adr in run.recorded.adrs] if run.recorded is not None else ())),
    })
    return OK


def do_abandon(args):
    path = journal_path(args.repository, args.state)
    existed = Path(path).exists()
    Path(path).unlink(missing_ok=True)
    emit({"abandoned": existed, "journal": str(path), "wrote_nothing": True})
    return OK


COMMANDS = {
    "modules": do_modules,
    "start": do_start,
    "card": do_card,
    "answer": do_answer,
    "write": do_write,
    "abandon": do_abandon,
}


def build_parser():
    parser = argparse.ArgumentParser(
        prog="session.py",
        description="Drive a wizard run across separate processes.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def with_common(name, help_text, needs_corpus=False):
        child = sub.add_parser(name, help=help_text)
        child.add_argument(
            "--repository",
            default=".",
            help="the repository the ADR set will be written to — the ADR monorepo's "
                 "root when a module is named (default: .)",
        )
        child.add_argument(
            "--state",
            default=None,
            help="the journal file, if not the default for this repository",
        )
        if needs_corpus:
            child.add_argument(
                "--corpus", required=True,
                help="the corpus root, or one module's directory when no module is named"
            )
        return child

    listed = sub.add_parser("modules", help="list the modules the corpus ships")
    listed.add_argument("--corpus", required=True, help="the corpus root")
    listed.add_argument("--type", choices=modules_module.TYPES, default=None,
                        help="list only the modules of this type")

    start = with_common("start", "validate the corpus and present the first card", True)
    start.add_argument(
        "--restart",
        action="store_true",
        help="discard a run already in progress for this repository",
    )
    start.add_argument("--module", default=None,
                       help="the module to walk; --corpus is then the corpus root")
    start.add_argument("--type", choices=modules_module.TYPES, default=None,
                       help="refuse a module of the other type")
    start.add_argument("--product", default=None,
                       help="the product a product module's set decides for")
    with_common("card", "the card awaiting an answer")
    answer = with_common("answer", "answer the card in hand and advance")
    answer.add_argument("--key", required=True, help="one of the card's answer_keys")
    answer.add_argument(
        "--rationale",
        default=None,
        help="required when opting out of a prescription, optional elsewhere",
    )
    answer.add_argument(
        "--parameters",
        default=None,
        help="JSON object of the names the chosen option asks for, "
             'e.g. \'{"environments": ["dev", "prod"]}\'',
    )
    with_common("write", "write the ADR set and close the run")
    with_common("abandon", "discard the run; the repository is left as it was")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except run_module.CorpusHalt as halt:
        # The corpus is defective. Nothing was asked and nothing written.
        print(halt.report, file=sys.stderr)
        return CANNOT_RUN
    except run_module.SetExists as refusal:
        # The repository already holds a set, or a directory this
        # version cannot publish into. Nothing was asked and nothing written.
        #
        # Reported whole rather than through the `cannot run:` prefix below,
        # because the refusal is four statements — what was found, that this
        # version cannot re-author it, that deletion is the only way forward,
        # and what deletion costs — and a team that acts on the first without
        # reading the fourth loses the rationale behind every decision.
        print(refusal.report, file=sys.stderr)
        return CANNOT_RUN
    except CannotRun as exc:
        print(f"cannot run: {exc}", file=sys.stderr)
        return CANNOT_RUN


if __name__ == "__main__":
    raise SystemExit(main())
