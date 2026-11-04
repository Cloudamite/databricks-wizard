"""Which evaluators this build implements, and where each read its fingerprint.

An evaluator is the code a rule's `evaluator` handle names: it is handed the
compiled rule and a reader over the estate, and it returns outcomes.

**This is a package rather than a module**, and the split is by decision family
— `catalogs.py` reads catalogs and their bindings, and its siblings read what
their own decisions are about. The registry stays here, in one place, because
its being closed is a property the product guarantees, and a table spread
across seven files is one nothing can check. The helpers every family shares are
in `reading.py`, not here, so that a family importing them does not close a
cycle through this module.

**A handle names one target state, not one family of resources.** The write
hoists the chosen option's rule into the ADR set without its key, so by the time
the analyzer reads it the handle is the only thing left saying what was
expected. `catalog_isolation_open` and `catalog_isolation_isolated` read the
same resource type and disagree about what it should say; sharing a handle would
make the analyzer report a deviation against whichever state the team did not
choose. The corpus validity table carries the rule that keeps an entry's states
apart.

**The table is closed and shipped.** No ADR set, corpus entry, plugin path,
argument or environment variable extends it. That is not
the argument made for the closed cloud vocabulary: here it keeps
arbitrary code out of a command pointed at the configuration of a production
data platform, and an evaluator loaded from a path named in an ADR set would
make the set — a document a team edits by hand and merges — executable.

**This build implements every handle the corpus names.** So the installation-side
case compilation attributes is now a version mismatch — a set written by a newer
product, naming a handle this build does not have — rather than a gap this
product is carrying. A registry naming an implementation that does not exist
would make compilation claim a rule is evaluable when nothing can evaluate it,
which is why the table and the code it resolves to move together.

An evaluator raises for nothing the estate does. A missing resource, a missing
attribute, an attribute of an unexpected type, a value that is null because it
is unknown until apply — each is an UNEVALUATED outcome with a reason. Raising
is reserved for a defect in this product, and `evaluation.py` contains it.
"""

from wizard.evaluators import (
    axis, catalogs, credential_level, grants, ownership, protection, schemas, storage,
    storage_level, workspaces,
)

# The table. One entry per target state this build can measure, keyed by the
# handle the corpus names. A mapping rather than a set, because a handle
# resolves to the code that runs it; `rules.py` asks only whether it is here.
IMPLEMENTED = {
    "catalog_isolation_isolated": catalogs.catalog_isolation_isolated,
    "catalog_isolation_open": catalogs.catalog_isolation_open,
    "grant_authority_authoritative": grants.grant_authority_authoritative,
    "grant_authority_granular": grants.grant_authority_granular,
    "workspace_axis_environment": workspaces.workspace_axis_environment,
    "workspace_axis_unit": workspaces.workspace_axis_unit,
    "workspace_axis_both": workspaces.workspace_axis_both,
    "workspace_axis_single": workspaces.workspace_axis_single,
    "storage_root_versioning_disabled": storage.storage_root_versioning_disabled,
    "storage_root_versioning_bounded": storage.storage_root_versioning_bounded,
    "destroy_protection_uniform": protection.destroy_protection_uniform,
    "catalog_managed_by_iac": catalogs.catalog_managed_by_iac,
    "catalog_axis_environment": axis.catalog_axis_environment,
    "catalog_axis_domain": axis.catalog_axis_domain,
    "catalog_axis_both": axis.catalog_axis_both,
    "schema_layer_per_schema": schemas.schema_layer_per_schema,
    "schema_layer_in_table_name": schemas.schema_layer_in_table_name,
    "destroy_protection_protected": protection.destroy_protection_protected,
    "catalog_isolation_read_only": catalogs.catalog_isolation_read_only,
    "metastore_storage_root_absent": storage_level.metastore_storage_root_absent,
    "catalog_buckets_unshared": storage_level.catalog_buckets_unshared,
    "shared_buckets_one_environment": storage_level.shared_buckets_one_environment,
    "catalog_identities_unshared": credential_level.catalog_identities_unshared,
    "shared_identities_one_environment": credential_level.shared_identities_one_environment,
    "unity_catalog_owned_by_group": ownership.unity_catalog_owned_by_group,
}

# Where each implemented fingerprint was read, and at which version.
#
# This is the Terraform dialect, so the keys are provider addresses. It carries
# **only implemented evaluators**: a version recorded against a fingerprint no
# code implements is a claim nobody verified, and the corpus used to make
# sixteen of them. The product requires every
# platform fact to be recorded against the version it was verified on, and a
# resource type is a platform fact — so it is recorded here, beside the code
# that reads it, rather than in the ADR set, which names no resource type at all.
# A workspace is a different resource type on Azure than on AWS and GCP, so
# the three topology handles read two providers and record both.
WORKSPACE_PROVIDERS = {"databricks/databricks": "1.133.0", "hashicorp/azurerm": "5.6.0"}

# The storage root is a Databricks fact and the versioning of the storage it
# names is the cloud provider's, so these handles read four providers.
STORAGE_PROVIDERS = {
    "databricks/databricks": "1.133.0",
    "hashicorp/aws": "6.66.0",
    "hashicorp/google": "8.4.0",
    "hashicorp/azurerm": "5.6.0",
}

VERIFIED_AGAINST = {
    "catalog_isolation_isolated": {"databricks/databricks": "1.133.0"},
    "catalog_isolation_open": {"databricks/databricks": "1.133.0"},
    "grant_authority_authoritative": {"databricks/databricks": "1.133.0"},
    "grant_authority_granular": {"databricks/databricks": "1.133.0"},
    "workspace_axis_environment": WORKSPACE_PROVIDERS,
    "workspace_axis_unit": WORKSPACE_PROVIDERS,
    "workspace_axis_both": WORKSPACE_PROVIDERS,
    "workspace_axis_single": WORKSPACE_PROVIDERS,
    "storage_root_versioning_disabled": STORAGE_PROVIDERS,
    "storage_root_versioning_bounded": STORAGE_PROVIDERS,
    "destroy_protection_uniform": {"databricks/databricks": "1.133.0"},
    "catalog_managed_by_iac": {"databricks/databricks": "1.133.0"},
    "catalog_axis_environment": {"databricks/databricks": "1.133.0"},
    "catalog_axis_domain": {"databricks/databricks": "1.133.0"},
    "catalog_axis_both": {"databricks/databricks": "1.133.0"},
    "schema_layer_per_schema": {"databricks/databricks": "1.133.0"},
    "schema_layer_in_table_name": {"databricks/databricks": "1.133.0"},
    "destroy_protection_protected": {"databricks/databricks": "1.133.0"},
    "catalog_isolation_read_only": {"databricks/databricks": "1.133.0"},
    "metastore_storage_root_absent": {"databricks/databricks": "1.133.0"},
    "catalog_buckets_unshared": {"databricks/databricks": "1.133.0"},
    "shared_buckets_one_environment": {"databricks/databricks": "1.133.0"},
    "catalog_identities_unshared": {"databricks/databricks": "1.133.0"},
    "shared_identities_one_environment": {"databricks/databricks": "1.133.0"},
    "unity_catalog_owned_by_group": {"databricks/databricks": "1.133.0"},
}


def implements(evaluator):
    """Whether this build can evaluate rules naming `evaluator`."""
    return evaluator in IMPLEMENTED


def implementation(evaluator):
    """The code `evaluator` names. Callers check `implements` first."""
    return IMPLEMENTED[evaluator]
