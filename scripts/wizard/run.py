"""A run of the wizard: the gate it opens behind, and the cursor the team
answers it through.

A run begins by validating the whole corpus with the validator's checks. Only if every
entry is valid does it present anything; a defective corpus halts before the
first question, naming every defective entry with the rule it broke, and writes
nothing.

**Validation is eager.** `start` performs it in full before it returns anything,
so there is no window in which a card exists and validation has not happened.
Halting before the first question is then a property of the structure rather than of a caller
remembering to check first — which matters because the caller would be the
front end, and a front end that forgot would elicit against a defective
corpus and produce an ADR set missing one of its members.

There is deliberately no way to skip a defective entry and carry on. Skipping
produces the partial target state an abandoned run must never leave, and it is worse than
an abandoned run because nothing about the resulting set announces that
something is absent.
"""

from wizard import append as append_module
from wizard import built_on as built_on_module
from wizard import corpus as corpus_module
from wizard import currency, target
from wizard.modules import module_of
from wizard.report import render_human
from wizard.validity import CannotRun, read_mapping
from wizard.walk import AnswerRefused, RationaleRequired, Walk, dependency_order

INVALID = "corpus-invalid"
UNREADABLE = "corpus-unreadable"

SET_EXISTS = """an ADR set already exists at {path}.

This version cannot re-author an existing set. It writes a set once, and adds
to it only the entries a newer corpus brings; it has neither amendment nor
re-authoring, so there is nothing else it can do with the one that is already
there.{moved}

The only way to start over is to delete that set and run again. That forfeits
the ADR numbers recorded in it — which by now may be cited in failure messages,
commit messages and runbooks, where an old citation would still resolve, to the
wrong decision — and every rationale the team recorded against them.

Nothing was asked and nothing was written."""

SET_DIRECTORY_OCCUPIED = """{path} already holds files, and this version can
only write a set into a directory that is empty or absent.

The set is published by assembling it and moving it into place in one step, so
that a run either leaves a whole set or leaves nothing. That step cannot be
taken over a directory with other files in it.

This is not an existing ADR set — there is no record here — so deleting
anything is not what is being asked for. Move the directory's contents
elsewhere, or empty it, and run again.

Nothing was asked and nothing was written."""


class CorpusHalt(Exception):
    """The run stopped before asking anything, and wrote nothing.

    `reason` separates *the corpus is invalid* from *the corpus could not be
    read*, following the validator's separation of exit 1 from exit 2. The two send a
    team to different places: the first is a defect to file against the corpus
    maintainer, the second is something wrong with their own installation.

    This exception carries what went wrong and nothing that could restart the
    run. The halt is not overridable from inside the run, so there is nothing
    here to override it with.
    """

    def __init__(self, reason, report, failures=()):
        super().__init__(report)
        self.reason = reason
        self.report = report
        self.failures = list(failures)


class SetExists(Exception):
    """The repository already holds a set, so the run stopped before asking
    anything.

    Deliberately not a `CorpusHalt`. That one says the corpus is defective or
    unreadable — a product defect to file against the corpus maintainer, or
    something wrong with the team's installation. This one says the team's own
    repository already holds a file they wrote themselves, which is not a
    defect at all. A front end that caught one for the other would send a team
    to the wrong place, so there is no base class inviting it to.

    Carries what was found and the report, and nothing that could restart the
    run — for the reason `CorpusHalt` carries nothing: the refusal is not
    overridable from inside the run, so there is nothing here to override it
    with.
    """

    def __init__(self, path, report):
        super().__init__(report)
        self.path = path
        self.report = report


class Run:
    """A corpus that passed the gate, and the walk it is answered through.

    The run is a cursor, not an iterator: `current` is the card awaiting an
    answer, `answer` records one and advances. The walk derives the order from
    the entries' `available_when` declarations and recomputes what remains after
    every answer, so there is no sequence of cards to hand out in advance and no
    answer-free way through the walk.

    `repository` is the tree the set will be written to. It is
    carried rather than used here: the gate's business with it is that a halt
    leaves it untouched, and a halt never constructs a Run.

    `manifest`, `corpus_digest` and `entry_digests` are the corpus's identity,
    taken at the gate. They are the only thing about the corpus the write needs
    that is not on a card, and taking them here is what lets the writer read no
    corpus entry at all.

    `folder` is where under `repository` the set lands, `product` the product
    it decides for, and `built_on` the set this walk started from, if any.
    """

    def __init__(self, entries, repository, manifest, corpus_digest,
                 folder=target.SET_DIRECTORY, product=None, built_on=None, recorded=None):
        self._walk = Walk([entry for _, entry in entries], built_on, recorded)
        self.repository = repository
        self.manifest = manifest
        self.corpus_digest = corpus_digest
        self.entry_digests = corpus_module.entry_digests(entries)
        self.folder = folder
        self.product = product
        self.built_on = built_on
        self.recorded = recorded

    @property
    def current(self):
        """The card awaiting an answer, or `None` once every entry is settled
        or pruned."""
        return self._walk.current

    def recorded_conflicts(self):
        """The recorded answers that no longer hold under the set built on as
        it is now, as `Walk.recorded_conflicts` gives them."""
        return self._walk.recorded_conflicts(self.recorded.answers)

    def answer(self, key=None, rationale=None, parameters=None):
        """Answer the card in hand, recompute applicability, and advance.

        A card that offers no keys — advice, which is shown and never asked —
        is advanced with none. An opt-out is refused without a rationale;
        everywhere else a rationale is optional.
        `parameters` are required exactly where the chosen option declares them.
        """
        return self._walk.answer(key, rationale, parameters)

    @property
    def settled(self):
        """Every entry the team answered, in presentation order.

        Each record carries the entry, the answer, any rationale, and the card
        it was answered on — which is what the write projects the set from.
        """
        return self._walk.settled

    @property
    def inapplicable(self):
        """Every entry the answers removed, each naming what removed it."""
        return self._walk.inapplicable

    @property
    def dependency_order(self):
        """The corpus ids of every decision and prescription, in the order the
        set numbers them — computed from the corpus before anything was asked,
        so it does not move with the answers."""
        return self._walk.dependency_order

    @property
    def advice(self):
        """The advice the run showed, in presentation order.

        Not part of `settled` or `inapplicable`: advice yields no rule, so it is
        no input to enforcement and never becomes an ADR.
        The closing report repeats the unattached ones from here.
        """
        return self._walk.advice


def start(corpus_root, repository_root, folder=target.SET_DIRECTORY, product=None):
    """Validate the corpus in full, then return the run.

    `corpus_root` is one module's directory, and `folder` where under
    `repository_root` its set lands. A module that builds on another starts from
    the set that module produced, read from the monorepo's `platform/` folder.

    Raises `CorpusHalt` if the corpus is invalid or cannot be read. There is no
    parameter that admits a skip-and-proceed, because there is no such path.
    """
    try:
        entries = corpus_module.load(corpus_root)
        manifest = corpus_module.load_manifest(corpus_root)
        failures = corpus_module.validate_loaded(
            entries, corpus_module.built_on_of(corpus_root, manifest))
    except CannotRun as exc:
        raise CorpusHalt(UNREADABLE, f"cannot run: {exc}") from None

    if failures:
        raise CorpusHalt(INVALID, render_human("corpus", failures), failures)

    # An existing set is refused in the same phase as the corpus gate, and
    # before a Run exists.
    #
    # Here rather than in a front end, because a `Run` presents a card the
    # moment it exists — `current` is the first one — so "no entry is
    # presented" is only satisfiable by raising instead of returning. A check
    # in `session.py` would also be a check the terminal spike and the test
    # fixtures do not make, which is the argument for eager validation.
    #
    # After the corpus, not before: a defective corpus is a product-integrity
    # fact whatever the repository holds, while an existing set is actionable
    # only once the product works at all.
    existing = target.existing_set(repository_root, folder)
    recorded, reasons = (_walked_up(existing, entries, manifest)
                         if existing is not None else (None, []))

    if existing is None:
        occupied = target.occupied(repository_root, folder)
        if occupied is not None:
            raise SetExists(occupied, SET_DIRECTORY_OCCUPIED.format(path=occupied))

    # Before the first card, and required: answers given without the set this
    # module builds on in view could contradict it, and nothing would say so.
    built_on = (built_on_module.read(repository_root, manifest["builds_on"])
                if manifest.get("builds_on") else None)

    run = Run(entries, repository_root, manifest, corpus_module.digest_of(entries),
              folder, product, built_on, recorded)
    if recorded is not None and built_on is not None:
        reasons += append_module.conflicts(run.recorded_conflicts(), recorded)
    if reasons:
        raise SetExists(existing, append_module.refusal(existing, manifest, reasons))
    return run


def _walked_up(existing, entries, manifest):
    """`(the set at existing, read for an append; the reasons it cannot be)`.

    A set that cannot be read, or that another module wrote, is refused as
    any existing set is. So is one with nothing new, which is also told what
    moved since it was written. One with new entries is appended to unless a
    reason is returned; the caller adds what only the set built on can tell
    before refusing, so that every reason is named at once.
    """
    try:
        document = read_mapping(existing)
    except (CannotRun, ValueError):  # a set that is not UTF-8 is unreadable too
        document = None
    if (not isinstance(document, dict) or not isinstance(document.get("adrs"), list)
            or module_of(document.get("module")) != manifest["module"]):
        raise SetExists(existing, SET_EXISTS.format(path=existing, moved=""))

    invalid = append_module.invalid(existing)
    notice = None if invalid else currency.notice_for(document, manifest, entries)
    if notice is not None and not notice["new"]:
        raise SetExists(existing, SET_EXISTS.format(path=existing, moved=_moved(notice)))
    if invalid:
        if not _shipped_but_unrecorded(document, entries):
            raise SetExists(existing, SET_EXISTS.format(path=existing, moved=""))
        raise SetExists(existing, append_module.refusal(existing, manifest, [invalid]))

    record = append_module.recorded(existing, document, notice,
                                    dependency_order([e for _, e in entries]))
    shipped = {e["id"]: e for _, e in entries if e.get("id")}
    reasons = [r for r in [append_module.without_digests(document)] if r]
    reasons += append_module.dependencies_on_new(record, shipped)
    return record, reasons


def _shipped_but_unrecorded(document, entries):
    """Whether an invalid set still lacks a decision or prescription the module
    ships: the one question an invalid set can be asked, from its ids alone."""
    recorded = {adr.get("corpus_entry") for adr in document["adrs"] if isinstance(adr, dict)}
    return any(e.get("id") not in recorded for _, e in entries
               if e.get("id") and e.get("kind") != currency.ADVICE)


def _moved(notice):
    """What the refusal of a set with nothing new adds: what moved since."""
    changed, removed = notice["changed"], notice["removed"]
    unknown = changed is None and not notice["corpus_digest_matches"]
    if not (changed or removed or unknown):
        return (f"\n\nThe set is current with the shipped module, {notice['module']} "
                f"{notice['shipped_version']}.")
    lines = [f"Written against {notice['module']} {notice['recorded_version']}; this skill "
             f"ships {notice['shipped_version']}, which adds nothing the set does not record."]
    if changed:
        lines.append("Its entries changed since it was written: " + ", ".join(
            f"{c['adr']} ({c['corpus_entry']})" for c in changed) + ".")
    if unknown:
        lines.append("Its entries may have changed since it was written; it records no "
                     "per-entry digests to say which.")
    if removed:
        lines.append("Its entries removed from the corpus since: " + ", ".join(
            f"{r['adr']} ({r['corpus_entry']})" for r in removed) + ".")
    lines.append("Taking up a changed or removed entry is amendment, which this version does "
                 "not have.")
    return "\n\n" + "\n".join(lines)
