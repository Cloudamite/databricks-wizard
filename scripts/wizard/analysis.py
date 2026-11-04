"""The analyzer's front end: everything that can refuse, and nothing that measures.

`prepare` runs the analyzer's front-end stages, in order — the ADR set
read and validated, the estate declaration read and validated, a plan bound to
each declared root, the estate's clouds detected and the set compiled against
them and against the declared substrate — and hands back a `Preparation`.
Evaluation, the enforcement invariant, the causes of a non-result, the report and
deviation identity come later and are not here.

**The order is the design.** Each stage reads something the stage before it has
already refused to proceed without, so one run reports one thing and it is
always the earliest thing wrong. A defective set outranks a defective
declaration, which outranks an unreadable plan.

**The substrate is the declaration's alone.** The set records a decision about a
team's architecture and says nothing about the tool that declares it, so there
are no two substrates to compare and no run to refuse on that ground. A rule
whose subject *is* the IaC layer declares `substrates`, and on an estate written
in another it compiles to a non-result naming the missing dialect rather than
taking the whole run down with it.

Detection is a stage here rather than a call beside `prepare` for the same
reason: detection comes after the gate and before compilation, and a
stage in this function makes that structural. A run the gate refuses has read no
provider configuration at all.

Two ways of refusing, and the difference is in the structure rather than in a
field beside it. `CannotRun` carries a sentence, for an artefact that could not
be read and for a binding the declaration does not admit. `Defective` carries
the validator's own failures, for an artefact that was read and broke its own
table. Both exit `2` at the command; a team acts on them differently.

Nothing here writes. The analyzer's only write is the report, and the report is
not built.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from wizard import adr_set, clouds, estate, rules
from wizard.validity import CannotRun, read_mapping

# What each artefact is called when a team is told about it. The keys are the
# ones `validity.ARTEFACT_KEYS` already names, so the two commands say the same
# words about the same file.
ARTEFACTS = {"adr-set": "ADR set", "estate": "estate declaration",
             "register": "exception register"}

# A resolved plan is recognised structurally. What a particular `format_version`
# *means* is the evaluators' business, and pinning a version
# here would be a compatibility policy no requirement states, applied by the
# component least able to know whether it mattered.
PLAN_KEYS = ("format_version", "planned_values")

# The output the offline planner adds to each copy, naming the variables given a
# placeholder. The plan file is Terraform's, so an output is the one place the
# planner can write that reaches it; `placeholders` reads it back.
RECORD = "databricks_wizard_placeholders"


class Defective(Exception):
    """A readable artefact that broke its own validity table.

    Distinct from `CannotRun` because the remedy is: *could not be read* sends a
    team to a path or a parser, and *is defective* sends them to a rule in a
    table with the entries that broke it.
    """

    def __init__(self, artefact, failures):
        super().__init__(f"the {ARTEFACTS[artefact]} is defective")
        self.artefact = artefact
        self.failures = list(failures)


@dataclass(frozen=True)
class Root:
    """One declared root and the plan this run was handed for it."""

    name: str
    plan: dict


@dataclass(frozen=True)
class Preparation:
    """What the front end hands to everything past binding.

    `bound` and `not_supplied` are ordered by the **declaration**, not by the
    arguments. A mapping would compare equal however it was built, so ordering
    by the declaration is what makes the declaration's order a claim about the
    analyzer rather than about `dict`.

    `clouds` is ordered by `clouds.CLOUDS` for the same kind of reason, and is
    empty exactly when no supplied plan configures one of the three — which is a
    finding rather than an error.

    `rules` is every compiled fingerprint of every entry carrying a rule, in ADR
    order. It is complete over the target state rather than over the part of it
    this estate can be measured on: a rule that can only be UNEVALUATED is here,
    carrying the cause that says why.
    """

    adr_set: dict
    declaration: dict
    bound: Tuple[Root, ...]
    not_supplied: Tuple[str, ...]
    clouds: Tuple[str, ...]
    rules: Tuple[rules.Rule, ...]


def prepare(set_path, estate_path, plans):
    """Run every stage up to binding, or refuse.

    `plans` maps a declared root name to a plan path. Raises `Defective` for an
    artefact that broke its table and `CannotRun` for everything else.
    """
    document = validated(adr_set, "adr-set", set_path)
    declaration = validated(estate, "estate", estate_path)
    return _bind(document, declaration, plans)


def validated(reader, artefact, path):
    # Read first, so an unparseable file is *could not be read* rather than a
    # table's worth of failures about a document nobody has. The reader reads it
    # again, because `validate(path)` being self-contained is the contract every
    # caller already has and the cost is one extra read of a small file.
    document = read_mapping(path)
    failures = reader.validate(path)
    if failures:
        raise Defective(artefact, failures)
    return document


def _bind(document, declaration, plans):
    declared = tuple(root["name"] for root in declaration["roots"])

    undeclared = sorted(name for name in plans if name not in declared)
    if undeclared:
        # Never adopted as new roots: the declaration is the authority on what
        # the estate is, and accepting an unknown name would let a rename stop a
        # root being measured with nothing saying so.
        named = ", ".join(repr(name) for name in undeclared)
        raise CannotRun(
            f"the estate declaration does not declare {named}, so no plan can be "
            "bound to it; the declaration is what says what this estate is"
        )

    bound = tuple(
        Root(name, _read_plan(name, plans[name])) for name in declared if name in plans
    )
    not_supplied = tuple(name for name in declared if name not in plans)
    # After binding, because it reads the plans, and therefore after every
    # refusal. This stage cannot refuse.
    detected = clouds.detect(root.plan for root in bound)
    # Compilation needs the cloud set, so it follows detection — and therefore
    # follows every refusal. Neither stage can refuse.
    # The substrate comes from the declaration rather than the set: the set
    # records a decision and says nothing about the tool that declares it.
    compiled = rules.compile_rules(document, detected, declaration.get("substrate"))
    return Preparation(document, declaration, bound, not_supplied, detected, compiled)


def placeholders(preparation):
    """Each covered root's variables the offline planner filled, in declaration order.

    Read from the record the planner adds to every plan. A
    root with an empty record, or with none because the team made the plan with
    Terraform, had every value, and is left out.
    """
    found = {}
    for root in preparation.bound:
        outputs = root.plan["planned_values"].get("outputs") or {}
        names = outputs.get(RECORD, {}).get("value", [])
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            raise CannotRun(f"the plan bound to root {root.name!r} records its placeholders "
                            f"in the output {RECORD!r} as something other than a list of names")
        if names:
            found[root.name] = sorted(names)
    return found


def _read_plan(root, path):
    """The plan for `root`, or `CannotRun` naming the root as well as the path.

    Naming the root is what makes the message useful to whoever maintains the
    pipeline: a caller who supplied six paths is never
    left to work out which of them this is about.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CannotRun(
            f"the plan bound to root {root!r} at {path.name} could not be read: {exc.strerror}"
        ) from None

    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CannotRun(
            f"the plan bound to root {root!r} at {path.name} is not readable JSON: {exc.msg}"
        ) from None

    if not isinstance(document, dict) or any(key not in document for key in PLAN_KEYS):
        missing = ", ".join(PLAN_KEYS)
        raise CannotRun(
            f"the plan bound to root {root!r} at {path.name} is not a Terraform plan: "
            f"a resolved plan carries {missing}"
        )

    return document
