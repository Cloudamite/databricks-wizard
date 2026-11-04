"""The ADR set write: what a finished run leaves in a repository.

**A projection, not a second reading of the corpus.** Cards went in, answered
cards came out, and everything written here is on a `Settled` record's card, on
an `Inapplicable` record, or on the run's own corpus identity. Nothing in this
module opens a corpus file. A writer that read the corpus again would be a
second interpretation of it, and the two would drift the first time a card
field changed.

**The options are the record of what happened.** Exactly one is `chosen`; an
option an earlier answer took away is `pruned` and names the ADR that took it;
an option with no status was selectable and not taken. There is no `decision`
string and no `answer_key` restating any of that, because a restatement can
disagree with what it restates and the set would still be valid.

**The set is assembled, then published in one move.** Every file — the record
and each rendered document — is written into a staging directory beside the
target, and the record is validated there. Only then is the staging directory
renamed onto `docs/decisions`, which is a single syscall: the set appears whole
or does not appear. A failure anywhere before that leaves nothing behind, and
the staging directory is removed on every path.

Beside the target rather than in the system temp directory, because `rename(2)`
is atomic only within one filesystem, and `/tmp` is frequently not the one the
repository is on. Staging elsewhere would force the publish to be a copy, and a
copy of nine files is nine separate writes, and the set must appear whole or
not at all.
"""

import datetime
import errno
import os
import re
import shutil

import yaml

from wizard import target
from wizard.adr_set import validate
from wizard.card import Option
from wizard.target import RECORD_NAME, SET_DIRECTORY
from wizard.validity import DECLINED

# Where a set lands and what the record is called are `target.py`'s to say, so
# that the gate refusing an existing set and this module cannot come to
# disagree about the path. Re-exported so the write's names are importable
# from the write.
__all__ = ["RECORD_NAME", "SET_DIRECTORY", "WriteRefused", "write_set"]

# The option a single-state prescription is written with. Its card offers no
# states to select among — the target state is disclosed as prose and the two
# answers are `accepted` and `declined` — so the write authors the one option
# that state is, and `declined` sits beside it as it does everywhere else.
ACCEPTED = "accepted"

# The shape of the set this module writes — what an analyzer must understand
# to read it. Not the corpus manifest's `schema_version`, which versions the
# shape of a corpus entry: the two are independent and happen both to be 1.
SCHEMA_VERSION = 1

ADOPTED = "adopted"
INAPPLICABLE = "inapplicable"
CHOSEN = "chosen"
PRUNED = "pruned"

# A flag renders as a phrase or as nothing at all, so the phrase is named here
# rather than buried in the renderer: it is the one record value a reader could
# not otherwise see in the text.
VENDOR_DEFAULT = "- The state the vendor endorses"
PRODUCT_PREFERRED = "- The state this product prefers, where the vendor declines to choose"

NOTICE = (
    "<!-- This document is generated from adr-set.yaml and regenerated in full "
    "on every write. Any hand edit to it is lost. Change the record, not this "
    "file. -->"
)


class WriteRefused(Exception):
    """The set would not have passed validation, so nothing was written.

    It carries the failures rather than a message alone: the caller reporting
    this is telling a team that a run they completed produced something the
    product will not stand behind, and the rules it broke are the only useful
    thing to say about that.
    """

    def __init__(self, failures):
        super().__init__("; ".join(failure.rule for failure in failures))
        self.failures = list(failures)


# --- The record ------------------------------------------------------------


def numbers_for(run):
    """`{corpus id: ADR number}`, ascending from `ADR-001`.

    Over the corpus dependency order, which the run computed before anything
    was asked — so the same corpus numbers a given entry the same whatever the
    team answers. An append keeps every recorded number and numbers the new
    entries, in that order, from the one after the highest recorded.
    """
    if run.recorded is None:
        return {
            corpus_entry: f"ADR-{position:03d}"
            for position, corpus_entry in enumerate(run.dependency_order, start=1)
        }
    numbers = dict(run.recorded.numbers)
    numbers.update(
        (corpus_entry, f"ADR-{position:03d}")
        for position, corpus_entry in enumerate(run.recorded.new,
                                                start=run.recorded.highest + 1)
    )
    return numbers


def without_empties(mapping):
    """Drop what the entry does not have, rather than carrying it empty.

    A field present and null is a different record from a field that was never
    written, and several validity rules turn on exactly that distinction.
    """
    return {key: value for key, value in mapping.items()
            if value not in (None, False) and value != {}}


def rule_of(check):
    """A `Check` as the record holds it."""
    if check is None:
        return None
    return without_empties({
        "summary": check.summary,
        "failure_message": check.failure_message,
        "evaluator": check.evaluator,
        "enforceability": check.enforceability,
        "scope": check.scope,
        "unevaluable_when": check.unevaluable_when,
        "absence_message": check.absence_message,
        # Copied, not recomputed, so the analyzer never has to open the corpus.
        # What is copied is the *claim* — which clouds and which substrates this
        # rule can be checked on — and never the fingerprint itself: no resource
        # type, no attribute path and no provider version reaches the set, which
        # is what lets one set be measured by more than one dialect.
        "clouds": list(check.clouds) or None,
        "substrates": list(check.substrates) if check.substrates else None,
        # Which recorded parameters this rule is measured against. Copied like
        # everything else here: the analyzer resolves them against the set it was
        # handed, and a rule that lost them would be compiled against nothing.
        "uses": list(check.uses) or None,
    })


def vendor_of(vendor):
    """The citation the card disclosed, whatever the entry's origin."""
    if vendor is None:
        return None
    return without_empties({
        "strength": vendor.strength,
        "quote": vendor.quote,
        "source": vendor.source,
        "checked": vendor.checked,
    })


def states_of(card):
    """The states the card put on offer, in the order it disclosed them.

    A single-state prescription has none of its own: its target state is prose
    and its rule is the entry's, so the one option it holds is authored here.
    """
    if card.options:
        return list(card.options)
    if card.target_state is not None:
        return [Option(key=ACCEPTED, label=card.target_state, cost=None,
                       check=card.check)]
    return []


def option_of(key, state):
    """One option of the record. `state` is `None` for a key naming no state."""
    if state is None:
        return {"key": key}
    return without_empties({
        "key": key,
        "label": state.label,
        "cost": state.cost,
        "vendor_default": state.vendor_default,
        "product_preferred": state.product_preferred,
    })


def because_of(because, numbers):
    """What removed something, in the set's own vocabulary.

    ADR numbers rather than corpus ids: a reader following one reference should
    not have to change vocabulary halfway. `answer` is absent for a cascade,
    where the entry named was itself never settled.
    """
    return without_empties({
        "entry": reference(because.entry, numbers),
        "answer": because.answer,
    })


def reference(entry, numbers):
    """This set's ADR number for a corpus id. An answer in the set this one
    builds on already arrives as that set's number, qualified with its module,
    and is recorded as it is."""
    return entry if "/" in entry else numbers[entry]


def options_of(card, answer, numbers):
    """`(options, the rule the answer compiles to, the sentence it leaves open)`.

    At most one of the last two is set: an option left open carries its
    sentence in place of a rule, since the rule is the chosen option's.

    The states on offer, then the ones an earlier answer took away, then the
    reserved key — which is the order `card.disclosure` names.
    """
    options, rules, sentences = [], {}, {}
    for state in states_of(card):
        options.append(option_of(state.key, state))
        rules[state.key] = state.check
        sentences[state.key] = state.unconstrained

    for removed in card.not_offered:
        options.append(dict(
            option_of(removed.key, removed.option),
            status=PRUNED,
            because=because_of(removed.because, numbers),
        ))

    if DECLINED in card.answer_keys:
        # It carries no label: a reserved key means what the product defines it
        # to mean, and prose invented for it would be the one string in the
        # record that came from neither the corpus nor the team.
        options.append({"key": DECLINED})

    for option in options:
        if option["key"] == answer:
            option["status"] = CHOSEN

    return options, rule_of(rules.get(answer)), sentences.get(answer)


def presented(adr_id, settled, numbers, digests):
    """An entry the team answered, projected from the card they answered it
    on."""
    card = settled.card
    options, rule, unconstrained = options_of(card, settled.answer, numbers)
    return without_empties({
        "id": adr_id,
        "corpus_entry": card.corpus_entry,
        "corpus_entry_digest": digests[card.corpus_entry],
        "title": card.title,
        "origin": card.origin,
        "state": DECLINED if settled.answer == DECLINED else ADOPTED,
        "question": card.question,
        "why": card.why,
        "options": options,
        "rule": rule,
        "unconstrained": unconstrained,
        "rationale": settled.rationale,
        # What the answer supplied, in the order it was given. Nothing is
        # derived, defaulted or reordered between the answer and the record: a
        # value the set invented would be a target state nobody agreed to.
        # An entry whose answer supplied none carries no
        # key at all, like every other optional field.
        "parameters": {name: list(values) for name, values in settled.parameters},
        "vendor": vendor_of(card.vendor),
    })


def not_presented(adr_id, record, numbers, digests):
    """An entry an earlier answer removed, which never became a card.

    It carries its identity, its state and what made it so. There is nothing
    else to say about an entry nobody was shown, and options describing a
    screen that never existed would say there was.
    """
    return {
        "id": adr_id,
        "corpus_entry": record.entry,
        "corpus_entry_digest": digests[record.entry],
        "title": record.title,
        "origin": record.origin,
        "state": INAPPLICABLE,
        "made_inapplicable_by": reference(record.because.entry, numbers),
    }


def record_for(run):
    """The whole set, as the record the analyzer reads."""
    numbers = numbers_for(run)
    settled = {record.entry: record for record in run.settled}
    removed = {record.entry: record for record in run.inapplicable}

    # An append writes every recorded ADR exactly as the set recorded it, and
    # projects only the entries it added.
    adrs = list(run.recorded.adrs) if run.recorded is not None else []
    walked = run.recorded.new if run.recorded is not None else run.dependency_order
    for corpus_entry in walked:
        adr_id = numbers[corpus_entry]
        if corpus_entry in settled:
            adrs.append(presented(adr_id, settled[corpus_entry], numbers, run.entry_digests))
        else:
            adrs.append(not_presented(adr_id, removed[corpus_entry], numbers,
                                      run.entry_digests))

    manifest = run.manifest
    return {
        "schema_version": SCHEMA_VERSION,
        # The one field that differs between two otherwise identical runs. The
        # wizard is not bound by the validator's no-clock rule, and recording
        # when a set was authored is worth the one varying field.
        "generated": datetime.date.today().isoformat(),
        # As the set recorded it, on an append: `1` stays `1`, and every reader
        # already takes it as `platform-core`.
        "module": (run.recorded.document["module"] if run.recorded is not None
                   else manifest["module"]),
        # The product a product set decides for, and the set it built on:
        # referred to by module and digest, never copied and never located.
        **({"product": run.product} if run.product else {}),
        **({"builds_on": {"module": run.built_on.module, "digest": run.built_on.digest}}
           if run.built_on else {}),
        "corpus": {"version": manifest["version"], "digest": run.corpus_digest},
        "adrs": adrs,
    }


# --- The prose -------------------------------------------------------------


def slug(title):
    return re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")


def document_name(entry):
    return f"{entry['id']}-{slug(entry['title'])}.md"


def render(entry):
    """One entry as prose, generated from its record and nothing else.

    Every value the record holds reaches this document, and no value reaches it
    from anywhere else. The record stays authoritative: prose that *is* the
    record has to be parsed, and a target state recovered by parsing English is
    one that can be recovered wrongly.
    """
    lines = [NOTICE, "", f"# {entry['id']} — {entry['title']}", ""]
    lines += [f"- Corpus entry: {entry['corpus_entry']}",
              *([f"- Corpus entry digest: {entry['corpus_entry_digest']}"]
                if "corpus_entry_digest" in entry else []),
              f"- Origin: {entry['origin']}",
              f"- State: {entry['state']}"]

    if "made_inapplicable_by" in entry:
        lines += ["", "This entry never applied: an earlier answer removed it. "
                      f"Made inapplicable by {entry['made_inapplicable_by']}."]
    if "question" in entry:
        lines += ["", "## Question", "", entry["question"]]
    if "why" in entry:
        lines += ["", "## Why", "", entry["why"]]

    if entry.get("options"):
        lines += ["", "## Options", ""]
        for option in entry["options"]:
            lines += _option_lines(option)

    if "rule" in entry:
        lines += ["", "## Rule", "", "```", entry["rule"]["summary"], "```", "",
                  f"- Evaluator: {entry['rule']['evaluator']}",
                  f"- Enforceability: {entry['rule']['enforceability']}",
                  f"- On failure: {entry['rule']['failure_message']}"]
        if "absence_message" in entry["rule"]:
            lines.append(f"- When absent: {entry['rule']['absence_message']}")
        # Spelled out rather than printed bare: a reader of the decision record
        # should not have to know what `estate` means to a rule compiler.
        scope = entry["rule"]["scope"]
        lines.append(
            f"- Checked per root ({scope})" if scope == "root"
            else f"- Checked across the whole estate ({scope}), which needs a plan for every "
                 "declared root"
        )
        lines.append(f"- Clouds: {', '.join(entry['rule']['clouds'])}")
        # Named only where it is declared, because absent means every substrate
        # and a line saying so on every entry would bury the entries where it
        # actually constrains something.
        substrates = entry["rule"].get("substrates")
        if substrates:
            lines.append(
                f"- Recorded for {', '.join(substrates)} only — this decision is about the "
                "tool that declares the estate, so it cannot be measured on another"
            )
        if "unevaluable_when" in entry["rule"]:
            lines.append(f"- Cannot be evaluated when {entry['rule']['unevaluable_when']}")

    if "unconstrained" in entry:
        lines += ["", "## Not enforced", "",
                  "This answer carries no rule, so nothing is measured against it. What it "
                  f"leaves open: {entry['unconstrained']}"]

    if "rationale" in entry:
        lines += ["", "## Rationale", "", entry["rationale"]]

    if "vendor" in entry:
        lines += ["", "## Vendor", ""]
        for heading, key in (("Position", "strength"), ("Quote", "quote"),
                             ("Source", "source"), ("Checked", "checked")):
            if key in entry["vendor"]:
                lines.append(f"- {heading}: {entry['vendor'][key]}")

    return "\n".join(lines) + "\n"


def _option_lines(option):
    heading = f"### {option['key']}"
    if "label" in option:
        heading += f" — {option['label']}"
    lines = []
    if "status" in option:
        lines.append(f"- Status: {option['status']}")
    if "cost" in option:
        lines.append(f"- Cost: {option['cost']}")
    if option.get("vendor_default"):
        lines.append(VENDOR_DEFAULT)
    if option.get("product_preferred"):
        lines.append(PRODUCT_PREFERRED)
    if "because" in option:
        answered = option["because"].get("answer")
        removed = f"- Removed by {option['because']['entry']}"
        lines.append(f"{removed} answered {answered}" if answered else removed)
    # An option with nothing but a key and a label — one selectable and not
    # taken — gets no attribute list and no blank line standing in for one.
    return [heading, ""] + (lines + [""] if lines else [])


# --- The write -------------------------------------------------------------


def serialise(record):
    return yaml.safe_dump(record, sort_keys=False, allow_unicode=True)


def _ensure_parent(directory):
    """Create the target's parent chain, returning what was created.

    Returned so that a write which does not reach the publish can put the tree
    back exactly as it found it. `docs/` is usually already there; the
    repository root itself sometimes is not.
    """
    created = []
    parent = directory.parent
    for path in [parent, *parent.parents]:
        if path.exists():
            break
        created.append(path)
    for path in reversed(created):
        path.mkdir()
    return created


def _unwind(created):
    """Remove the directories `_ensure_parent` made, innermost first.

    Stops at the first that is not empty: something else put a file there
    between the two moments, and it is not this function's to delete.
    """
    for path in created:
        try:
            path.rmdir()
        except OSError:
            break


def _stage(staging):
    """An empty staging directory at `staging`.

    Removed first if it is already there. A previous write killed between
    assembling and publishing is the only thing that leaves one, it is ours by
    name, and leaving it would make the publish inherit that run's files.
    """
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    return staging


def _publish(staging, directory):
    """Make the assembled set visible.

    One rename, which is what makes the write atomic: the set appears whole or not
    at all. `rename(2)` also replaces an existing *empty* directory, so absent
    and empty targets take this path without a stat and without a
    rmdir-then-rename race.

    A target that holds files cannot be replaced this way, and nothing portable
    lands N files into one atomically. The gate refuses a directory holding
    anything but a set. What reaches the fallback is an append, writing over
    the set it read, and an in-process caller writing a second time
    over its own set, as the write's own tests do. There the record goes first:
    every `os.replace` is atomic, so the set is replaced in that one move, no
    record is ever half-written, and no document arrives without the record
    behind it. Every recorded ADR's document has the name it had, so none is
    left behind.
    """
    try:
        os.rename(staging, directory)
        return
    except OSError as exc:
        if exc.errno not in (errno.ENOTEMPTY, errno.EEXIST):
            raise

    os.replace(staging / RECORD_NAME, directory / RECORD_NAME)
    for path in sorted(staging.iterdir()):
        os.replace(path, directory / path.name)


def write_set(run):
    """Write the set, and return the path of the record.

    The whole set is assembled and validated beside its target, then moved into
    place in one step. Nothing lands before every file is written and the
    record is known to be good, and a failure at any point leaves the
    repository as it was.
    """
    record = record_for(run)
    documents = {document_name(entry): render(entry) for entry in record["adrs"]}
    directory = target.set_directory(run.repository, run.folder)
    staging = target.staging_directory(run.repository, run.folder)

    created = _ensure_parent(directory)
    published = False
    try:
        staged = _stage(staging)
        (staged / RECORD_NAME).write_text(serialise(record), encoding="utf-8")
        for name, document in documents.items():
            (staged / name).write_text(document, encoding="utf-8")

        failures = validate(staged / RECORD_NAME)
        if failures:
            raise WriteRefused(failures)

        _publish(staged, directory)
        published = True
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        if not published:
            _unwind(created)
    return directory / RECORD_NAME
