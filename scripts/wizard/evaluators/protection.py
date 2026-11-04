"""The protection family: what the IaC layer guards against destruction.

DEC-006a's fingerprint was recorded by the audit as "`force_destroy`;
`lifecycle.prevent_destroy`". **Only the first is in a plan.** Terraform's JSON
format carries no lifecycle block anywhere — not in `planned_values`, and not in
the configuration representation, whose resource objects are `address`, `mode`,
`type`, `name`, `provider_config_key`, `provisioners`, `expressions`,
`schema_version`, `count_expression` and `for_each_expression`. A guard declared
that way is invisible to this product, and no version of it can see one.

What is left is one affirmative fact, verified against `databricks/databricks`
1.133.0: `force_destroy` is "Delete catalog regardless of its contents" on
`databricks_catalog` and "Delete schema regardless of its contents" on
`databricks_schema`. Set to `true`, it says the securable may be deleted with
data in it, which is a securable declaring no guard.

**`force_destroy` false and `force_destroy` absent are the same bytes in a
plan.** The marshaller renders an attribute the team never wrote exactly as it
renders one they wrote as `false`, so *this team chose not to guard* and *this
team never considered it* are indistinguishable here. Reading either as *a guard
is declared* would report a deviation against every catalog anyone has written
without thinking about it — the *rule fires on a legitimate configuration*
failure, which is worse than no rule at all.

So this family confirms the recorded state where it is stated and discloses the
rest, rather than inventing the verdict it cannot read. The entry discloses it
too: a rule whose non-result a team cannot act on is at least a rule that has not
lied to them.
"""

from wizard import outcomes
from wizard.evaluators.reading import stated

CATALOG = "databricks_catalog"
SCHEMA = "databricks_schema"


def destroy_protection_uniform(rule, estate):
    """DEC-006a's `uniform` state: no catalog or schema declares a guard.

    `force_destroy: true` is a securable saying it may be deleted regardless of
    its contents, which is the recorded state holding for that securable.
    Anything else is not readable, for the reason this module's docstring gives,
    and is the non-result the entry discloses.
    """
    securables = estate.of_type(CATALOG) + estate.of_type(SCHEMA)
    if not securables:
        return (outcomes.unevaluable_as_disclosed(
            rule, estate.root,
            otherwise=f"{estate.subject} declares no {CATALOG} or {SCHEMA} resources"),)

    found = []
    for resource in securables:
        address, unreadable = _securable_address(rule, resource)
        if unreadable is not None:
            found.append(unreadable)
        elif resource.values.get("force_destroy") is True:
            found.append(outcomes.passed(rule, resource, address))
        else:
            found.append(outcomes.unevaluable_as_disclosed(
                rule, estate.root, resource=resource, estate_address=address,
                otherwise=f"{address} declares no force_destroy, and a guard declared through "
                          "lifecycle.prevent_destroy is in no part of a Terraform plan"))
    return tuple(found)


def destroy_protection_protected(rule, estate):
    """DEC-006a's `protected` state: production is guarded, and nothing else is.

    **Production is the last environment DEC-002 recorded**, read from the
    rule's parameters rather than asked for again: two records of one fact can
    disagree, and a team who renamed an environment in one place and not the
    other would get deviations against securables that never moved.

    **Which securables are production follows the axis the team chose, and this
    rule is not told which.** It does not need to be: under the environment axis
    the production catalog *is* the environment's name, under `both` it ends
    with it, and under the domain axis the production schema carries it. All
    three are the same test on a name, so one rule measures all three without
    reading another entry's answer.

    This reads `force_destroy` the opposite way round from its sibling, and the
    asymmetry is the point. `uniform` asks whether a team *expressed* no guard,
    and an absent attribute expresses nothing. This one asks whether a securable
    *may be deleted with data in it*, which is a fact about the estate that an
    absent attribute settles: it may not.
    """
    production = _production(rule)
    securables = estate.of_type(CATALOG) + estate.of_type(SCHEMA)
    if not production or not securables:
        return (outcomes.unevaluable_as_disclosed(
            rule, estate.root,
            otherwise=f"{estate.subject} declares no {CATALOG} or {SCHEMA} resources"),)

    by_catalog = {
        resource.values.get("name"): resource for resource in estate.of_type(CATALOG)
    }

    found = []
    for resource in securables:
        address, unreadable = _securable_address(rule, resource)
        if unreadable is not None:
            found.append(unreadable)
            continue
        if not _is_production(resource, production, by_catalog):
            continue
        if resource.values.get("force_destroy") is True:
            found.append(outcomes.failed(rule, resource, address, resource=address))
        else:
            found.append(outcomes.passed(rule, resource, address))

    if not found:
        # Nothing in this estate is production by any of the three namings. The
        # rule has nothing to measure rather than nothing to report, and a
        # vacuous PASS would say production is protected in an estate that
        # declares none.
        return (outcomes.unevaluable_as_disclosed(
            rule, estate.root,
            otherwise=f"no catalog or schema in {estate.subject} is named for {production!r}, so "
                      "none of them can be placed in production"),)
    return tuple(found)


def _production(rule):
    """The environment the recorded list ends with, or `None` where none was."""
    recorded = tuple(dict(rule.parameters).get("environments") or ())
    return recorded[-1] if recorded else None


def _is_production(resource, production, by_catalog):
    """Whether this securable belongs to production, whichever axis names it.

    A catalog called `prod` (the environment axis) or `sales_prod` (both axes);
    a schema called `prod` (the domain axis) or one held by a production
    catalog. Nothing here reads which axis the team chose — the three namings do
    not overlap in a way that could make one estate answer differently.
    """
    name = resource.values.get("name")
    if named_for(name, production):
        return True
    if resource.type == SCHEMA:
        parent = by_catalog.get(resource.values.get("catalog_name"))
        return parent is not None and named_for(parent.values.get("name"), production)
    return False


def named_for(name, production):
    return name == production or (stated(name) and name.endswith(f"_{production}"))


def _securable_address(rule, resource):
    """What the platform calls this securable, or the non-result standing for it.

    A catalog is named by itself; a schema is named by the catalog that holds it
    and its own name, because `bronze` in `sales` and `bronze` in `weather` are
    two schemas and two identities. Half of that pair is no identity at all.
    """
    name = resource.values.get("name")
    parent = resource.values.get("catalog_name") if resource.type == SCHEMA else None

    if not stated(name) or (resource.type == SCHEMA and not stated(parent)):
        return None, outcomes.unevaluable_on(
            rule, resource,
            reason=f"the name of {resource.address} is not known at plan time, so the "
                   "securable has no identity a deviation could be recorded against")

    return (f"{parent}.{name}" if parent else name), None
