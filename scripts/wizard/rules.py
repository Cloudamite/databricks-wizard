"""An ADR set and a cloud set become compiled rules.

A compiled rule is **data
before it is a verdict** — the analogue of elicitation's card, and for the same
reason: *this rule reported X on resource Y* is a field assertion against an
outcome and a string match against printed text.

**Membership is a function of the set alone.** Every entry carrying a `rule`
compiles to at least one `Rule` and every entry without one compiles to nothing,
whatever the clouds. What the cloud decides is which fingerprint each rule gets,
and — when it selects none — whether the rule can produce a verdict at all. If
cloud membership changed which rules existed, a team's rule count would move
when their estate grew a second cloud, and a baseline taken before would not line
up with one taken after. That is the ratchet's basis.

**Nothing is dropped.** A rule with no fingerprint for the estate's clouds and a
rule naming an evaluator this build does not implement both compile, carrying the
cause that says why they can only be UNEVALUATED. A
cause is assigned once and never overwritten, so what is attributed here is what
the report renders.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from wizard import evaluators
from wizard.adr_set import adr_number
# The two causes compilation can attribute, of the closed
# vocabulary of four. `estate-side` and `coverage-side` are evaluation's, and
# neither is reachable from here. The vocabulary lives in one module rather than
# beside each component that attributes from it, because a closed set spread
# across three files is one nothing can check.
from wizard.outcomes import INSTALLATION_SIDE, PRODUCT_SIDE

@dataclass(frozen=True)
class Rule:
    """One compiled fingerprint of one ADR.

    `parameters` are the names the set recorded that this rule is measured
    against: ordered pairs rather than a mapping, for the reason an
    outcome's placeholders are — two rules that resolved the same names resolved
    them in the same order, and the order is what says which environment is
    production. Empty for the rules that read none, which is most of them.

    `clouds` is what this fingerprint covers — the intersection of the rule's
    claim with the estate, not the claim — and is empty exactly when the rule
    covers none of them, which is the case `cause` then explains. It is also
    empty when the rule declares no dialect for this estate's substrate, which
    is the coarser version of the same thing.

    `substrates` is the rule's own claim, as the set records it, or None where
    it declares none. Compilation has already acted on it; the audit reads it
    to leave out a rule bound to another substrate.
    """

    adr: str
    evaluator: str
    scope: str
    clouds: Tuple[str, ...]
    summary: str
    failure_message: str
    enforceability: str
    unevaluable_when: Optional[str] = None
    absence_message: Optional[str] = None
    parameters: Tuple[Tuple[str, Tuple[str, ...]], ...] = ()
    cause: Optional[str] = None
    reason: Optional[str] = None
    substrates: Optional[Tuple[str, ...]] = None


def _recorded_parameters(document):
    """Every parameter the set recorded, keyed by its name.

    By name alone, because that is what a rule's `uses` names: a name is one
    fact across the set, recorded by whichever ADR's answer first needed it,
    and the set's validity table refuses a second record of it.
    """
    recorded = {}
    for entry in document.get("adrs") or []:
        if isinstance(entry, dict) and isinstance(entry.get("parameters"), dict):
            recorded.update(entry["parameters"])
    return recorded


def _resolve_uses(rule, recorded):
    """`(parameters, missing)` — what this rule reads, and what nothing recorded."""
    resolved, missing = [], []
    for name in rule.get("uses") or []:
        if not isinstance(name, str):
            missing.append("a declaration that names nothing")
            continue
        values = recorded.get(name)
        if not isinstance(values, list) or not values:
            missing.append(repr(name))
            continue
        resolved.append((name, tuple(values)))
    return tuple(resolved), tuple(missing)


def compile_rules(document, clouds, substrate, answers=evaluators.implements):
    """The rules `document` compiles to on an estate running `clouds`,
    written in `substrate`.

    A pure function of its arguments: no corpus is opened, no plan is read
    here — the clouds and the substrate arrive already determined — and no
    network request is made.

    `answers` says whether a handle has an answer in the dialect measuring this
    substrate: the Terraform registry by default, the audit's own for `live`.
    A handle it does not answer is installation-side.
    """
    recorded = _recorded_parameters(document)
    compiled = []
    for entry in sorted(_carrying_a_rule(document), key=adr_number):
        compiled.extend(_compile(entry, tuple(clouds), substrate, recorded, answers))
    return tuple(compiled)


def _carrying_a_rule(document):
    """Every entry with a `rule` block, and no other test.

    Neither `origin` nor `state` is read. An entry recording `state: declined`
    that nonetheless carries a rule compiles — no valid set holds one, because
    the set's validity gate rejects it first, and that is why the enforcement
    invariant is asserted at this boundary rather than through the command.
    """
    entries = document.get("adrs")
    if not isinstance(entries, list):
        return []
    return [
        entry for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("rule"), dict)
    ]


def _compile(entry, estate_clouds, substrate, recorded=None, answers=evaluators.implements):
    rule = entry["rule"]
    adr = entry.get("id")
    parameters, missing = _resolve_uses(rule, recorded or {})

    if missing:
        # Product-side, like a fingerprint nobody authored, and for the same
        # reason: no upgrade and nothing the team does to their estate supplies
        # a name the corpus asked for and no entry recorded. It outranks the
        # cloud and evaluator cases because a rule with no values to measure
        # against cannot be measured on any cloud by any build.
        return (_rule(entry, rule, (), PRODUCT_SIDE,
                      f"this rule is measured against {_listed(missing)}, which no entry in "
                      "this set recorded; the corpus that asked for it is what has to change",
                      parameters),)

    # The substrate axis, checked before the cloud one because it is the coarser
    # claim: a rule with no dialect for this substrate has no fingerprint on any
    # of its clouds. `substrates` absent means *every* substrate, which is the
    # ordinary case — only an entry whose subject is the IaC layer itself names
    # one.
    declared = rule.get("substrates")
    if declared and substrate not in declared:
        return (_rule(entry, rule, (), PRODUCT_SIDE, _no_dialect(adr, substrate, declared),
                      parameters),)

    matching = tuple(c for c in estate_clouds if c in (rule.get("clouds") or ()))

    if not matching:
        # Product-side, and it outranks installation-side where both apply.
        # Nothing this build could install supplies a fingerprint nobody has
        # authored, so upgrading would not help; the team is told what has to
        # happen first, and the evaluator gap surfaces once the rule claims
        # their cloud.
        return (_rule(entry, rule, (), PRODUCT_SIDE, _no_fingerprint(adr, estate_clouds),
                      parameters),)

    cause, reason = (None, None)
    if not answers(rule.get("evaluator")):
        cause = INSTALLATION_SIDE
        reason = (
            f"this version does not implement the evaluator "
            f"{rule.get('evaluator')!r}; it resolves by upgrading"
        )

    # One compiled rule per entry, covering every matching cloud. A rule states
    # its target state at platform level and names no resource type, so there is
    # nothing left for a cloud to vary: which resource type carries the
    # fingerprint on which cloud is the evaluator's, and it is handed the clouds
    # it covers. `matching` is in the cloud table's order, so this is stable
    # without depending on dictionary iteration.
    return (_rule(entry, rule, matching, cause, reason, parameters),)


def _listed(names):
    """`'a'`, `'a' and 'b'` — a list a sentence can carry."""
    names = list(names)
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"


def _rule(entry, rule, clouds, cause, reason, parameters=()):
    adr = entry.get("id")
    resolved = rule.get("failure_message")
    return Rule(
        adr=adr,
        evaluator=rule.get("evaluator"),
        scope=rule.get("scope"),
        clouds=clouds,
        summary=rule.get("summary"),
        # `{adr}` is resolved here and estate placeholders are not: a compiler
        # that guessed at `{catalog}` would be inventing an estate it has not
        # read. It is the entry's `id` that resolves it, never its
        # `corpus_entry` — an ADR number escapes into failure messages and
        # runbooks, and a corpus id does not.
        failure_message=_resolve(resolved, adr),
        enforceability=rule.get("enforceability"),
        absence_message=_resolve(rule.get("absence_message"), adr),
        unevaluable_when=rule.get("unevaluable_when"),
        parameters=parameters,
        cause=cause,
        reason=reason,
        substrates=tuple(rule["substrates"]) if rule.get("substrates") else None,
    )


def _resolve(message, adr):
    if not isinstance(message, str):
        return message
    return message.replace("{adr}", str(adr))


def _no_dialect(adr, substrate, declared):
    """Why a rule this estate's substrate is not covered by can say nothing.

    Product-side for the same reason the cloud case is: no upgrade of this build
    supplies a dialect nobody has authored, so the team is told what has to
    happen rather than to try a newer version.
    """
    return (
        f"{adr} is recorded for {', '.join(declared)} and this estate is written in "
        f"{substrate}; it awaits a dialect a maintainer must author"
    )


def _no_fingerprint(adr, estate_clouds):
    if not estate_clouds:
        return (
            f"{adr} has no fingerprint for this estate, which declares no cloud this "
            "product recognises"
        )
    return (
        f"{adr} has no fingerprint for {', '.join(estate_clouds)}; it awaits one "
        "a maintainer must author"
    )
