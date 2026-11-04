"""The workspace family: what one workspace corresponds to.

DEC-001a's four states. Three are measured **by naming shape** against the
environments the team recorded, exactly as DEC-002's catalogs are; the
fourth, a single workspace, by count. Two resource types, because a workspace is
created by a different one on Azure than on AWS and GCP:

- `databricks_mws_workspaces.workspace_name` — "name of the workspace, will
  appear on UI" (`databricks/databricks` 1.133.0). The provider says this
  resource is for AWS and GCP and to use the Azure one instead.
- `azurerm_databricks_workspace.name` — "Specifies the name of the Databricks
  Workspace resource." (`hashicorp/azurerm` 5.6.0)

The rule states its target state at platform level and names neither. Which
resource type carries the fingerprint is the dialect's, and an estate on two
clouds has as many workspaces as it declares of both.

**A name is the only fingerprint there is.** Nothing in a plan says what a
workspace is for, so the convention is the product's and the card states it: a
workspace per environment is named for it, one per business unit and
environment is named `<unit>_<environment>` — the separator and the split are
`naming.split_name`, shared with the catalogs so that one convention is written
once. Business units are never recorded; like DEC-002's domains, they are read
off the names.

**A missing workspace lands in the root that declares the others.** Workspaces
are declared in the account root, not in the root of the environment they
serve, so the catalog family's placement — the root labelled with the
environment — would put the deviation where nothing could fix it. Where more
than one root declares workspaces, nothing says which the missing one belongs
in, and the rule reports a non-result instead of choosing.

**A workspace whose name is unknown at plan time is a declared workspace with
no identity.** It counts toward a single workspace; it earns no verdict; and
where a named workspace is missing, it may be the missing one — so an absence
it could explain is a non-result, never a deviation the applied plan could
contradict.

These rules are `weak`, and for a reason no fingerprint fixes: a workspace
created out of band — the console, a landing zone, another team's configuration
— appears in no plan.
"""

from wizard import outcomes
from wizard.evaluators import schemas
from wizard.evaluators.reading import stated
from wizard.naming import SEPARATOR, environments_of, listed, split_name

# Each type paired with the attribute the platform, not Terraform, names it by.
WORKSPACE_TYPES = {
    "databricks_mws_workspaces": "workspace_name",
    "azurerm_databricks_workspace": "name",
}


def workspace_axis_environment(rule, estate):
    """DEC-001a's `environment` state: exactly one workspace named for each
    environment.

    An environment with none, or with more than one, deviates. A workspace named
    for no recorded environment — a sandbox, a second region — passes, however
    many there are: the recorded state is that every environment has its own
    workspace, not that nothing else exists, and a rule firing on a deliberate
    extra workspace teaches a team to switch it off.
    """
    return _by_name(rule, estate, lambda name, recorded: True,
                    expected=lambda recorded, named: list(recorded),
                    unique=lambda name, recorded: name in recorded)


def workspace_axis_unit(rule, estate):
    """DEC-001a's `unit` state: no workspace is named for an environment.

    Environments live inside each unit's workspace, where DEC-002 says how
    they are kept apart. A workspace named for one — `prod`, or `finance_prod` — is the environment
    axis showing through. Only the environment's own name counts: `production`
    is not `prod`.
    """
    return _by_name(rule, estate,
                    lambda name, recorded: split_name(name)[1] not in recorded)


def workspace_axis_both(rule, estate):
    """DEC-001a's `both` state: exactly one workspace per business unit and
    environment.

    Every workspace is named `<unit>_<environment>` with an environment the team
    recorded, no two share a name, and every unit so named has one in every
    recorded environment.
    """
    def follows(name, recorded):
        unit, environment = split_name(name)
        return bool(unit) and environment in recorded

    def expected(recorded, named):
        units = sorted({split_name(name)[0] for name in named if follows(name, recorded)})
        return [f"{unit}{SEPARATOR}{environment}"
                for unit in units for environment in recorded]

    return _by_name(rule, estate, follows, expected, unique=follows)


def workspace_axis_single(rule, estate):
    """DEC-001a's `single` state: the estate declares exactly one workspace.

    Its other clause — that environments and units are carried by catalog
    instead — is DEC-002's to measure, and is measured there.

    **A count deviation lands on every workspace that constitutes it.** A count
    is a property of the estate and a deviation's identity needs one resource,
    so each workspace carries its own deviation resolving the same count, and
    declaring one more creates exactly one more — the shape the gate's ratchet
    matches against.
    """
    declared = _declared(estate)
    if not declared:
        return (_disclosed(rule, estate),)

    count = len(declared)
    found = []
    for resource, name in declared:
        if not stated(name):
            found.append(_unnamed(rule, resource,
                                  f"; it is counted among the {count} this estate declares"))
        elif count == 1:
            found.append(outcomes.passed(rule, resource, name))
        else:
            found.append(outcomes.failed(rule, resource, name, count=count))
    return tuple(found)


def _by_name(rule, estate, holds, expected=None, unique=None):
    """One outcome per declared workspace, then one per expected name none has.

    `holds(name, recorded)` judges a workspace by its name. `expected(recorded,
    named)`, where a state has one, lists the names the estate must declare.
    `unique(name, recorded)` says which names the state allows only once. The
    name the UI shows is not unique in Terraform, so two blocks can claim one;
    each carries the deviation, as each workspace carries a count's.
    """
    declared = _declared(estate)
    if not declared:
        return (_disclosed(rule, estate),)
    recorded = environments_of(rule)
    if not recorded:
        # Unreachable through the analyzer, which gives a rule reading a
        # parameter nothing recorded a product-side cause. Measuring against an
        # empty list would pass every estate.
        return (outcomes.unevaluable(
            rule, outcomes.PRODUCT_SIDE,
            "this rule records no environments to read the workspaces' names against",
            root=estate.root),)

    names = [name for _, name in declared if stated(name)]
    repeated = {name for name in names
                if unique is not None and names.count(name) > 1 and unique(name, recorded)}

    found, named, unnamed = [], set(), []
    for resource, name in declared:
        if not stated(name):
            unnamed.append(resource)
            found.append(_unnamed(rule, resource))
        elif name not in repeated and holds(name, recorded):
            named.add(name)
            found.append(outcomes.passed(rule, resource, name))
        else:
            named.add(name)
            found.append(outcomes.failed(rule, resource, name, workspace=name))

    if expected is not None:
        absent = [name for name in expected(recorded, named) if name not in named]
        found.extend(_absent(rule, estate, declared, absent, unnamed))
    return tuple(found)


def _absent(rule, estate, declared, absent, unnamed):
    """A deviation per expected workspace the estate does not declare.

    Placed in the root declaring the estate's workspaces. Where one of those is
    unnamed it may be the missing one, and where more than one root declares
    them nothing says which the missing one belongs in — either way the absence
    is a non-result naming what could not be decided.
    """
    if not absent:
        return []
    if unnamed:
        return [schemas.undecided(rule, estate, absent, unnamed, "workspace")]
    roots = sorted({resource.root for resource, _ in declared})
    if len(roots) > 1:
        return [outcomes.unevaluable(
            rule, outcomes.ESTATE_SIDE,
            f"this estate declares no workspace named {listed(absent)}, and workspaces are "
            f"declared in {listed(roots)}, so the deviation cannot be placed in one of them",
            root=estate.root)]
    (root,) = roots
    return [outcomes.missing(rule, root, name, workspace=name) for name in absent]


def _declared(estate):
    """Every workspace the estate declares, of either type, with its name."""
    return [
        (resource, resource.values.get(attribute))
        for type_, attribute in WORKSPACE_TYPES.items()
        for resource in estate.of_type(type_)
    ]


def _disclosed(rule, estate):
    return outcomes.unevaluable_as_disclosed(
        rule, estate.root, otherwise=f"{estate.subject} declares no workspaces")


def _unnamed(rule, resource, counted=""):
    return outcomes.unevaluable_on(
        rule, resource,
        reason=f"the name of {resource.address} is not known at plan time, so the workspace "
               f"has no identity a deviation could be recorded against{counted}")
