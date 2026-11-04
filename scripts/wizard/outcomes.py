"""What evaluation produces, and the vocabulary it produces it in.

An **outcome** is one rule's verdict about one resource in one root. It is data
before it is a report, for the reason a compiled rule is data before it is a
verdict and a card is data before it is a page: *this rule reported X on
resource Y* is a field assertion against an outcome and a string match against
printed text. The report renders these; nothing here renders anything.

**The four causes live here rather than in the component that attributes each.**
The vocabulary is exactly four and closed, and a closed set spread
across the three modules that attribute from it is one nothing can check. Two of
them are compilation's (`rules.py` imports them from here) and two are
evaluation's.

**A resolved failure message is not a stored field.** An outcome carries the
values its rule's placeholders resolved to, and `message_of` renders the
sentence from those and the rule. Storing the rendered string beside the values
it was rendered from would be the restatement this product's shapes refuse
everywhere else — and it would let a report's sentence and its data disagree.
What is required is that the rendering *cannot fail*, which is
`unresolved_in`'s job and is checked before an outcome leaves evaluation.
"""

import re
from dataclasses import dataclass
from typing import Optional, Tuple

# The three verdicts. UNEVALUATED is not a failure and never
# contributes to the exit code; it is the honest answer
# where a verdict would be a guess.
PASS = "PASS"
FAIL = "FAIL"
UNEVALUATED = "UNEVALUATED"
VERDICTS = (PASS, FAIL, UNEVALUATED)

# The closed vocabulary of causes. They differ in who must act:
# estate-side may resolve on its own, product-side waits on a corpus maintainer,
# installation-side on an upgrade, and coverage-side on the team's own pipeline
# today — which is why rendering all four as "unevaluated" leaves a team waiting
# for three of them to fix themselves.
ESTATE_SIDE = "estate-side"
PRODUCT_SIDE = "product-side"
INSTALLATION_SIDE = "installation-side"
COVERAGE_SIDE = "coverage-side"
CAUSES = (ESTATE_SIDE, PRODUCT_SIDE, INSTALLATION_SIDE, COVERAGE_SIDE)

# `{catalog}`, `{workspace}` — the estate placeholders a `failure_message`
# carries. `{adr}` is not among them: it is resolved at compile time, because the compiler knows the ADR number and cannot know the
# estate.
PLACEHOLDER = re.compile(r"{([^{}]+)}")


@dataclass(frozen=True)
class Outcome:
    """One rule's verdict about one resource in one root.

    `root` is the declared root this outcome was reached for, and is present
    even where no resource was matched — a rule that found nothing in `dev`
    found nothing *in dev*. It is `None` only for a rule evaluated over the
    estate that produced no resource, where no one root is the answer.

    `estate_address` is what the platform calls the thing and is what identity
    is derived from; `terraform_address` is how a team finds it in
    their code and is display only. A resource whose naming attribute is not
    known at plan time carries the second and not the first.

    `placeholders` is what the rule's message resolves against, as ordered
    pairs rather than a mapping: two outcomes that resolved the same values
    compare equal only if they resolved them the same way, and a mapping would
    compare equal however it was built.

    `absent` marks a deviation found by absence, which is
    what selects the rule's `absence_message`. It is a field rather than read off
    the missing Terraform address, because that address is display only and
    nothing should come to depend on it.
    """

    rule: object
    verdict: str
    root: Optional[str] = None
    estate_address: Optional[str] = None
    terraform_address: Optional[str] = None
    cause: Optional[str] = None
    reason: Optional[str] = None
    placeholders: Tuple[Tuple[str, str], ...] = ()
    absent: bool = False


def passed(rule, resource, estate_address):
    """`rule` holds on `resource`."""
    return Outcome(
        rule=rule,
        verdict=PASS,
        root=resource.root,
        estate_address=estate_address,
        terraform_address=resource.address,
    )


def failed(rule, resource, estate_address, /, **placeholders):
    """`rule` does not hold on `resource` — a deviation, once the report carries it.

    The evaluator supplies the placeholder values because it is the evaluator
    that read the resource; whether they are enough for the rule's message is
    checked once, in `evaluation.py`, rather than in each evaluator.

    The first three are positional-only, because a rule's placeholders are the
    corpus maintainer's words and one of them is `{resource}` — a keyword
    argument of that name would collide with this function's own, and the
    collision would be a `TypeError` in front of a team rather than a report.
    """
    return Outcome(
        rule=rule,
        verdict=FAIL,
        root=resource.root,
        estate_address=estate_address,
        terraform_address=resource.address,
        placeholders=tuple(sorted(placeholders.items())),
    )


def missing(rule, root, estate_address, /, **placeholders):
    """A deviation the rule found by *absence*.

    The target state names something the estate must declare and the estate
    declares none of it. It is a deviation like any other — all four identity
    components are present, so an exception matches it as it matches any other
    — and it carries no Terraform address, because there is no block to point a
    team at. That field was always display-only.

    The root comes from the estate declaration rather than from a resource,
    since there is no resource: it is where the declaration says the missing
    thing would have been. A rule that cannot place it reports a non-result
    instead of attributing the deviation to a root that did not earn it.
    """
    return Outcome(
        rule=rule,
        verdict=FAIL,
        root=root,
        estate_address=estate_address,
        placeholders=tuple(sorted(placeholders.items())),
        absent=True,
    )


def unevaluable(rule, cause, reason, root=None):
    """No verdict, and the class and sentence that say why.

    Both are required: a cause without a reason is unactionable, and a reason
    without a cause makes the reader classify it themselves.
    """
    return Outcome(rule=rule, verdict=UNEVALUATED, root=root, cause=cause, reason=reason)


def unevaluable_on(rule, resource, reason, estate_address=None, cause=ESTATE_SIDE):
    """No verdict on a resource that was matched and could not be read.

    Estate-side by default because that is the class this shape describes — a
    resource the estate declares and this rule cannot read. It is passed
    explicitly rather than inferred from anything absent.
    """
    return Outcome(
        rule=rule,
        verdict=UNEVALUATED,
        root=resource.root,
        estate_address=estate_address,
        terraform_address=resource.address,
        cause=cause,
        reason=reason,
    )


def unevaluable_as_disclosed(rule, root, otherwise, resource=None, estate_address=None):
    """The estate-side non-result the rule anticipated, in the rule's own words.

    Where the rule disclosed `unevaluable_when`, the team
    reads back the sentence they were shown at elicitation rather than a
    paraphrase of it. Quoted in exactly one place, so no evaluator can paraphrase
    it by accident; `otherwise` is the evaluator's own sentence, for a rule that
    disclosed nothing.

    A disclosed non-result may be about one resource rather than about the whole
    reader — a securable whose attribute the plan does not carry is the case the
    rule disclosed, found on a resource that has a name and an address. Passing
    `resource` keeps that outcome pointing at it, and keeps the sentence quoted
    here rather than in a second place that could paraphrase it.
    """
    reason = rule.unevaluable_when or otherwise
    if resource is not None:
        return unevaluable_on(rule, resource, reason=reason, estate_address=estate_address)
    return unevaluable(rule, ESTATE_SIDE, reason, root=root)


def unresolved_in(template, values):
    """The placeholder names `template` carries that `values` cannot fill.

    A missing value, `None` and the empty string are all unresolved: a report
    reading `None is OPEN` sends a team looking for a resource called `None`,
    and one reading ` is OPEN` sends them nowhere at all.
    """
    if not isinstance(template, str):
        return ()
    return tuple(
        name for name in PLACEHOLDER.findall(template)
        if values.get(name) is None or str(values[name]) == ""
    )


def template_of(outcome):
    """The message `outcome` renders: the rule's `absence_message` for a
    deviation found by absence, where the rule carries one, and its
    `failure_message` otherwise.

    A set written before `absence_message` existed carries only the second, and
    reads as it always did. One function chooses, so the sentence a report
    renders and the sentence evaluation checked cannot be two different ones.
    """
    if outcome.absent and outcome.rule.absence_message:
        return outcome.rule.absence_message
    return outcome.rule.failure_message


def message_of(outcome):
    """The rule's message, resolved — or `None` where there is none.

    Only a deviation renders one. A PASS has nothing to say and an UNEVALUATED
    says it in its `reason`, which is prose the rule or the evaluator wrote
    rather than a template.
    """
    if outcome.verdict != FAIL:
        return None
    values = dict(outcome.placeholders)
    return PLACEHOLDER.sub(lambda m: str(values[m.group(1)]), template_of(outcome))


def with_message_resolved(outcome):
    """A deviation whose message cannot be resolved is a non-result instead.

    A report reading `None is OPEN — every workspace can reach it` sends a team
    looking for a resource called `None`. If an evaluator cannot supply a
    placeholder its own rule's message names, that is a defect in this product
    and takes the same path an evaluator that raised takes.
    Here rather than in either dialect's evaluation, so both make the check the
    same way.
    """
    if outcome.verdict != FAIL:
        return outcome
    missing = unresolved_in(template_of(outcome), dict(outcome.placeholders))
    if not missing:
        return outcome
    return unevaluable(
        outcome.rule, INSTALLATION_SIDE,
        f"the evaluator {outcome.rule.evaluator!r} resolved no value for "
        f"{quoted(missing)} in this rule's failure message; that is a defect in this "
        "product and resolves by upgrading",
        root=outcome.root)


def quoted(names):
    """`'a'`, `'a' and 'b'`, `'a', 'b' and 'c'` — a list a sentence can carry."""
    names = [repr(name) for name in names]
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"
