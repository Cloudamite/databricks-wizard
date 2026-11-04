"""The catalog family: what a catalog is reachable from, and by whom.

DEC-001b's three states read the same two resource types — a catalog and the
bindings that say which workspaces may reach it — and disagree about what they
should say. They are three handles because the write hoists the chosen option's
rule into the ADR set without its key, so the handle is the only thing left
saying what was expected.

The estate address throughout this family is the catalog's `name`, the name it
has on the metastore. That is what makes a deviation survive a `moved` block, a
module rename or a `for_each` key change, and it is the
component the gate's ratchet matches an exception against.
"""

from wizard import outcomes
from wizard.evaluators.reading import stated
from wizard.naming import named_for

CATALOG = "databricks_catalog"
BINDING = "databricks_workspace_binding"

# `securable_type` defaults to `catalog` in the provider and a plan need not
# restate a default, so an absent one counts. Treating it as a non-match would
# fail catalogs that are correctly bound, which is the *rule fires on a
# legitimate configuration* failure, which is worse than no rule at all.
CATALOG_SECURABLE = "catalog"

# The whole documented vocabulary of `isolation_mode`, verified against
# `databricks/databricks` 1.133.0: "Whether the catalog is accessible from all
# workspaces or a specific set of workspaces. Can be `ISOLATED` or `OPEN`."
ISOLATED = "ISOLATED"
OPEN = "OPEN"
ISOLATION_MODES = (ISOLATED, OPEN)


def catalog_isolation_isolated(rule, estate):
    """DEC-001b's `isolated` state: every catalog ISOLATED, and bound.

    Verified against `databricks/databricks` 1.133.0. The estate address is
    `values.name` — the catalog's name on the metastore — which is what makes a
    deviation survive a `moved` block, a module rename or a `for_each` key
    change.

    The binding must be in the same reader as the catalog. The rule is
    `scope: root`, so that reader spans one root, and a team that split a
    catalog from its binding across two roots gets a deviation they can see
    rather than a rule that reads across the boundary their declaration draws.
    """
    catalogs = estate.of_type(CATALOG)
    if not catalogs:
        return (outcomes.unevaluable_as_disclosed(
            rule, estate.root, otherwise=f"{estate.subject} declares no {CATALOG} resources"),)

    bound = _bound_catalogs(estate)
    found = []
    for resource in catalogs:
        name, mode, unreadable = _isolation_state(rule, resource)
        if unreadable is not None:
            found.append(unreadable)
            continue

        if mode == ISOLATED and name in bound:
            found.append(outcomes.passed(rule, resource, name))
        else:
            # ISOLATED with no binding is a deviation and not a non-result: the
            # catalog is reachable from no workspace, which is a real divergence
            # from a target state that says it is reachable from the bound ones.
            found.append(outcomes.failed(rule, resource, name, catalog=name))
    return tuple(found)


def catalog_isolation_open(rule, estate):
    """DEC-001b's `open` state: no catalog is ISOLATED.

    Verified against `databricks/databricks` 1.133.0. The same resource type and
    the same attribute as its sibling, read for the opposite target state — which
    is why they are two handles rather than one,
    and why the pair is what shows the analyzer follows the recorded decision
    rather than shipping an opinion.

    **Bindings are not read here.** A binding is evidence of the state the
    sibling measures; reading it in this one would make two handles disagree
    about the same estate for reasons neither rule states.

    **A mode the provider does not document is a non-result, where the sibling
    calls it a deviation.** The difference is in what each rule asserts. This one
    asserts the *absence* of ISOLATED, so a third value would have to be passed —
    a claim about a value this build does not know the meaning of. The sibling
    asserts a positive state, and an estate not in that state has diverged from
    it whatever else it says.
    """
    catalogs = estate.of_type(CATALOG)
    if not catalogs:
        return (outcomes.unevaluable_as_disclosed(
            rule, estate.root, otherwise=f"{estate.subject} declares no {CATALOG} resources"),)

    found = []
    for resource in catalogs:
        name, mode, unreadable = _isolation_state(rule, resource)
        if unreadable is not None:
            found.append(unreadable)
            continue

        if mode not in ISOLATION_MODES:
            found.append(outcomes.unevaluable_on(
                rule, resource, estate_address=name,
                reason=f"{name} declares isolation_mode {mode!r}, which is not one of the "
                       f"{' or '.join(ISOLATION_MODES)} this build reads; the value was read "
                       "and not understood, so no verdict rests on it"))
        elif mode == ISOLATED:
            found.append(outcomes.failed(rule, resource, name, catalog=name))
        else:
            found.append(outcomes.passed(rule, resource, name))
    return tuple(found)


def _isolation_state(rule, resource):
    """A catalog's name and isolation mode, or the non-result standing for them.

    `(name, mode, None)` where both were read, and `(None, None, outcome)` where
    either was not. Both handles of this pair read the same two attributes and
    owe the same two non-results, and a second copy of this is a second place for
    them to drift apart.
    """
    name = resource.values.get("name")
    if not stated(name):
        # No reproducible estate address, so no identity — and a deviation whose
        # identity moved between runs would never match its exception and
        # would fire the gate on every build forever.
        return None, None, outcomes.unevaluable_on(
            rule, resource,
            reason=f"the name of {resource.address} is not known at plan time, so the "
                   "catalog has no identity a deviation could be recorded against")

    mode = resource.values.get("isolation_mode")
    if not stated(mode):
        # The provider's own default is not the same fact as the team having
        # expressed a choice, and the resource could have been changed outside
        # Terraform. A verdict is issued only on a fact that was read.
        return None, None, outcomes.unevaluable_on(
            rule, resource, estate_address=name,
            reason=f"{name} declares no isolation_mode, so this estate expresses no "
                   "choice for the rule to measure")

    return name, mode, None


def _bound_catalogs(estate):
    """Every catalog name some workspace binding in this reader names."""
    return {
        binding.values.get("securable_name")
        for binding in estate.of_type(BINDING)
        if binding.values.get("securable_type", CATALOG_SECURABLE) == CATALOG_SECURABLE
    }


# `mode` is read by exactly one evaluator, and it is the one declared exception
# to where an evaluator reads. Every other rule measures the platform,
# where a team refactoring a reference into a declaration has changed nothing;
# this one measures what the IaC layer manages, and that refactor is the change
# it exists to see.
MANAGED = "managed"


def catalog_managed_by_iac(rule, estate):
    """PRE-002: no catalog is introduced by a reference alone.

    A catalog present only as a data source is one the configuration reads and
    does not declare — created through the UI, the account console or SQL. It is
    not merely undeclared: the analyzer reads the configuration rather than the
    metastore, so every other rule in the set is silently inapplicable to it,
    which is the argument the entry makes to the team during `describe`.

    The rule is `scope: estate` and is evaluated only when every declared root
    was supplied, so a catalog declared in the account root and referenced in a
    workspace root is managed — as the team's own declaration says it is.
    """
    catalogs = estate.of_type(CATALOG)
    if not catalogs:
        return (outcomes.unevaluable_as_disclosed(
            rule, estate.root, otherwise=f"{estate.subject} declares no {CATALOG} resources"),)

    declared = {
        resource.values.get("name") for resource in catalogs
        if resource.mode == MANAGED and stated(resource.values.get("name"))
    }

    found = []
    # One outcome per catalog, not per block. A module reading back a catalog the
    # configuration also declares is ordinary, and two outcomes would be two
    # exceptions for one catalog.
    seen = set()
    for resource in catalogs:
        name = resource.values.get("name")
        if not stated(name):
            found.append(outcomes.unevaluable_on(
                rule, resource,
                reason=f"the name of {resource.address} is not known at plan time, so the "
                       "catalog has no identity a deviation could be recorded against"))
            continue
        if name in seen:
            continue
        seen.add(name)

        if name in declared:
            found.append(outcomes.passed(rule, _declaring(catalogs, name), name))
        else:
            found.append(outcomes.failed(rule, resource, name, catalog=name))
    return tuple(found)


def _declaring(catalogs, name):
    """The block that declares `name`, which is the one a team would go and read."""
    return next(resource for resource in catalogs
                if resource.mode == MANAGED and resource.values.get("name") == name)


# `BINDING_TYPE_READ_WRITE` is the provider's default and a plan need not restate
# it, so an absent binding type is a read-write binding — verified against
# `databricks/databricks` 1.133.0: "Binding mode. Default to
# `BINDING_TYPE_READ_WRITE`. Possible values are `BINDING_TYPE_READ_ONLY`,
# `BINDING_TYPE_READ_WRITE`."
READ_ONLY = "BINDING_TYPE_READ_ONLY"


def catalog_isolation_read_only(rule, estate):
    """DEC-001b's `bound-read-only` state: production is never writable from below.

    Three clauses, all measured: every catalog is ISOLATED, every catalog is
    bound, and no binding declared in a lower environment may write to a
    production catalog.

    **The product's own opinion is the third clause**, and it is why this option
    asks the team nothing. *Which workspaces only consume* has no answer a team
    gives from memory — a binding names a numeric workspace id — and it has a
    better one already recorded: the environments, in order, with production
    last.

    **What places a binding in an environment is the estate declaration**, not
    the binding. A binding names a workspace id and no attribute anywhere
    resolves that to an environment, so the root it was declared in is what
    says where it is. A run whose declaration labels no
    root cannot make the comparison, and says so.
    """
    recorded = tuple(dict(rule.parameters).get("environments") or ())
    catalogs = estate.of_type(CATALOG)
    bindings = estate.of_type(BINDING)
    labelled = {root: estate.environment_of(root) for root in estate.roots}
    if not recorded or not catalogs or not bindings or not any(labelled.values()):
        return (outcomes.unevaluable_as_disclosed(
            rule, estate.root,
            otherwise=f"{estate.subject} declares no {CATALOG} or {BINDING} resources, or the estate "
                      "declaration does not say which environment each root holds"),)

    production, lower = recorded[-1], set(recorded[:-1])
    bound = _bound_catalogs(estate)
    writable_from_below = _writable_from_below(estate, bindings, labelled, lower)

    found = []
    for resource in catalogs:
        name, mode, unreadable = _isolation_state(rule, resource)
        if unreadable is not None:
            found.append(unreadable)
            continue

        below = name in writable_from_below and named_for(name, production)
        if mode == ISOLATED and name in bound and not below:
            found.append(outcomes.passed(rule, resource, name))
        else:
            found.append(outcomes.failed(rule, resource, name, catalog=name))
    return tuple(found)


def _writable_from_below(estate, bindings, labelled, lower):
    """Every catalog some lower environment binds with permission to write."""
    return {
        binding.values.get("securable_name")
        for binding in bindings
        if binding.values.get("securable_type", CATALOG_SECURABLE) == CATALOG_SECURABLE
        and labelled.get(binding.root) in lower
        and binding.values.get("binding_type", "") != READ_ONLY
    }

