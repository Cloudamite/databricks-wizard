"""The outcomes become the report.

The structured report is the primary artefact and this module is the only thing
that builds it. `rendering.py` derives the human output from what this returns
and from nothing else, which is the card/renderer seam one layer out: a
rendering that recounted the deviations would agree with the structure until the
day it did not, and the day it does not, the team believes the screen.

**Split by kind.** A deviation carries an identity and a resolved message; a
non-result carries a cause and a reason; an entry the set does not enforce
carries a state and why it carries no rule. Each entry holds only the fields its
kind has, so no field is null because its kind has no such thing, and the
exception register and the gate each read the one array they need.

**Complete over the compiled rules, and over the set.** Every compiled rule
appears once per outcome it produced, whatever the verdict, and every entry
carrying no rule appears with the reason it carries none. Both are the same
honesty: a rule absent from the report cannot be told from a rule the set does
not carry, and an entry absent from it cannot be told from an entry the team
never saw.

**Nothing dated, nothing pathed, nothing copied.** No timestamp, duration,
hostname, user or path — a report is regenerated on every build and compared
against its predecessor, and a clock would be the one field guaranteed to change
while the estate did not. The only plan values that reach the file are the
placeholders a rule's author named and the addresses evaluation emitted; the
analyzer copies no other attribute of any resource, which is why a workspace URL
or a metastore id cannot leak through it.

This module reads a `Preparation` and a sequence of outcomes. It opens no file,
reads no clock and invokes no model.
"""

from wizard.adr_set import STATES, adr_number, set_digest
from wizard.analysis import placeholders
from wizard.identity import identity_of
from wizard.outcomes import CAUSES, FAIL, PASS, PLACEHOLDER, message_of, template_of

# The exception register and the gate read this file and a baseline is a report kept, so a
# consumer must be able to tell a shape it understands from one it does not
# without inferring it from which fields happen to be present. Version 2 added
# `measured_against.set`; version 3 added `counts.by_root`.
SCHEMA_VERSION = 4

# The substrate an audit's report records: what tells a consumer it
# holds an audit of the account rather than an analysis of plans.
LIVE = "live"


def place_key(measured_against):
    """The key an outcome's place is written under: `root` in the analyzer's
    report, `place` in the audit's, since an account has no roots. The identity
    keeps its four components either way."""
    return "place" if measured_against.get("substrate") == LIVE else "root"


def report(preparation, outcomes):
    """The structured report of one analysis.

    A pure function of its two arguments.
    """
    return assemble(preparation.adr_set,
                    measured_against(preparation.adr_set,
                                     preparation.declaration.get("substrate")),
                    _estate(preparation), outcomes)


def assemble(document, measured_against, estate, outcomes, addresses=True):
    """A report of `outcomes` against the set `document`, from either dialect.

    The analyzer's and the audit's reports differ in what they say was measured
    (`measured_against`, `estate`) and in whether an outcome carries a Terraform
    address; everything else is this one shape. `addresses` is false for the
    audit, whose outcomes have no Terraform address and carry no key for one.

    The key order is the order a reader meets them in: what this measured
    against, what it measured, the position, and only then the findings — the
    head of the report is the position, never the first deviation.
    """
    place = place_key(measured_against)
    deviations, conformant, unevaluated = _partition(outcomes, addresses, place)
    not_enforced = _not_enforced(document)
    counts = _counts(document, deviations, conformant, unevaluated, not_enforced)
    counts["by_root"] = _by_root(place, estate.get("declared_roots", ()),
                                 deviations, conformant, unevaluated)
    return {
        "schema_version": SCHEMA_VERSION,
        "measured_against": measured_against,
        "estate": estate,
        "counts": counts,
        "deviations": deviations,
        "conformant": conformant,
        "unevaluated": unevaluated,
        "not_enforced": not_enforced,
    }


def _partition(outcomes, addresses, place):
    """The outcomes as three arrays, in the order evaluation produced them.

    A partition taken in place rather than three sorts: evaluation
    already fixes the order — by compiled rule, then by the declaration's root
    order, then by estate address — and re-sorting here would be a second
    implementation of it that could come to disagree.

    A deviation whose identity has already been seen is dropped rather than
    carried twice. Identity is a projection of four
    components out of a larger outcome, and any projection can map two things to
    one; where the analysis reaches the same finding twice, the report states it
    once.
    """
    deviations, conformant, unevaluated = [], [], []
    seen = set()
    for outcome in outcomes:
        if outcome.verdict == FAIL:
            identity = identity_of(outcome)
            if identity in seen:
                continue
            seen.add(identity)
            deviations.append(_located(_deviation(outcome, identity, place), outcome, addresses))
        elif outcome.verdict == PASS:
            conformant.append(_located(_conformant(outcome, place), outcome, addresses))
        else:
            unevaluated.append(_unevaluated(outcome, place))
    return deviations, conformant, unevaluated


def _deviation(outcome, identity, place):
    """One finding: what was decided, what it was found on, and what it says.

    `expected` is the rule's own expression of the target state and `observed`
    is what the evaluator read — the two halves of *what the target state
    expected against what the plan holds*. `observed` carries the values of
    the placeholders the deviation's message names and nothing else. An evaluator may supply more than a rule's
    message names — PRE-001's supplies `objects` to sets written before their
    message named it — and what the author did not name stays out.

    `message` is rendered here from the values beside it rather than stored on
    the outcome, so the sentence and its data cannot disagree.
    """
    return {
        "identity": {
            "adr": identity.adr,
            "evaluator": identity.evaluator,
            place: identity.root,
            "estate_address": identity.estate_address,
        },
        **_rule_fields(outcome.rule),
        place: outcome.root,
        "estate_address": outcome.estate_address,
        "observed": _observed(outcome),
        "message": message_of(outcome),
    }


def _observed(outcome):
    """The placeholder values the deviation's message names. The message is the one `message_of` renders, so a
    deviation found by absence keeps what its absence message names."""
    named = set(PLACEHOLDER.findall(template_of(outcome) or ""))
    return {name: value for name, value in outcome.placeholders if name in named}


def _conformant(outcome, place):
    """One rule holding on one resource.

    Carried for the reason a PASS is not omitted: a rule absent from the report
    is indistinguishable from a rule the target state does not carry.
    """
    return {
        **_rule_fields(outcome.rule),
        place: outcome.root,
        "estate_address": outcome.estate_address,
    }


def _located(entry, outcome, addresses):
    """`entry` with the Terraform address after its estate address, where the
    report carries one: how a team finds the resource in their code, display
    only."""
    if not addresses:
        return entry
    located = {}
    for key, value in entry.items():
        located[key] = value
        if key == "estate_address":
            located["terraform_address"] = outcome.terraform_address
    return located


def _unevaluated(outcome, place):
    """One non-result, with the class it is in and the sentence that says why.

    `root` is present even where no resource was matched — a rule that found
    nothing in `dev` found nothing *in dev* — and is `None` only for an
    estate-scoped rule where no one root is the answer.

    There is no `resolved_by` field. The cause is already the field that says
    which class this is in, and a sentence beside it would be a second
    statement of the same fact; what resolves each class is a label the
    rendering applies.
    """
    return {
        **_rule_fields(outcome.rule),
        "cause": outcome.cause,
        "reason": outcome.reason,
        place: outcome.root,
    }


def _rule_fields(rule):
    """What every entry carries about the rule it came from.

    `enforceability` is among them because its value must reach the report
    unchanged: it is disclosure, and a consumer that
    skipped a `weak` rule would stop running a check with nothing in the report
    saying so.
    """
    return {
        "adr": rule.adr,
        "evaluator": rule.evaluator,
        "expected": rule.summary,
        "clouds": list(rule.clouds),
        "enforceability": rule.enforceability,
    }


def _not_enforced(document):
    """Every entry carrying no rule, with the reason it carries none.

    A declined entry carries its `rationale`, an entry left open its
    `unconstrained` sentence, and an inapplicable one the entry that made it so — the entry's own field names rather than one `reason` field
    meaning two different things.

    `origin` is quoted here and nowhere else. The report may describe the set;
    it may not be steered by it, so how an entry arrived reaches a reader only
    where the entry itself is being described, never where a verdict, an
    identity or a message is.
    """
    listed = []
    for entry in sorted(_entries(document), key=adr_number):
        if isinstance(entry.get("rule"), dict):
            continue
        described = {
            "adr": entry.get("id"),
            "title": entry.get("title"),
            "state": entry.get("state"),
            "origin": entry.get("origin"),
        }
        if entry.get("rationale"):
            described["rationale"] = entry["rationale"]
        if entry.get("unconstrained"):
            described["unconstrained"] = entry["unconstrained"]
        if entry.get("made_inapplicable_by"):
            described["made_inapplicable_by"] = entry["made_inapplicable_by"]
        listed.append(described)
    return listed


def measured_against(document, substrate):
    """What this report is a measurement against, so it still says so alone.

    No path: a path is a property of the machine that ran it rather than of the
    measurement, and a report carrying one would differ between a CI agent and a
    laptop over inputs that were identical.

    The substrate is the caller's, never the set's: the estate declaration's
    for the analyzer, `live` for the audit. It is a fact about what was measured
    rather than about what was recorded — the same set read against a bundle
    estate, or against the account, is the same target state, measured
    somewhere else — and the set carries none to take it from.

    `set` is the digest of the set itself, taken over the document the analyzer
    validated and measured, never read from the file. It is for a
    command that compares a report with a set, and the rendering does not print
    it.
    """
    corpus = document.get("corpus") if isinstance(document.get("corpus"), dict) else {}
    return {
        "module": document.get("module"),
        "corpus": {"version": corpus.get("version"), "digest": corpus.get("digest")},
        "set": set_digest(document),
        "substrate": substrate,
    }


def _estate(preparation):
    """What was declared, what was covered, and what clouds were found.

    `covered_roots` is a bound on every estate-scoped claim in the report: a
    PASS is a claim about the roots supplied and never about the account or
    metastore they sit in, and a reader must be able to see the bound without
    re-running anything.

    An empty `clouds` is the whole fact behind every product-side non-result in
    such a run. It is carried as itself rather than restated as a flag beside
    it; leading with it once is the rendering's job.
    """
    return {
        "name": preparation.declaration.get("name"),
        "declared_roots": [root["name"] for root in preparation.declaration["roots"]],
        "covered_roots": [root.name for root in preparation.bound],
        "clouds": list(preparation.clouds),
        "placeholders": placeholders(preparation),
    }


def _counts(document, deviations, conformant, unevaluated, not_enforced):
    """The position, which is what a team reads first.

    Per cause as well as in total, with every cause present at zero: four
    non-results waiting on the team's own estate and four waiting on a corpus
    maintainer are different positions, and one total cannot carry the
    difference.
    """
    by_cause = {cause: 0 for cause in CAUSES}
    for entry in unevaluated:
        if entry["cause"] in by_cause:
            by_cause[entry["cause"]] += 1
    return {
        "deviations": len(deviations),
        "conformant": len(conformant),
        "unevaluated": len(unevaluated),
        "by_cause": by_cause,
        "not_enforced": len(not_enforced),
        "entries_by_state": _by_state(document),
    }


def _by_root(place, declared, deviations, conformant, unevaluated):
    """The position of each place, which is the same position one root at a time.

    Root-scoped rules run once per root, so an estate-wide count cannot say
    *nothing to measure in `account`* apart from *nothing to measure anywhere*.

    A list rather than a mapping, because a place can be `None` — an
    estate-scoped non-result no one root is the answer to — and a mapping has no
    key for that. Declared roots come first in the declaration's order, each
    present at zero, so a root that produced nothing is still seen to have been
    counted; any other place follows in order of first appearance, and the
    unplaced bucket, where there is one, comes last. Every count here sums to
    the estate's own.
    """
    order = list(dict.fromkeys(
        [*declared, *(entry[place] for entry in (*deviations, *conformant, *unevaluated)
                      if entry[place] is not None)]))
    if any(entry[place] is None for entry in (*deviations, *conformant, *unevaluated)):
        order.append(None)
    rows = {name: {place: name, "deviations": 0, "conformant": 0, "unevaluated": 0,
                   "by_cause": {cause: 0 for cause in CAUSES}} for name in order}
    for entry in deviations:
        rows[entry[place]]["deviations"] += 1
    for entry in conformant:
        rows[entry[place]]["conformant"] += 1
    for entry in unevaluated:
        row = rows[entry[place]]
        row["unevaluated"] += 1
        if entry["cause"] in row["by_cause"]:
            row["by_cause"][entry["cause"]] += 1
    return list(rows.values())


def _by_state(document):
    """Entries by `state`, with every state present at zero.

    Describing the set is permitted; being steered by it is not. A count is a
    description — it changes no verdict, no deviation and no identity.
    """
    counted = {state: 0 for state in STATES}
    for entry in _entries(document):
        state = entry.get("state")
        if state in counted:
            counted[state] += 1
    return counted


def _entries(document):
    entries = document.get("adrs") if isinstance(document, dict) else None
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]
