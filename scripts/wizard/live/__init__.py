"""The audit's evaluators, and the registry that says which handle each answers.

The audit measures the live account against the ADR set with evaluators of its
own, written against the account's objects. It shares the product's decisions, compiled rules,
outcomes, identity and report, and nothing that reads a plan: no module here
imports `wizard.evaluators` or `wizard.plan`.

**Every handle the corpus names on a rule the audit considers is answered.**
A rule bound to another substrate is not considered, and nor is a declined handle: one the shipped corpus binds to
another substrate, which a set written before its rule said so carries without
`substrates`. A handle in neither table is one this build does not know, and
compiles installation-side.
"""

from wizard.live import (
    catalogs, credential_level, names, ownership, storage, storage_level, workspaces,
)

LIVE = {
    "workspace_axis_environment": workspaces.workspace_axis_environment,
    "workspace_axis_unit": workspaces.workspace_axis_unit,
    "workspace_axis_both": workspaces.workspace_axis_both,
    "workspace_axis_single": workspaces.workspace_axis_single,
    "catalog_isolation_open": catalogs.catalog_isolation_open,
    "catalog_isolation_isolated": catalogs.catalog_isolation_isolated,
    "catalog_isolation_read_only": catalogs.catalog_isolation_read_only,
    "catalog_axis_environment": names.catalog_axis_environment,
    "catalog_axis_domain": names.catalog_axis_domain,
    "catalog_axis_both": names.catalog_axis_both,
    "schema_layer_per_schema": names.schema_layer_per_schema,
    "schema_layer_in_table_name": names.schema_layer_in_table_name,
    "storage_root_versioning_disabled": storage.storage_root_versioning_disabled,
    "storage_root_versioning_bounded": storage.storage_root_versioning_bounded,
    "metastore_storage_root_absent": storage_level.metastore_storage_root_absent,
    "catalog_buckets_unshared": storage_level.catalog_buckets_unshared,
    "shared_buckets_one_environment": storage_level.shared_buckets_one_environment,
    "catalog_identities_unshared": credential_level.catalog_identities_unshared,
    "shared_identities_one_environment": credential_level.shared_identities_one_environment,
    "unity_catalog_owned_by_group": ownership.unity_catalog_owned_by_group,
}

# PRE-002's rule declared no `substrates` before 2026-10-05: an account
# records no tool that created a catalog.
DECLINED = frozenset({"catalog_managed_by_iac"})


def answers(handle):
    """Whether this build has a live evaluator for `handle`. A declined handle
    has none, and is never evaluated (`evaluation.considered`)."""
    return handle in LIVE
