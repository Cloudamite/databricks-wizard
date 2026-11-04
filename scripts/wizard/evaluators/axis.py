"""The axis family: what one catalog corresponds to.

DEC-002's three states, each measured against the environments the team
recorded. The rule is handed them on its compiled `parameters`, so no
evaluator reads an ADR set and a second dialect implementing the same handle
gets the same names.

**The order of the recorded environments is the answer to two other questions.**
They are given least to most production-like, so the last is production, which
is what `destroy_protection_protected` and `catalog_isolation_read_only` read.
Nothing here depends on the order — every environment is equal to an axis — and
it is recorded once so that the three rules cannot come to disagree.

**Domains are never recorded, and this is where that decision is paid for.**
A new domain is ordinary growth, and a target state re-authored for one would be
re-authored constantly. So the domain axis is measured by shape: whatever
domains the estate declares, each must appear in every recorded environment.

**Two kinds of deviation, and the second is why the names are worth recording.**
A catalog the recorded list does not name is an ordinary per-resource outcome. A
recorded environment the estate declares no catalog for has no resource at all,
and it is the finding a team most wants — a deviation found by absence is the
shape it takes. Where the estate declaration does not say which root holds an
environment, the missing catalog cannot be placed, and the rule says so instead
of attributing a deviation to a root that did not earn it.
"""

from wizard import outcomes
from wizard.evaluators import schemas
from wizard.evaluators.reading import stated
from wizard.naming import SEPARATOR, environments_of, listed, split_name

CATALOG = "databricks_catalog"


def catalog_axis_environment(rule, estate):
    """DEC-002's `environment` state: the catalogs are the environments.

    The recorded names *are* the catalogs. A catalog outside the list is a
    deviation on the resource that declares it; an environment with no catalog
    is a deviation with no resource, placed in the root the declaration labels
    with it.
    """
    recorded = environments_of(rule)
    catalogs = estate.of_type(CATALOG)
    if not recorded or not catalogs:
        return (_disclosed(rule, estate, CATALOG),)

    found, declared, unknown = [], set(), []
    for resource in catalogs:
        name = resource.values.get("name")
        if not stated(name):
            unknown.append(resource)
            found.append(_unnamed(rule, resource, "catalog"))
            continue
        declared.add(name)
        if name in recorded:
            found.append(outcomes.passed(rule, resource, name))
        else:
            found.append(outcomes.failed(rule, resource, name, catalog=name))

    found.extend(_absent(rule, estate,
                         [(name, name) for name in recorded if name not in declared],
                         placeholder="catalog", unknown=unknown))
    return tuple(found)


def catalog_axis_domain(rule, estate):
    """DEC-002's `domain` state: a catalog per domain, environments as schemas.

    Every catalog holds one schema per recorded environment and no other. The
    catalog names are the team's own and nothing here reads them — which is what
    makes this the option under which a new domain costs nothing.

    The shape is `schemas.holds_exactly`, shared with DEC-003's
    `layer-per-schema` state: the two make the same claim about the same
    resources and differ only in which recorded list they read. Two target
    states, two handles, one implementation — a second copy would be a second
    place for the absence case to drift.
    """
    return schemas.holds_exactly(rule, estate, environments_of(rule))


def catalog_axis_both(rule, estate):
    """DEC-002's `both` state: a catalog per domain and environment.

    Every catalog is named `domain_environment`, and every domain the estate
    declares has one in every recorded environment. The domain half of the name
    is whatever the team put there; the environment half must be one they
    recorded.
    """
    recorded = environments_of(rule)
    catalogs = estate.of_type(CATALOG)
    if not recorded or not catalogs:
        return (_disclosed(rule, estate, CATALOG),)

    found, declared, unknown = [], {}, []
    for resource in catalogs:
        name = resource.values.get("name")
        if not stated(name):
            unknown.append(resource)
            found.append(_unnamed(rule, resource, "catalog"))
            continue

        domain, environment = split_name(name)
        if domain and environment in recorded:
            declared.setdefault(domain, set()).add(environment)
            found.append(outcomes.passed(rule, resource, name))
        else:
            # Either it carries no environment this target state records, or it
            # is not named for a domain and an environment at all. One deviation
            # either way: the team's convention is one thing, and a name that
            # does not follow it has left the shape the rule measures.
            found.append(outcomes.failed(rule, resource, name, catalog=name))

    absent = [
        (f"{domain}{SEPARATOR}{environment}", environment)
        for domain in sorted(declared)
        for environment in recorded
        if environment not in declared[domain]
    ]
    found.extend(_absent(rule, estate, absent, placeholder="catalog", unknown=unknown))
    return tuple(found)


_disclosed = schemas.disclosed


_unnamed = schemas.unnamed


def _absent(rule, estate, expected, placeholder, unknown=()):
    """A deviation per thing the target state names and the estate does not declare.

    Where a catalog of unknown name is declared it may be the missing one, and
    the absences are one non-result naming both instead (`schemas.undecided`).

    `expected` is `(estate address, environment)` pairs. The root comes from the
    estate declaration: a missing catalog belongs in the root that says it holds
    that environment. Where nothing says, the rule reports a non-result naming
    what it could not place — a deviation attributed to a root that did not earn
    it would be a finding in the wrong place, and identity would move the day the
    declaration gained a label.
    """
    if expected and unknown:
        return [schemas.undecided(rule, estate, [address for address, _ in expected],
                                  unknown, placeholder)]
    placed, unplaced = [], []
    for address, environment in expected:
        root = _root_holding(estate, environment)
        if root is None:
            unplaced.append(address)
        else:
            placed.append(outcomes.missing(rule, root, address, **{placeholder: address}))

    if unplaced:
        placed.append(outcomes.unevaluable(
            rule, outcomes.ESTATE_SIDE,
            f"this estate declares no {listed(unplaced)}, and the estate declaration does not "
            "say which root holds the environment each belongs to, so the deviation cannot be "
            "placed; labelling the roots is what resolves it",
            root=estate.root))
    return placed


def _root_holding(estate, environment):
    """The declared root that says it holds `environment`, or `None`."""
    for root in estate.roots:
        if estate.environment_of(root) == environment:
            return root
    return None
