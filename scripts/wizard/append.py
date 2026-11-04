"""Walking a set up to a newer corpus: the set read, and what stops it.

A team upgrades the skill and the module it walked gains entries. Running the
walk again appends them: the recorded answers count as given, only the new
entries are asked, and every recorded ADR is written again exactly as it was.

**What is read is answers, as from a set built on.** Each recorded ADR offers
the walk the answer it holds, and the names it recorded. The walk resolves those
entries before it begins, so it never presents them and never writes them: the
write copies the recorded ADRs from the set itself.

**Refused before the first card, for every reason at once.** An append that
could not keep the recorded ADRs as they are is refused before anything is
asked, and the refusal names everything it found, so a team does not fix one
thing to be told of the next. An invalid set is the exception: nothing else in
it can be trusted enough to check.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from wizard.adr_set import set_digest, validate
from wizard.card import Because
from wizard.walk import targets

CHOSEN = "chosen"

REFUSED = """the set at {path} cannot be walked up to {module} {version}.

{reasons}

Each of these needs a recorded ADR changed, which is amendment, and this
version does not have it. The only other way is to delete that set and walk
again. That forfeits the ADR numbers recorded in it — which by now may be cited
in failure messages, commit messages and runbooks, where an old citation would
still resolve, to the wrong decision — and every rationale the team recorded
against them.

Nothing was asked and nothing was written."""


@dataclass(frozen=True)
class Recorded:
    """The set being walked up, as the walk and the write need it.

    `document` is the set as read; the write copies its ADRs from here and
    nowhere else. `notice` is what moved since it was written, as the validator
    reports it, and
    `new` the entries the append adds, in the order they are numbered.
    """

    path: Path
    document: dict
    notice: dict
    new: Tuple[str, ...]

    @property
    def adrs(self):
        return tuple(self.document["adrs"])

    @property
    def digest(self):
        return set_digest(self.document)

    @property
    def numbers(self):
        """`{corpus id: ADR number}` for every recorded ADR."""
        return {adr["corpus_entry"]: adr["id"] for adr in self.adrs}

    @property
    def answers(self):
        """`{corpus id: chosen key}`, or `None` for an entry recorded inapplicable."""
        return {adr["corpus_entry"]: chosen(adr) for adr in self.adrs}

    @property
    def parameters(self):
        """`{name: (values, because)}` for every name a recorded answer gave."""
        return {
            name: (tuple(values), Because(adr["corpus_entry"], chosen(adr)))
            for adr in self.adrs
            for name, values in (adr.get("parameters") or {}).items()
        }

    @property
    def highest(self):
        """The highest number the set records, as an integer."""
        return max(int(adr["id"].partition("-")[2]) for adr in self.adrs)


def chosen(adr):
    """The key of the option an ADR records as chosen, or `None` for one an
    answer made inapplicable, which has no options."""
    keys = [o["key"] for o in adr.get("options") or [] if o.get("status") == CHOSEN]
    return keys[0] if keys else None


def recorded(path, document, notice, dependency_order):
    """The set as an append reads it. `notice` must name new entries."""
    new = tuple(entry for entry in dependency_order if entry in set(notice["new"]))
    return Recorded(Path(path), document, notice, new)


def invalid(path):
    """The reason an invalid set cannot be appended to, or `None`."""
    failures = validate(path)
    if not failures:
        return None
    count = f"{len(failures)} {'failure' if len(failures) == 1 else 'failures'}"
    return (f"- It is not a valid ADR set ({count}; run validate.py on it to see them), so "
            "nothing else about it was checked.")


def without_digests(document):
    """The reason a set with no per-entry digests cannot be appended to, or `None`."""
    if all("corpus_entry_digest" in adr for adr in document["adrs"]):
        return None
    return ("- Its ADRs record no per-entry digests: it was written before they existed. "
            "After an append it would name the shipped corpus, and could no longer say which "
            "of its entries changed.")


def dependencies_on_new(record, shipped):
    """A reason for each recorded ADR whose shipped entry now declares on a new one.

    Either level counts: an entry available only when the new one is answered a
    given way, or an option that is.
    """
    new = set(record.new)
    reasons = []
    for adr in record.adrs:
        entry = shipped.get(adr["corpus_entry"])
        on = sorted(targets(entry) & new) if entry is not None else []
        if on:
            reasons.append(f"- {adr['id']} ({adr['corpus_entry']}) now depends on "
                           f"{', '.join(on)}, which is new: its answer could remove what "
                           "the team already chose.")
    return reasons


def conflicts(found, record):
    """A reason for each recorded answer that no longer holds under the set
    built on as it is now, from `Run.recorded_conflicts`."""
    reasons = []
    for corpus_entry, kind, because in found:
        adr = record.numbers[corpus_entry]
        decided = _referred(because, record) if because is not None else None
        if kind == "applicable":
            made = next(a.get("made_inapplicable_by") for a in record.adrs
                        if a["corpus_entry"] == corpus_entry)
            reasons.append(f"- {adr} ({corpus_entry}) is recorded inapplicable, made so by "
                           f"{made}, and is now applicable.")
        elif kind == "inapplicable":
            reasons.append(f"- {adr} ({corpus_entry}) is recorded as answered, and {decided} "
                           "now makes it inapplicable.")
        else:
            reasons.append(f"- {adr} ({corpus_entry}) records an option {decided} now "
                           "removes.")
    return reasons


def _referred(because, record):
    """What decides a recorded answer now, in the set's own vocabulary: an ADR of
    the set built on as it is qualified, one of this set by its number."""
    entry = because.entry
    reference = entry if "/" in entry else record.numbers.get(entry, entry)
    return f"{reference}'s answer" if because.answer is None else \
        f"{reference}'s answer {because.answer!r}"


def refusal(path, manifest, reasons):
    return REFUSED.format(path=path, module=manifest["module"], version=manifest["version"],
                          reasons="\n".join(reasons))


def notice_of(record, built_on):
    """`start`'s `append` field: what the append will ask, and what moved."""
    notice = {
        "set": str(record.path),
        "recorded_version": record.notice["recorded_version"],
        "shipped_version": record.notice["shipped_version"],
        "new": list(record.new),
        "changed": record.notice["changed"],
        "removed": record.notice["removed"],
    }
    if built_on is not None:
        notice["builds_on"] = {"recorded": (record.document.get("builds_on") or {}).get("digest"),
                               "read": built_on.digest}
    return notice
