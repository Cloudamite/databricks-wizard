"""Compiled rules and an estate become outcomes, in the account.

Each rule is evaluated once over the whole estate, and each outcome carries the
place it is filed in (`account`, `workspace:<name>`, `metastore:<name>`): an
account has no roots to evaluate a rule per root over, and every declared
workspace is in the snapshot, since the reader writes none otherwise.

A rule bound to another substrate is not considered at all: it has no outcome, so nothing downstream reports it. It is left out here,
after compilation, so `compile_rules` behaves as it does for the analyzer.

As in the Terraform dialect's evaluation, a rule compiled with a cause is not
evaluated, an evaluator that raises or returns nothing is a defect contained to
its own rule, and a deviation whose message cannot be resolved is a non-result.
"""

from wizard import outcomes
from wizard.live import DECLINED, LIVE
from wizard.outcomes import INSTALLATION_SIDE


def evaluate(rules, estate):
    """Every outcome of every compiled rule the audit considers: by rule, then
    by place, then by estate address."""
    found = []
    for rule in rules:
        if considered(rule):
            found.extend(_outcomes_of(rule, estate))
    return tuple(found)


def considered(rule):
    """Whether the audit asks `rule` at all.

    Not when it declares `substrates`, which never include `live`: the closed
    vocabulary names IaC layers, and no rule is bound to the account. Nor when
    it names a handle the live registry declines, which a set written before
    PRE-002 declared `substrates` carries without it.
    """
    return not rule.substrates and rule.evaluator not in DECLINED


def _outcomes_of(rule, estate):
    if rule.cause:
        return (outcomes.unevaluable(rule, rule.cause, rule.reason),)
    try:
        produced = tuple(LIVE[rule.evaluator](rule, estate))
    except Exception as exc:  # noqa: BLE001 - containment is the point
        return (outcomes.unevaluable(
            rule, INSTALLATION_SIDE,
            f"the evaluator {rule.evaluator!r} failed on this account ({type(exc).__name__}); "
            "that is a defect in this product and resolves by upgrading"),)
    if not produced:
        return (outcomes.unevaluable(
            rule, INSTALLATION_SIDE,
            f"the evaluator {rule.evaluator!r} returned no outcome, and its contract is at "
            "least one; that is a defect in this product and resolves by upgrading"),)
    resolved = [outcomes.with_message_resolved(outcome) for outcome in produced]
    return sorted(resolved, key=lambda o: (o.root or "", o.estate_address or ""))
