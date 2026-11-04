"""The grant family: who owns a securable's grant list.

DEC-006b's two states are two provider resources with opposite postures toward
grants made elsewhere. Verified against `databricks/databricks` 1.133.0:

- `databricks_grants` is "*authoritative* for grants on securables. Configuring
  this resource for a securable will **OVERWRITE** any existing grants and
  changes made outside of Terraform will be reset."
- `databricks_grant`, singular, is authoritative "for a given *singular*
  principal", and the provider offers it "for more granular grant management".

**The subject of this decision is a securable, not a grant statement.** Two
`databricks_grant` blocks for two principals describe one grant list, so they
produce one outcome — two would be two exceptions for one fact.

**The estate address is the securable's type and its name**, because both
resources name their subject by exactly one of eighteen arguments — `catalog`,
`schema`, `table`, `share`, … — and a share called `sales` and a catalog called
`sales` are two securables with two grant lists. An estate address of the bare
name would give them one identity, and an exception approved for one would
silence the other.
"""

from wizard import outcomes
from wizard.evaluators.reading import stated

AUTHORITATIVE = "databricks_grants"
GRANULAR = "databricks_grant"

# The securable arguments both resources share, of which exactly one is required.
# A closed list rather than "whichever key is not `principal`": a provider adding
# an argument would otherwise silently become a securable type, and the estate
# address — which is identity — would move under a team that changed nothing.
SECURABLES = (
    "metastore",
    "catalog",
    "schema",
    "table",
    "volume",
    "model",
    "function",
    "secret",
    "share",
    "credential",
    "storage_credential",
    "external_location",
    "foreign_connection",
    "model_service",
    "model_provider_service",
    "mcp_service",
    "pipeline",
    "recipient",
)


def grant_authority_authoritative(rule, estate):
    """DEC-006b's `authoritative` state: the IaC layer owns the whole grant list.

    A securable deviates in either of two ways, which is why the rule's message
    is disjunctive: it is declared only granularly, so the list is not owned
    wholesale and a grant made in the UI survives every apply; or it is declared
    both ways, and then an authoritative declaration overwrites the list on every
    apply while a granular one keeps re-adding its principal, with nothing in the
    estate saying which wins.
    """
    return _per_securable(
        rule, estate,
        deviates=lambda authoritative, granular: not authoritative or granular)


def grant_authority_granular(rule, estate):
    """DEC-006b's `granular` state: only the declared grants are owned.

    An authoritative declaration resets grants made outside Terraform, which is
    the thing a team on this option recorded that they do not want — so it is a
    deviation whether or not granular declarations sit beside it.
    """
    return _per_securable(rule, estate, deviates=lambda authoritative, _: authoritative)


def _per_securable(rule, estate, deviates):
    """One outcome per securable some grant declaration in this reader names."""
    declarations = estate.of_type(AUTHORITATIVE) + estate.of_type(GRANULAR)
    if not declarations:
        return (outcomes.unevaluable_as_disclosed(
            rule, estate.root,
            otherwise=f"{estate.subject} declares no {AUTHORITATIVE} or {GRANULAR} resources"),)

    unreadable = []
    # Insertion-ordered: the first declaration naming a securable is the one the
    # outcome carries a Terraform address from. A securable declared several
    # times has no one block to point at, and the address is display only.
    securables = {}
    for resource in declarations:
        address, problem = _securable_of(rule, resource)
        if problem is not None:
            unreadable.append(problem)
            continue
        found = securables.setdefault(address, {"resource": resource, AUTHORITATIVE: False,
                                                GRANULAR: False})
        found[resource.type] = True

    found = list(unreadable)
    for address, state in securables.items():
        if deviates(state[AUTHORITATIVE], state[GRANULAR]):
            found.append(outcomes.failed(rule, state["resource"], address, securable=address))
        else:
            found.append(outcomes.passed(rule, state["resource"], address))
    return tuple(found)


def _securable_of(rule, resource):
    """`("catalog:sales", None)`, or the non-result that stands in for it."""
    # A plan carries every argument the provider declares and writes each one a
    # block does not set as `null`, so presence says nothing about which one the
    # block names. The one it names but cannot yet read is the one left out:
    # Terraform omits a value known only after apply.
    named = [key for key in SECURABLES if resource.values.get(key) is not None]
    if not named:
        if any(key not in resource.values for key in SECURABLES):
            return None, outcomes.unevaluable_on(
                rule, resource,
                reason=f"the securable named by {resource.address} is not known at plan "
                       "time, so it has no identity a deviation could be recorded against")
        # Exactly one securable argument is required of both resources. A block
        # carrying none is a shape this build cannot read, and it is the
        # estate's to fix rather than a reason to raise.
        return None, outcomes.unevaluable_on(
            rule, resource,
            reason=f"{resource.address} names no securable this build reads, so there is "
                   "nothing for the grant declaration to be about")

    key = named[0]
    name = resource.values.get(key)
    if not stated(name):
        return None, outcomes.unevaluable_on(
            rule, resource,
            reason=f"the {key} named by {resource.address} is not known at plan time, so "
                   "the securable has no identity a deviation could be recorded against")

    return f"{key}:{name}", None
