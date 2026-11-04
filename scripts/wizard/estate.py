"""The estate-declaration validity table, implemented.

A declaration names the Terraform roots one estate consists of, so that the
analyzer can tell *this estate declares no such resource* from *I was not given
the root that declares it* — two non-results with opposite remedies.

This is the same machinery as the corpus and ADR-set tables run against a third
list of rules, and it is here for a reason the other two do not have: the corpus
ships with the product and the ADR set is emitted by the wizard, which can only
write shapes it knows. **A declaration is written by hand**, so it is the one
artefact where a team can make a shape mistake, and the validator exists so they
can find it themselves.

Nothing here reads the ADR set. That the declaration's substrate must agree with
the set's is the analyzer's check, because only the
analyzer has both.
"""

from pathlib import Path

from wizard.validity import (
    ESTATE_RULES,
    CannotRun,
    Failure,
    is_stated,
    read_mapping,
)


STATE_KEYS = {"bucket", "region"}


def state_of(document):
    """`(bucket, region)` the declaration names for its roots' state, or `None`."""
    state = document.get("state")
    return (state["bucket"], state["region"]) if isinstance(state, dict) else None


def validate(path):
    document = read_mapping(path)
    name = Path(path).name
    failures = []

    def failure(key, entries=()):
        return Failure(ESTATE_RULES[key], list(entries), name)

    # `schema_version` is the one rule that is about a type rather than a
    # presence: a declaration whose version is "1" would compare unequal to
    # every version the product knows, and silently.
    if not isinstance(document.get("schema_version"), int) or isinstance(
        document.get("schema_version"), bool
    ):
        failures.append(failure("schema_version"))

    if not is_stated(document.get("name")):
        failures.append(failure("name"))

    if not is_stated(document.get("substrate")):
        failures.append(failure("substrate"))

    # Where the roots' state is kept: the estate's own
    # configuration, not a fact about what it is, so its shape alone is checked.
    if "state" in document:
        state = document["state"]
        if not isinstance(state, dict) or set(state) != STATE_KEYS:
            failures.append(failure("state"))
        elif not all(isinstance(state[key], str) and is_stated(state[key])
                     for key in sorted(STATE_KEYS)):
            failures.append(failure("state_values"))

    roots = document.get("roots")
    if not isinstance(roots, list) or not roots:
        # An empty list is the same claim as an absent key, made explicitly, and
        # both are defective: a declaration naming no root cannot tell a
        # supplied root from a missing one, which leaves every estate-scoped
        # rule silently unevaluable — the condition the file exists to prevent.
        failures.append(failure("roots"))
        return failures

    if any(not isinstance(root, dict) for root in roots):
        raise CannotRun(f"{name} contains a root that is not a mapping")

    seen = set()
    duplicated = []
    for root in roots:
        root_name = root.get("name")
        # Optional, and checked for shape rather than for membership. Which
        # environments exist is the ADR set's to record, and this table is
        # deliberately runnable against the declaration alone — the same reason
        # the retired substrate-agreement check belonged to the analyzer.
        # A root naming an environment no set records is not defective: the
        # evaluator that correlates the two reports it, in the run that has both.
        if "environment" in root and not is_stated(root.get("environment")):
            failures.append(failure("root_environment"))
        if not is_stated(root_name):
            failures.append(failure("root_name"))
            continue
        if root_name in seen:
            duplicated.append(root_name)
        seen.add(root_name)

    if duplicated:
        # Named once with every root it implicates, in the order that exhibits
        # the collision — a duplicate is a property of the set, not of either
        # root on its own.
        failures.append(failure("root_names_unique", duplicated))

    return failures
