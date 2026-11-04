"""PRE-004: Unity Catalog is owned by a group the team names.

Five types carry an `owner` (`databricks/databricks` 1.133.0, `terraform providers
schema -json`): the metastore, storage credentials, external locations, catalogs
and schemas. On each it is optional and **computed**: a block that sets none plans
the owner as unknown, and the provider then records whoever created the object.
That is the very case this rule exists for, so an owner the plan does not state is
a deviation, not a non-result: the block names no group, and the creator will own
it. An owner computed from another unknown value reads the same, and is named the
same way; the scaffold states every owner as a literal.

One outcome per securable, filed by what names it in the account: a schema by
its catalog and its own name. Securables read through a data source are not this
root's to own.
"""

from wizard import outcomes
from wizard.evaluators.reading import declared, stated
from wizard.naming import recorded

OWNER_GROUP = "owner_group"
OWNED = {
    "databricks_metastore": "metastore",
    "databricks_storage_credential": "storage credential",
    "databricks_external_location": "external location",
    "databricks_catalog": "catalog",
    "databricks_schema": "schema",
}


def unity_catalog_owned_by_group(rule, estate):
    """Every securable this root declares is owned by a group the set records."""
    groups = recorded(rule, OWNER_GROUP)
    found = []
    for kind, noun in OWNED.items():
        for resource in declared(estate, kind):
            name = _name(resource)
            if resource.values.get("owner") in groups:
                found.append(outcomes.passed(rule, resource, f"{noun} {name}"))
            else:
                found.append(outcomes.failed(rule, resource, f"{noun} {name}",
                                             resource=f"{noun} {name}"))
    if not found:
        found.append(outcomes.unevaluable_as_disclosed(
            rule, estate.root, otherwise=f"{estate.subject} declares no Unity Catalog "
                                         "securable"))
    return tuple(found)


def _name(resource):
    values = resource.values
    name = values.get("name") if stated(values.get("name")) else resource.address
    if resource.type == "databricks_schema" and stated(values.get("catalog_name")):
        return f"{values['catalog_name']}.{name}"
    return name
