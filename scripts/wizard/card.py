"""What the team is shown, as data.

The elicitor produces a card; a renderer turns it into text. Nothing between
them knows about the other. Almost every presentation requirement for a
prescription or a decision is of the form *the team is shown X*, and against a
card those are field assertions rather than string matching — a suite that breaks when someone
rewords a label is one that gets deleted.

**Sequence is a field too.** The disclosure must open with the target state,
and the write-once notice must come before the choice. Both are claims about order, so the card carries `disclosure`: the parts
it has, in the order they are disclosed. A renderer walks that rather than
hardcoding a layout, and the requirements stay field assertions.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

# `report` is the closing card; the other three are corpus entries.
KINDS = ("prescription", "decision", "advice", "report")

# An entry the product adopted on the team's behalf, against one they were asked
# about. Carried as text so that a renderer cannot lose the distinction and
# colour can only ever be redundant emphasis.
PRESCRIBED = "prescribed"
CHOSEN = "chosen"


@dataclass(frozen=True)
class Vendor:
    """The vendor's position, as the entry states it.

    Shown verbatim and never paraphrased, with the date the citation was last
    checked: whether the vendor still says what it said is what `checked`
    records, and a team reading a two-year-old date knows what to do with it.
    `strength` may be `silent`, which is a position and is shown as one.
    """

    strength: str
    quote: str
    source: str
    checked: str


@dataclass(frozen=True)
class Check:
    """What will be checked in the estate, and whether it can be.

    `unevaluable_when` is disclosed at choosing time rather than discovered at
    gate time: a team that learns an entry is weakly enforceable from a silent
    UNEVALUATED three weeks later concludes the tool is broken.

    `clouds` names every cloud this check has a fingerprint for, and has no
    default: a rule that does not say which clouds it covers is claiming all of
    them. `substrates` is the same claim one axis up and *does* default — absent
    means every substrate, which is the ordinary case, because a target state is
    a statement about a team's architecture rather than about the tool that
    declares it. Only a check whose subject is the IaC layer itself names one.

    `scope` says what the rule is evaluated over: `root` against each supplied
    plan on its own, `estate` once across them all. It rides on the card for two
    reasons. The write projects the set's rule from this dataclass, so a field
    absent here never reaches the ADR set the analyzer reads; and an `estate`
    rule needs a plan for every declared root, which is a condition on the team's
    pipeline that belongs with `unevaluable_when` at choosing time rather than
    in a non-result weeks later.

    Both ride on the card because the team is shown the check before they
    answer, and the write copies what was disclosed. Which variant an estate
    gets is the analyzer's to select, not the wizard's to ask.

    `uses` names the recorded parameters this rule is measured against, by name
    alone: a name is one fact across the set, and whichever ADR recorded it is
    the one compilation reads. It rides
    here for the first of those two reasons: the write projects the set's rule
    from this dataclass, so a rule whose `uses` stopped at the card would compile
    against nothing and report a product-side non-result on every estate.

    `absence_message` is the sentence a deviation found by absence renders,
    where the rule can find one. It rides here for the
    first of those two reasons as well: a field the card dropped would never
    reach the set, and every absence would read the per-resource sentence.
    """

    summary: str
    failure_message: str
    evaluator: str
    enforceability: str
    scope: str
    unevaluable_when: Optional[str] = None
    absence_message: Optional[str] = None
    clouds: tuple = ()
    substrates: Optional[tuple] = None
    uses: tuple = ()


@dataclass(frozen=True)
class Parameter:
    """A name the team is asked for, because a rule cannot measure without it.

    An option records which state a team holds; some states are not checkable
    without the names the team gave the things they are about — which
    environments exist, which layers they use. The question is the corpus
    maintainer's words, shown as written, for the reason a vendor quote is.

    It carries nothing a renderer could derive. There is no type, because every
    value is a sequence of names; no default, because a default would be the
    product answering for the team; and no example, because an example beside a
    question is a suggestion and a suggested environment list is one teams would
    accept unread.

    `given` is what an earlier answer in the run already supplied under this
    name, in the order it was given, and `given_by` the answer that supplied it.
    A given parameter is shown and never asked: a name is one fact across the set, and a second ask would be
    a second record that could disagree with the first. Both are empty on a
    declaration no earlier answer has reached.
    """

    name: str
    question: str
    given: Tuple[str, ...] = ()
    given_by: Optional["Because"] = None


@dataclass(frozen=True)
class Option:
    """One state on offer — a decision's option, or an alternative satisfying
    state of a graded prescription.

    Each carries the rule it compiles to. A prescription whose alternatives
    shared one rule would record one target state and tolerate another, which is
    what giving each alternative its own rule exists to prevent.

    `parameters` are the names this state cannot be measured without, and they
    ride on the option rather than on the card because they belong to the state
    that needs them — a team choosing a different option is never asked.
    Most options declare none.
    """

    key: str
    label: str
    cost: Optional[str]
    check: Optional[Check]
    vendor_default: bool = False
    # What this product would choose where the vendor declines to. A separate
    # field from `vendor_default` because they are separate claims with separate
    # weights, and a reader must be able to tell *the vendor recommends this*
    # from *we recommend this*. Neither decides anything.
    product_preferred: bool = False
    parameters: Tuple[Parameter, ...] = ()
    # What an option that enforces nothing leaves open, shown where `check`
    # would be. Set exactly when `check` is not: the team
    # reads *checks nothing* before it chooses, not after.
    unconstrained: Optional[str] = None


@dataclass(frozen=True)
class Advice:
    """Guidance nobody has yet found a way to check.

    It carries its **own** citation rather than borrowing the card's. Attached
    advice sits beside a host entry whose `vendor` is the host's, and one
    vendor's words shown under another entry's source is worse than showing no
    source at all. On an advice card of its own the card's `vendor` is `None`
    for the same reason: one fact, one home.

    `no_rule_because` travels with it so advice reads as guidance awaiting a
    fingerprint rather than guidance the product declined to enforce — the
    moment a fingerprint is found the entry becomes a prescription, and that is
    a maintainer's act on the corpus rather than anything the wizard does.

    `fingerprint_reviewed` is carried and nothing is derived from it. Comparing
    it against today would make the same corpus and the same answers produce a
    different run on a different morning.

    `relates_to` is `None` when the advice names no entry. The closing report
    repeats those in full; the run records which is which
    and decides nothing.
    """

    entry: str
    statement: str
    vendor: Optional[Vendor] = None
    no_rule_because: Optional[str] = None
    fingerprint_reviewed: Optional[str] = None
    relates_to: Optional[str] = None


@dataclass(frozen=True)
class Because:
    """The answer responsible for something on a later card — an option it
    removed, or a parameter it already gave.

    `answer` is `None` when `entry` was itself never settled — a cascade. The
    record then names the entry immediately above in the chain, whose own record
    names the one above that, ending at an entry that names a real answer.
    """

    entry: str
    answer: Optional[str] = None


@dataclass(frozen=True)
class NotOffered:
    """An option the team cannot choose, and the answer that removed it.

    It is still carried on the card: hiding a pruned option makes the wizard
    look arbitrary, and showing it is how a team learns the platform rather than
    merely obeying the tool. The renderer shows it; the walk supplies its
    provenance.

    `option` is the removed state's own record, so a renderer can name the door
    that closed rather than print a bare key. It is `None` only for a key that
    names no state — nothing prunable is shaped that way today, and inventing a
    label for one would be worse than saying there is none.
    """

    key: str
    because: Because
    option: Optional["Option"] = None


@dataclass(frozen=True)
class Card:
    """One screen's worth of content.

    `corpus_entry` is the entry's stable corpus id and **never** an ADR number.
    Numbers are assigned when the set is written, and a run that is
    still eliciting has not written anything — so a card cannot carry one
    without inventing it.

    `answer_keys` is what the run accepts as an answer; `options` is what the
    team is shown to choose among. The two differ: a prescription's `declined`
    is an answer but not a state on offer, and a single-state prescription has
    two answers and nothing to select between.

    `question` is to a decision what `target_state` is to a prescription — what
    the screen is about, and the part its disclosure opens with. Exactly one of
    the two is ever set, because an entry is one kind.

    `advice` is what this screen says without asserting: the entry itself on an
    advice card, and whatever the corpus attached to the entry on any other.
    `vendor` is `None` on an advice card, because the citation belongs to the
    record rather than to the screen.

    `title` is the screen's heading and deliberately **not** a member of
    `disclosure`: the disclosure orders name the parts a renderer walks, and a
    heading is not one of them. It is carried because the written record
    identifies an entry by it, and the writer reads no
    corpus entry — so if the card does not carry it, nothing does.

    `remaining_estimate` is an estimate and is named as one: later answers can
    prune, so the number of entries still to come may fall by more than one
    between cards. No field states a fixed total, because there is no honest
    total to state.
    """

    kind: str
    corpus_entry: str
    title: Optional[str] = None
    origin: Optional[str] = None
    question: Optional[str] = None
    target_state: Optional[str] = None
    why: Optional[str] = None
    vendor: Optional[Vendor] = None
    check: Optional[Check] = None
    amendable: bool = False
    options: Tuple[Option, ...] = ()
    # A single-state prescription's own parameters, asked when it is accepted:
    # it has no option to declare them on.
    parameters: Tuple[Parameter, ...] = ()
    not_offered: Tuple[NotOffered, ...] = ()
    advice: Tuple[Advice, ...] = ()
    answer_keys: Tuple[str, ...] = ()
    responses: Tuple[str, ...] = ()
    disclosure: Tuple[str, ...] = ()
    remaining_estimate: int = 0


# --- The closing card -----------------------------------------------------


@dataclass(frozen=True)
class Declined:
    """One entry the team opted out of, and the reason they gave.

    The rationale is carried whole and is never summarised. Declining a
    prescription costs a written reason and costs a line here as well — a set
    with many declined entries should be uncomfortable to read, which a
    truncated rationale would quietly undo.
    """

    id: str
    title: str
    rationale: str


@dataclass(frozen=True)
class LeftOpen:
    """One entry answered at an option that enforces nothing, with the corpus's sentence on what that answer leaves open.

    Named for the same reason a declined entry is: it compiles to no rule, and a
    team that does not read that here would assume something checks it.
    """

    id: str
    title: str
    unconstrained: str


@dataclass(frozen=True)
class NotApplicable:
    """One entry an earlier answer removed, which the team never saw.

    `because` is the ADR number of the entry that removed it — the immediate
    one in the chain — and `because_title` is that entry's title
    as the set records it. Both are resolved inside the set: the record names a
    number, and a report that reached for the corpus to render the title would
    be reading something the artefact does not contain.

    `because_title` is `None` when `because` is an ADR of the set this one builds
    on, named with its module: its title is in that set, not this one.
    """

    id: str
    title: str
    because: str
    because_title: Optional[str]


@dataclass(frozen=True)
class Report:
    """What the team is told once the set has been written.

    Every field but `unattached_advice` is read back off the record. That is
    what stops the report becoming a second,
    disagreeing account of the run: the team and the analyzer read the same
    bytes. Advice is the exception because it is kept out of
    the set entirely — it yields no rule, so it never becomes an ADR — and the
    report is the only place an unattached one can appear at all.

    `chosen` and `prescribed` partition the entries and are description, not
    behaviour. The enforcement invariant forbids a consumer branching on how an
    entry arrived; it does not forbid describing the set to the person who just
    authored it, which is what a human reading their own decisions needs.

    Every distinction is a string or a structural difference, so colour can only
    ever be redundant emphasis, and the whole card survives
    `dataclasses.asdict` — which is how it reaches the front end.
    """

    entries: int
    paths: Tuple[str, ...]
    chosen: int
    prescribed: int
    declined: Tuple[Declined, ...]
    left_open: Tuple[LeftOpen, ...]
    inapplicable: Tuple[NotApplicable, ...]
    unattached_advice: Tuple[Advice, ...]
    no_rule_notice: str
    # The ADRs an append found and wrote again unchanged. Every other count and
    # list covers only what the append added.
    left_as_recorded: int = 0
    kind: str = "report"
