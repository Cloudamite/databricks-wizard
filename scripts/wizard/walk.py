"""The dependency-ordered walk, and the pruning answers drive.

No file states the presentation order, because dependencies are declared
backwards — by the entry that depends on another, never by the entry depended
upon. That direction is what lets a new entry be added by writing one file, and
what will let a team's own entry depend on a shipped one without editing a
shipped file. The cost is that the order has to be derived, which is what this
module does.

**Pure.** It reads no files, prints nothing, and knows nothing about a terminal:
it takes the entries the corpus loader already returned and hands back cards.
The engine stays a candidate for a front end that is not a command line.

**Eager recomputation.** Every answer is followed by a sweep that resolves
everything the answer determined, not just the entry about to be presented. A
team that has just pruned six entries has pruned them now, not when the walk
would have arrived at each — and the remaining-work estimate would otherwise
report a number the run already knows to be wrong.

The corpus reaching this module has passed the run's gate, so `available_when`
resolves and the graph is acyclic. Neither is re-checked here; the walk would
have nothing useful to say about a corpus the gate exists to stop.
"""

from dataclasses import dataclass

from wizard import elicit
from wizard.card import Because
from wizard.corpus import dependencies, is_graded
from wizard.validity import is_stated


@dataclass(frozen=True)
class Inapplicable:
    """An entry the answers removed, and what removed it.

    The write puts these into the ADR set: an inapplicable entry stays in the
    set, marked as such, and yields no rule — the same shape as a prescription
    the team opted out of.

    It carries `title` and `origin` because it never became a card and the
    writer reads no corpus entry. What comes out of a run is the cards the team
    answered, plus the identity of what never became one; there is nothing else
    to say about an entry nobody was shown.
    """

    entry: str
    because: Because
    title: str = None
    origin: str = None


@dataclass(frozen=True)
class Settled:
    """One answered entry: what the team said, and why where they said why.

    `rationale` is `None` when none was given rather than an empty string, so
    "the team declined to explain an optional choice" and "the team wrote
    nothing" are not the same record.

    `card` is the card the team answered, carried out of the run intact. The
    ADR set is a projection of it: the title, the states on offer, the ones an
    earlier answer closed, the rule each compiles to and the citation behind
    them are all already there, and a writer reaching back into the corpus
    would be a second interpretation of it.
    """

    entry: str
    answer: str
    rationale: str = None
    card: "Card" = None
    # What the chosen option asked the team for, as ordered pairs: two answers
    # that recorded the same names recorded them in the order they were given,
    # and the order is what says which environment is production.
    parameters: tuple = ()


class AnswerRefused(ValueError):
    """An answer the card in hand does not offer.

    Refusing is the only observable form of "not selectable": an engine that
    leaves a pruned key out of the keys it offers and accepts it anyway
    satisfies the absence and breaks the guarantee.
    """


class RationaleRequired(AnswerRefused):
    """An opt-out with nothing written against it.

    Declining is the act that leaves no reasoning behind, so it costs a written
    rationale. If both responses cost the same, opting out
    becomes the path of least resistance and the set fills with declined entries
    nobody engaged with.
    """


class ParametersRequired(AnswerRefused):
    """An option chosen without the names it cannot be measured without.

    The same shape as `RationaleRequired`, and for the same reason: an answer
    that is missing part of itself leaves the run unchanged rather than
    recording half of it. A set holding a decision whose parameter is absent
    would compile to a rule with a hole in it, discovered by the analyzer weeks
    later.
    """


DECLINED = "declined"


def stated_values(values):
    """Whether `values` is something a rule can be measured against.

    A non-empty sequence of distinct, non-empty strings. Checked here, at the
    point the team can still fix it cheaply, as well as in the set's validity
    table — a value that reaches the record defective has already been written
    into a document the team merges.
    """
    if not isinstance(values, (list, tuple)) or not values:
        return False
    if any(not is_stated(value) for value in values):
        return False
    return len(set(values)) == len(values)


def is_rationale(text):
    """Whitespace alone is not a rationale."""
    return is_stated(text)


def is_attached_advice(entry):
    """Advice that names an entry it belongs beside.

    It is never a step of its own: Basic Flow 6 shows it *with* the entry, and a
    screen of its own would make guidance nothing checks look like a question
    the team failed to answer.
    """
    return entry.get("kind") == "advice" and entry.get("relates_to") is not None


def offers(entry):
    """`[(key, declaration | None), ...]` — what the card offers, in order.

    A prescription's disposition is an answer like any other, so the reserved
    `accepted` / `declined` appear here beside a decision's option keys and a
    graded prescription's alternatives. `declined` is always available: opting
    out is not something an earlier answer can take away.
    """
    kind = entry.get("kind")
    if kind == "decision":
        return [(o["key"], o.get("available_when")) for o in entry.get("options") or []]
    if kind == "prescription":
        if is_graded(entry):
            alternatives = entry.get("alternatives") or []
            return [(a["key"], a.get("available_when")) for a in alternatives] + [
                ("declined", None)
            ]
        return [("accepted", None), ("declined", None)]
    return []  # advice is shown, never asked


def targets(entry):
    """Every entry of this module this one declares on, from both levels of
    declaration.

    A key into the set the module builds on is qualified with that module's
    name, and is left out: that set was settled before the walk began, so it
    orders nothing and is never waited for.
    """
    found = set()
    for declaration in dependencies(entry):
        found.update(t for t in declaration if "/" not in t)
    return found


def dependency_order(entries):
    """The corpus ids of every decision and prescription, in the order the ADR
    set numbers them.

    A topological order over the whole corpus, lowest entry id breaking ties
    between entries neither of which depends on the other. It is computed
    before anything is asked and so does not move with the answers: the same
    corpus numbers a given entry the same for every team holding it.

    The walk's own resolution order is also a dependency order covering
    everything, and was rejected for numbering because the sweep resolves an
    entry an answer just removed before the next card is presented — a pruned
    entry would take a number ahead of one still to come.

    Advice is absent: it yields no rule and is not in the set, so there is
    nothing for it to be numbered as. It terminates because the corpus reaching
    this module has passed the gate and its graph is acyclic.
    """
    pending = {
        entry["id"]: targets(entry)
        for entry in entries
        if entry.get("id") and entry.get("kind") != "advice"
    }
    ordered = []
    while pending:
        # An entry is ready once nothing it declares on is still waiting. A
        # target outside this set — an advice entry, or an id the corpus does
        # not hold — orders nothing, and the gate has already ruled on both.
        ready = min(key for key, on in pending.items() if not on & pending.keys())
        ordered.append(ready)
        del pending[ready]
    return tuple(ordered)


class Walk:
    """The cursor a run is driven through.

    `current` is the card awaiting an answer, `answer` records one and advances.
    There is deliberately no answer-free path: an iterator over the entries
    would be a second walk that prunes nothing, and pruning is the point.
    """

    def __init__(self, entries, built_on=None, recorded=None):
        self._entries = {e["id"]: e for e in entries if e.get("id")}
        self._built_on = built_on   # the set this walk builds on, or None
        self._recorded = recorded   # the set this walk appends to, or None
        self.dependency_order = dependency_order(entries)
        self._answers = {}          # id -> answer key, or None for advice
        self._removed = {}          # id -> Because
        self._resolved_at = {}      # id -> the order in which it was resolved
        self._settled = []
        self._inapplicable = []
        self._advice = []
        self._current = None
        self._attached_now = ()
        if recorded is not None:
            self._take_recorded(recorded.answers)
        self._advance()

    def _take_recorded(self, answers):
        """Resolve every entry the set appended to records, as it records it.

        Resolved, so the walk never presents them; answered or removed, so they
        act on the new entries as answers given in this walk would. Neither
        settled nor inapplicable, so the write does not project them again: it
        copies the recorded ADRs. An entry the corpus no longer ships is skipped,
        since nothing shipped can declare on it.
        """
        for entry_id, answer in answers.items():
            if entry_id not in self._entries:
                continue
            self._resolve(entry_id)
            if answer is not None:
                # One recorded inapplicable needs nothing more: resolved and
                # unanswered, it satisfies no declaration, as a removed one.
                self._answers[entry_id] = answer
        # Advice of its own is a step of a walk, and the walk that wrote the set
        # took it. An append asks only what the set does not record, and a set
        # records no advice. Attached advice still shows
        # beside a new entry, as it would in any walk.
        for entry_id, entry in sorted(self._entries.items()):
            if entry.get("kind") == "advice" and not is_attached_advice(entry):
                self._resolve(entry_id)

    # --- What the caller sees ---------------------------------------------

    @property
    def current(self):
        return self._current

    @property
    def settled(self):
        return tuple(self._settled)

    @property
    def inapplicable(self):
        return tuple(self._inapplicable)

    @property
    def advice(self):
        """The advice the run showed, in presentation order.

        Separate from `settled` and `inapplicable` because those are what the
        ADR set is written from, and advice yields no rule — there is nothing
        for it to be an ADR of. Keeping it out here means
        the write needs no kind check, and no later consumer has to remember
        one. The closing report reads this instead.
        """
        return tuple(self._advice)

    def recorded_conflicts(self, answers):
        """`[(entry id, kind, because), ...]` for each recorded answer that no
        longer holds, read with the shipped declarations.

        `kind` is `applicable` for an entry recorded inapplicable that nothing
        now removes, `inapplicable` for an answered entry something now removes,
        and `removed` for an answer whose option is no longer offered. `because`
        is what removes it, `None` for `applicable`.
        """
        found = []
        for entry_id in self.dependency_order:
            if entry_id not in answers:
                continue
            recorded = answers[entry_id]
            because = self._blocker(self._entries[entry_id].get("available_when"))
            selectable, removed = self._pruned_options(entry_id)
            if because is None and removed and not selectable:
                because = max((b for _, b in removed), key=self._rank)
            if recorded is None:
                if because is None:
                    found.append((entry_id, "applicable", None))
            elif because is not None:
                found.append((entry_id, "inapplicable", because))
            elif recorded not in selectable:
                removing = dict(removed).get(recorded)
                if removing is not None:
                    found.append((entry_id, "removed", removing))
        return found

    def answer(self, key=None, rationale=None, parameters=None):
        """Record an answer to the card in hand, recompute, and advance.

        A rationale is optional everywhere except an opt-out, where it is the
        condition of the entry being settled at all. Parameters are required
        exactly where the chosen option declares them, and refused where it does
        not — an answer carrying a name no state asked for is an answer to a
        different question.
        """
        if self._current is None:
            raise AnswerRefused("there is no card in hand to answer")

        card = self._current
        if card.answer_keys and key not in card.answer_keys:
            raise AnswerRefused(
                f"{key!r} is not offered for {card.corpus_entry} — "
                f"{', '.join(card.answer_keys)}"
            )
        if not card.answer_keys and key is not None:
            raise AnswerRefused(
                f"{card.corpus_entry} takes no answer, and {key!r} was given"
            )
        if key == DECLINED and not is_rationale(rationale):
            raise RationaleRequired(
                f"opting out of {card.corpus_entry} requires a rationale; "
                f"{rationale!r} is not one"
            )

        recorded = self._parameters_for(card, key, parameters)

        self._resolve(card.corpus_entry)
        self._answers[card.corpus_entry] = key
        if self._entries[card.corpus_entry].get("kind") != "advice":
            # Blank prose is not a rationale and is recorded as none given: an
            # optional prompt the team pressed Enter at sends `""`, and an ADR
            # carrying an empty rationale reads as a team that explained itself
            # and said nothing.
            self._settled.append(
                Settled(card.corpus_entry, key,
                        rationale if is_rationale(rationale) else None,
                        card, recorded)
            )
        self._record_advice(card.corpus_entry)
        self._advance()

    def _parameters_for(self, card, key, given):
        """What this answer records, or the refusal that stops it recording.

        Declared on the chosen option and nowhere else, so the question *what is
        required here* has one answer whatever else the card offers. A
        declaration an earlier answer already gave is not asked, and supplying
        it again is refused: a second value would be a second record of one
        fact.
        """
        chosen = [
            parameter
            for option in card.options if option.key == key
            for parameter in option.parameters
        ]
        if key == "accepted":  # a single-state prescription declares its own
            chosen += list(card.parameters)
        declared = [p for p in chosen if not p.given]
        supplied = dict(given or {})

        again = [p for p in chosen if p.given and p.name in supplied]
        if again:
            raise AnswerRefused(
                "; ".join(f"{p.name} was already given by the answer to {p.given_by.entry}"
                          for p in again)
                + f", and is not asked for again on {card.corpus_entry}"
            )

        missing = [p.name for p in declared if p.name not in supplied]
        if missing:
            raise ParametersRequired(
                f"{card.corpus_entry} records {key!r} only with "
                f"{', '.join(missing)}; the answer supplied none of them"
            )

        unasked = [name for name in supplied if name not in {p.name for p in declared}]
        if unasked:
            raise AnswerRefused(
                f"{key!r} on {card.corpus_entry} asks for nothing called "
                f"{', '.join(sorted(unasked))}"
            )

        defective = [name for name, values in supplied.items() if not stated_values(values)]
        if defective:
            raise AnswerRefused(
                f"{', '.join(sorted(defective))} on {card.corpus_entry} must each be a list of "
                "distinct, non-empty names; a rule measured against anything else would "
                "measure nothing and pass"
            )

        # Ordered pairs in the order the option declared them, with each value
        # sequence in the order the team gave it: the last environment is
        # production, so the order is part of the answer rather than a rendering.
        return tuple((p.name, tuple(supplied[p.name])) for p in declared)

    # --- The machine -------------------------------------------------------

    def _given(self):
        """`{name: (values, because)}` for every parameter an answer supplied.

        One entry per name, because a name is one fact across the set and the
        walk refuses a second value for it.
        """
        given = dict(self._built_on.parameters) if self._built_on else {}
        if self._recorded is not None:
            given.update(self._recorded.parameters)
        given.update(
            (name, (values, Because(settled.entry, settled.answer)))
            for settled in self._settled
            for name, values in settled.parameters
        )
        return given

    def _rank(self, because):
        """When the answer `because` names was given. An answer in the set this
        walk builds on was given before anything in it."""
        return self._resolved_at.get(because.entry, -1)

    def _resolve(self, entry_id):
        self._resolved_at[entry_id] = len(self._resolved_at)

    def _unresolved(self):
        return [i for i in sorted(self._entries) if i not in self._resolved_at]

    def _determinable(self, entry_id):
        """True once every entry this one declares on has been settled or
        removed — which is when it can be presented, and the earliest its own
        applicability can be decided."""
        return all(t in self._resolved_at for t in targets(self._entries[entry_id]))

    def _satisfied_by(self, target_id, keys):
        """The answer on `target_id`, if it satisfies `keys`; otherwise the
        `Because` that explains why it does not."""
        if "/" in target_id:
            # A key into the set this walk builds on, answered before it began.
            return self._built_on.satisfied(target_id.partition("/")[2], keys)
        if target_id in self._removed:
            # It was never settled, so no answer can be named for it. The record
            # points one step up the chain rather than skipping to the root.
            return Because(target_id, None)

        answer = self._answers.get(target_id)
        if answer in keys:
            return None
        if (
            "accepted" in keys
            and self._entries[target_id].get("kind") == "prescription"
            and answer not in (None, "declined")
        ):
            # `accepted` is a wildcard over any adopted state, so adding an
            # alternative to a prescription does not require editing the entries
            # that depend on it.
            return None
        return Because(target_id, answer)

    def _blocker(self, declaration):
        """Why `declaration` cannot be satisfied, or `None` if it can.

        Several targets are an AND. When more than one of them blocks, the one
        that resolved last is named: it is the answer that settled the matter,
        and the same rule picks the answer that removed an entry's last option.
        """
        if not isinstance(declaration, dict):
            return None
        blockers = [
            because
            for target, keys in sorted(declaration.items())
            if (because := self._satisfied_by(target, keys or [])) is not None
        ]
        if not blockers:
            return None
        return max(blockers, key=self._rank)

    def _record_advice(self, entry_id):
        """Everything the card just answered showed, in the order it showed it.

        An advice card is its own advice; any other card carries what the corpus
        attached to it. Both reach one collection, each record naming what it
        relates to, so the closing report can repeat the unattached without the
        run having decided that for it.
        """
        if self._entries[entry_id].get("kind") == "advice":
            self._advice.append(elicit.advice_of(self._entries[entry_id]))
        for advice_id in self._attached_now:
            self._resolve(advice_id)
            self._advice.append(elicit.advice_of(self._entries[advice_id]))

    def _attached_to(self, host_id):
        """The advice belonging beside `host_id`, in entry-id order.

        The same tie-break `_advance` uses on entries, on a second axis: the
        corpus states no sequence here either.

        Advice an earlier answer already made unavailable is excluded by having
        been resolved — the sweep runs to a fixpoint before this is asked, so
        anything blocked has been removed by now. What remains is advice whose
        own declaration *cannot be decided yet*, because `relates_to` is not a
        dependency and an advice entry can reach its host before the entry it
        declares on has been answered. That is left out: attaching it would mean
        deciding its availability from an answer the team has not given.

        Advice that is never attached and never presented is simply never
        resolved. There is nothing to clean up — it is excluded from the steps
        `_advance` offers and from the estimate, so the run ends without it, and
        that absence is exactly its suppression.
        """
        return tuple(
            i for i in sorted(self._entries)
            if i not in self._resolved_at
            and is_attached_advice(self._entries[i])
            and self._entries[i].get("relates_to") == host_id
            and self._determinable(i)
        )

    def _remove(self, entry_id, because):
        self._resolve(entry_id)
        self._removed[entry_id] = because
        entry = self._entries[entry_id]
        if entry.get("kind") != "advice":
            # Advice is not in the set, so it is not in the set as an
            # inapplicable member either.
            self._inapplicable.append(
                Inapplicable(entry_id, because, entry.get("title"),
                             elicit.origin_of(entry))
            )

    def _pruned_options(self, entry_id):
        """`(selectable keys, ((key, because), ...))` for an entry in hand.

        Plain pairs rather than card records: what the team is shown is
        `elicit`'s to build, and that is where the entry's branches are already
        in hand. This module owes it which keys survived and what removed the
        rest.
        """
        selectable, removed = [], []
        for key, declaration in offers(self._entries[entry_id]):
            because = self._blocker(declaration)
            if because is None:
                selectable.append(key)
            else:
                removed.append((key, because))
        return selectable, removed

    def _sweep(self):
        """Remove everything the answers so far have made inapplicable.

        Removing one entry can determine another, so this runs to a fixpoint.
        It terminates because the graph is acyclic and each pass either removes
        an entry or stops.
        """
        while True:
            for entry_id in self._unresolved():
                if not self._determinable(entry_id):
                    continue

                because = self._blocker(self._entries[entry_id].get("available_when"))
                if because is not None:
                    self._remove(entry_id, because)
                    break

                selectable, removed = self._pruned_options(entry_id)
                if removed and not selectable:
                    # Option-level pruning emptied the entry: there is nothing
                    # left to answer, so it is inapplicable exactly as the
                    # entry-level case is, naming the answer that removed the
                    # last option.
                    last = max((because for _, because in removed), key=self._rank)
                    self._remove(entry_id, last)
                    break
            else:
                return

    def _advance(self):
        """Recompute, then take the next presentable entry in id order.

        Topological order leaves independent entries unordered and something has
        to choose. The entry id decides: a filename would make presentation a
        property of the files rather than of the declarations, and the corpus
        states no sequence of its own.
        """
        self._sweep()
        unresolved = self._unresolved()
        # Attached advice is never a step, so it is neither presentable nor
        # counted in what remains — an estimate that included it would promise
        # screens the team will never be shown.
        steps = [i for i in unresolved if not is_attached_advice(self._entries[i])]
        presentable = [i for i in steps if self._determinable(i)]
        if not presentable:
            self._current = None
            self._attached_now = ()
            return

        entry_id = presentable[0]
        selectable, removed = self._pruned_options(entry_id)
        self._attached_now = self._attached_to(entry_id)
        self._current = elicit.card_for(
            self._entries[entry_id],
            selectable,
            removed,
            [self._entries[i] for i in self._attached_now],
            remaining_estimate=len(steps) - 1,
            given=self._given(),
        )
