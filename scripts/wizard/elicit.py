"""A corpus entry, plus what the answers so far left of it, becomes a card.

This is the elicitor half of the seam between eliciting and rendering: it decides *what the team must see* and stops there. Nothing here
formats anything, and nothing here knows a terminal exists.

**A prescription discloses in a fixed order** — target state, then the
justification, then the evidence, then what will be checked, then that the entry
cannot be amended, and only then the choice. That order is required, and it is
carried in `card.disclosure` rather than left to a renderer, because a
requirement no data can express is a requirement nothing can check.

**A decision discloses in its own order** — the question, the vendor's position,
the states on offer, what an earlier answer took away, and only then the choice.
That order is the same kind of claim about sequence and is carried the same
way. A state's caveat is not a part of its own: a state
carries its own enforceability and its own condition on `check`, so the caveat
is disclosed by the state, and before the answer because `options` precedes
`responses`.

**Advice discloses last, before the responses.** It is guidance nothing
downstream will check, so it belongs beside the choice rather than inside it,
and the states — whose caveats do bear on the choice — come first. Advice with
no entry to sit beside is a screen of its own, and then it is all the screen
has.

**A part the entry does not carry is absent from the disclosure**, not present
and empty. A renderer walking the sequence then draws no blank heading, and a
test can tell "the entry has no justification" from "the justification was
dropped".
"""

from wizard.card import (
    CHOSEN,
    PRESCRIBED,
    Advice,
    Card,
    Check,
    NotOffered,
    Option,
    Parameter,
    Vendor,
)
from wizard.corpus import branches, is_graded

# What the team may do here, which is what a renderer turns into key hints.
# A prescription has exactly two responses and there is no third: amendment left
# scope, and the disclosure must say so up front.
PRESCRIPTION_RESPONSES = ("accept", "opt-out")
DECISION_RESPONSES = ("choose",)

# Nothing authored in this version can be amended. Carried as a fact so the
# sentence itself stays with the renderer rather than the engine.
AMENDABLE = False


def vendor_of(entry):
    block = entry.get("vendor")
    if not isinstance(block, dict):
        return None
    return Vendor(
        strength=block.get("strength"),
        quote=block.get("quote"),
        source=block.get("source"),
        checked=block.get("checked"),
    )


def check_of(block):
    """A rule as the team is shown it, or `None` where there is no rule.

    `unevaluable_when` is optional in the corpus and `None` here when absent —
    never invented, and never dropped when it is declared.
    """
    if not isinstance(block, dict):
        return None
    clouds = block.get("clouds")
    substrates = block.get("substrates")
    return Check(
        summary=block.get("summary"),
        failure_message=block.get("failure_message"),
        evaluator=block.get("evaluator"),
        enforceability=block.get("enforceability"),
        scope=block.get("scope"),
        unevaluable_when=block.get("unevaluable_when"),
        absence_message=block.get("absence_message"),
        uses=tuple(block.get("uses") or ()),
        clouds=tuple(clouds) if isinstance(clouds, list) else (),
        substrates=tuple(substrates) if isinstance(substrates, list) else None,
    )


def branch_by_key(entry):
    return {
        b.get("key"): b for b in branches(entry) or [] if isinstance(b, dict)
    }


def option_of(branch, given=None):
    return Option(
        key=branch.get("key"),
        label=branch.get("label"),
        cost=branch.get("cost"),
        check=check_of(branch.get("rule")),
        vendor_default=bool(branch.get("vendor_default")),
        product_preferred=bool(branch.get("product_preferred")),
        parameters=parameters_of(branch, given),
        unconstrained=branch.get("unconstrained"),
    )


def parameters_of(branch, given=None):
    """What this state cannot be measured without, as the card carries it.

    The corpus is read here and nowhere downstream: the walk refuses an answer
    against what the card declared, and the write records what the answer
    supplied, so a state's declarations are interpreted once.

    `given` is the walk's `{name: (values, because)}` for every parameter an
    earlier answer supplied. A declaration it names is carried with those
    values, so a front end shows them rather than asking.
    """
    given = given or {}
    found = []
    for declaration in branch.get("parameters") or []:
        if not isinstance(declaration, dict):
            continue
        name = declaration.get("name")
        values, because = given.get(name, ((), None))
        found.append(Parameter(name=name, question=declaration.get("question"),
                               given=values, given_by=because))
    return tuple(found)


def advice_of(entry):
    """An advice entry as the team is shown it.

    The citation comes through `vendor_of` like any other entry's, but it lands
    on the record rather than on the card: attached advice sits beside a host
    with a citation of its own, and the two must not be confusable.
    """
    return Advice(
        entry=entry.get("id"),
        statement=entry.get("statement"),
        vendor=vendor_of(entry),
        no_rule_because=entry.get("no_rule_because"),
        fingerprint_reviewed=entry.get("fingerprint_reviewed"),
        relates_to=entry.get("relates_to"),
    )


def origin_of(entry):
    """Prescribed or chosen — and neither for advice, which never enters the
    set at all."""
    kind = entry.get("kind")
    if kind == "prescription":
        return PRESCRIBED
    if kind == "decision":
        return CHOSEN
    return None


def responses_for(entry):
    kind = entry.get("kind")
    if kind == "prescription":
        return PRESCRIPTION_RESPONSES
    if kind == "decision":
        return DECISION_RESPONSES
    return ()  # advice is shown, never asked


def states_on_offer(entry, selectable, given=None):
    """The states the team chooses among, pruning included.

    A single-state prescription has none: `accepted` and `declined` are
    dispositions, not satisfying states, and presenting them as a list to pick
    from would make accepting look like a choice between two positions the
    product holds.
    """
    if entry.get("kind") == "prescription" and not is_graded(entry):
        return ()
    return tuple(
        option_of(branch, given)
        for branch in branches(entry) or []
        if isinstance(branch, dict) and branch.get("key") in selectable
    )


def not_offered_for(entry, removed):
    """The states an earlier answer took away, each with its own record.

    `removed` is the walk's `((key, because), ...)`. The record carries the
    option itself, not just its key: a renderer holding `managed` can print
    `managed`, but it cannot tell the team which door closed, and showing the
    door is the whole reason a pruned option stays on the card.
    """
    declared = branch_by_key(entry)
    return tuple(
        NotOffered(
            key=key,
            because=because,
            option=option_of(declared[key]) if key in declared else None,
        )
        for key, because in removed
    )


# `not_offered` sits in both orders and in the same place, after the states on
# offer: options are rendered under one contract whatever the kind, and a
# graded prescription can have an alternative pruned exactly as a decision can.
#
# There is no `caveats` part. A state's enforceability and the condition under
# which its rule cannot be measured are disclosed by the state itself, on its
# own `check`, which is where a renderer shows them.
# A part collecting them would put one fact in two places, and a renderer handed
# several options' conditions with no field to transcribe composes the sentence
# joining them — which is the defect this layout exists to prevent. Disclosure before
# the answer survives as ordering: `options` precedes `responses` in both orders
# below, so the caveat before the answer is carried by position rather than
# by a part.
PRESCRIPTION_ORDER = (
    "target_state", "why", "vendor", "check", "write_once",
    "options", "parameters", "not_offered", "advice", "responses",
)
DECISION_ORDER = (
    "question", "vendor", "options", "not_offered", "advice", "responses",
)
# An advice card is its advice and nothing else: the statement, the citation and
# the recorded reason for having no rule all live on the record, so a renderer
# walking one part draws the whole screen.
ADVICE_ORDER = ("advice",)

ORDERS = {
    "prescription": PRESCRIPTION_ORDER,
    "decision": DECISION_ORDER,
    "advice": ADVICE_ORDER,
}


def disclosure_for(entry, card_parts):
    """The parts this card has, in the order they are disclosed."""
    order = ORDERS.get(entry.get("kind"))
    if order is None:
        return ()
    return tuple(part for part in order if part in card_parts)


def card_for(entry, selectable, removed, attached, remaining_estimate, given=None):
    """The card for one entry, given the keys still selectable on it.

    `removed` is the walk's `((key, because), ...)` for the keys an earlier
    answer took away, `attached` the advice entries it resolved as belonging
    beside this one, and `given` the parameters earlier answers supplied.
    """
    kind = entry.get("kind")
    is_prescription = kind == "prescription"
    is_decision = kind == "decision"
    is_advice = kind == "advice"

    # An advice card's citation is on its record, not on the card: one fact with
    # two homes is a renderer that shows the source twice.
    vendor = None if is_advice else vendor_of(entry)
    check = check_of(entry.get("rule"))
    options = states_on_offer(entry, selectable, given)
    # A single-state prescription has no options to declare them on, so what it
    # cannot be measured without is the entry's own, asked when it is accepted.
    parameters = (parameters_of(entry, given)
                  if is_prescription and not is_graded(entry) else ())
    not_offered = not_offered_for(entry, removed)
    advice = (advice_of(entry),) if is_advice else tuple(
        advice_of(a) for a in attached
    )
    responses = responses_for(entry)

    present = {"responses"} if responses else set()
    if is_prescription:
        present.add("write_once")
        if entry.get("decision"):
            present.add("target_state")
        # `why` is required of every prescription by the validity table and the
        # run validates before it presents anything, so a card is never built
        # from an entry without one. Guarding it anyway would be a branch no
        # valid corpus can take.
        present.add("why")
    if is_decision and entry.get("question"):
        present.add("question")
    if vendor is not None:
        present.add("vendor")
    if check is not None:
        present.add("check")
    if options:
        present.add("options")
    if parameters:
        present.add("parameters")
    if not_offered:
        present.add("not_offered")
    if advice:
        present.add("advice")

    return Card(
        kind=kind,
        corpus_entry=entry.get("id"),
        title=entry.get("title"),
        origin=origin_of(entry),
        question=entry.get("question") if is_decision else None,
        target_state=entry.get("decision") if is_prescription else None,
        why=entry.get("why") if is_prescription else None,
        vendor=vendor,
        check=check,
        amendable=AMENDABLE,
        options=options,
        parameters=parameters,
        not_offered=not_offered,
        advice=advice,
        answer_keys=tuple(selectable),
        responses=responses,
        disclosure=disclosure_for(entry, present),
        remaining_estimate=remaining_estimate,
    )
