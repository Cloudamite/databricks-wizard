"""The storage family: object versioning on the storage behind the storage roots.

PRE-001, the one entry fingerprinted outside the Databricks provider. Two reads
joined by a URL: the Unity Catalog storage roots, which are Databricks facts, and
the versioning state of the storage they name, which is the cloud provider's.

- `databricks_metastore.storage_root` — "Path on cloud storage account, where
  managed `databricks_table` are stored" — and `databricks_catalog.storage_root`
  and `databricks_schema.storage_root`, each an optional string
  (`databricks/databricks` 1.133.0, `terraform providers schema -json`)
- `aws_s3_bucket_versioning.versioning_configuration.status` — "Versioning state
  of the bucket", one of `Enabled`, `Suspended`, `Disabled`; and
  `aws_s3_bucket_lifecycle_configuration`, whose `noncurrent_version_expiration`
  carries `noncurrent_days` and `newer_noncurrent_versions` (`hashicorp/aws`
  6.66.0)
- `google_storage_bucket.versioning.enabled` — "While set to `true`, versioning
  is fully enabled for this bucket" — and `lifecycle_rule.condition`'s
  `num_newer_versions` and `days_since_noncurrent_time` (`hashicorp/google` 8.4.0)
- `azurerm_storage_account.blob_properties.versioning_enabled`
  (`hashicorp/azurerm` 5.6.0)

**Every managed storage location is joined, and no external location.** Unity
Catalog keeps managed storage at the metastore's, a catalog's and a schema's
storage root, and Databricks recommends the catalog's for isolating catalogs, so
all three are read (issue #31). An
external location is any location a team registers, and measuring them all would
report a deviation on a landing-zone bucket whose versioning is nobody's
business — the *rule fires on a legitimate configuration* failure, which is
worse than no rule at all. The audit describes the join through
`databricks_external_location.url`; the narrower one is what the rule's own words
ask for, which is the storage backing the storage root.

**One outcome per bucket.** Versioning is a setting of the bucket, so roots that
share one are one outcome: filed by the broadest object using it, naming every
one, with the bucket as its estate address — the address the metastore-only
evaluator gave, so its identities, and the exceptions recorded against them,
are unchanged.

**UNEVALUATED is this entry's normal outcome rather than an edge case**, as the
audit records: the bucket is frequently in a different Terraform state from the
metastore, and then this estate cannot see it. The rule discloses that before it
is answered.
"""

from wizard import outcomes
from wizard.evaluators.reading import stated
from wizard.naming import (
    AWS, AZURE, GCP, MOST_VERSIONS, listed, storage_named_by, within_the_bound,
)

# Broadest first: a bucket is filed by the first of these that uses it.
STORAGE_ROOTS = ("databricks_metastore", "databricks_catalog", "databricks_schema")

# `Enabled` is the only documented status that means versioning is on. A status
# outside the documented three was read and not understood, and no verdict rests
# on it.
S3_STATUSES = {"Enabled": True, "Suspended": False, "Disabled": False}


def storage_root_versioning_disabled(rule, estate):
    """PRE-001's `disabled` alternative: versioning is not enabled on the storage.

    Delta keeps its own version history in the transaction log, so the storage
    layer's versioning is a second, uncoordinated copy of the same idea: VACUUM
    deletes files the storage layer then retains as noncurrent versions, and
    those are neither readable as Delta history nor reclaimed by it.
    """
    return _per_storage_root(rule, estate, verdict=_disabled)


def storage_root_versioning_bounded(rule, estate):
    """PRE-001's `bounded` alternative: versioning on, ≤3 versions, ≤7 days.

    An estate with versioning switched off deviates from this too. It is in the
    prescription's other alternative, which is a different ADR than the one the
    team holds, and the report is where a set and an estate that have drifted
    apart are brought back together.
    """
    return _per_storage_root(rule, estate, verdict=_bounded)


def _per_storage_root(rule, estate, verdict):
    """One outcome per bucket behind the storage roots the estate declares."""
    declared = [
        (resource, resource.values.get("storage_root"))
        for kind in STORAGE_ROOTS
        for resource in sorted(estate.of_type(kind), key=_object)
    ]
    declared = [(resource, url) for resource, url in declared if stated(url)]
    if not declared:
        return (_disclosed(rule, estate),)

    found, buckets = [], {}
    for resource, url in declared:
        cloud, name = storage_named_by(url)
        if cloud is None:
            found.append(outcomes.unevaluable_on(
                rule, resource,
                reason=f"the storage root {url!r} is on a scheme this build does not read, "
                       "so the storage behind it cannot be found"))
            continue
        buckets.setdefault((cloud, name), []).append(resource)

    for (cloud, name), using in buckets.items():
        resource, objects = using[0], listed(_object(r) for r in using)
        state, unreadable = _versioning_of(rule, estate, cloud, name, resource, objects)
        if unreadable is not None:
            found.append(unreadable)
            continue

        found.append(verdict(rule, estate, resource, cloud, name, objects, state))
    return tuple(found)


def _object(resource):
    """`metastore main`, `catalog sales`, `schema sales.bronze` — by the
    Terraform address where the name is not known at plan time. Within one
    kind, it is also the order that decides which object files a bucket."""
    values = resource.values
    name = values.get("name")
    if not stated(name):
        name = resource.address
    elif resource.type == "databricks_schema" and stated(values.get("catalog_name")):
        name = f"{values['catalog_name']}.{name}"
    return f"{resource.type.removeprefix('databricks_')} {name}"


def _disabled(rule, estate, resource, cloud, name, objects, enabled):
    if not enabled:
        return outcomes.passed(rule, resource, name)
    return outcomes.failed(rule, resource, name, bucket=name, objects=objects)


def _bounded(rule, estate, resource, cloud, name, objects, enabled):
    if not enabled:
        return outcomes.failed(rule, resource, name, bucket=name, objects=objects)

    if cloud == AZURE:
        # Azure bounds noncurrent versions by age, through a management policy,
        # and has no equivalent of *keep at most three*. Half a bound is not the
        # recorded state, and either verdict would claim to have read something
        # this build cannot.
        return outcomes.unevaluable_on(
            rule, resource, estate_address=name,
            reason=f"versioning is enabled on {name}, behind the storage root of {objects}, "
                   f"and this build cannot read a bound of at most {MOST_VERSIONS} versions "
                   "on Azure, which expresses no such limit")

    if _bounded_by_a_policy(estate, cloud, name):
        return outcomes.passed(rule, resource, name)
    return outcomes.failed(rule, resource, name, bucket=name, objects=objects)


def _disclosed(rule, estate):
    return outcomes.unevaluable_as_disclosed(
        rule, estate.root,
        otherwise=f"the storage backing the storage root is not declared in {estate.subject}")


def _versioning_of(rule, estate, cloud, name, at, objects):
    """Whether versioning is on, or the non-result standing in for the answer."""
    if cloud == AWS:
        for resource in estate.of_type("aws_s3_bucket_versioning"):
            if resource.values.get("bucket") != name:
                continue
            status = _first(resource.values.get("versioning_configuration")).get("status")
            if status not in S3_STATUSES:
                return None, outcomes.unevaluable_on(
                    rule, at, estate_address=name,
                    reason=f"{name}, behind the storage root of {objects}, declares a "
                           f"versioning status of {status!r}, which is not one this build reads")
            return S3_STATUSES[status], None

    if cloud == GCP:
        for resource in estate.of_type("google_storage_bucket"):
            if resource.values.get("name") == name:
                return _stated_flag(
                    rule, estate, _first(resource.values.get("versioning")).get("enabled"))

    if cloud == AZURE:
        for resource in estate.of_type("azurerm_storage_account"):
            if resource.values.get("name") == name:
                return _stated_flag(
                    rule, estate,
                    _first(resource.values.get("blob_properties")).get("versioning_enabled"))

    return None, _disclosed(rule, estate)


def _stated_flag(rule, estate, enabled):
    """A versioning flag the estate actually expresses, or the disclosed non-result.

    A bucket declaring no versioning setting is the second half of what this
    rule discloses, and it is not the same fact as one declaring versioning off:
    the provider's default is not a choice the team expressed, and the bucket
    could have been changed outside Terraform. Reading an absent block as *off*
    would hand a PASS to an estate nobody read.
    """
    if not isinstance(enabled, bool):
        return None, _disclosed(rule, estate)
    return enabled, None


def _bounded_by_a_policy(estate, cloud, name):
    """Whether some lifecycle policy keeps noncurrent versions within the bounds."""
    if cloud == AWS:
        return any(
            within_the_bound(expiration.get("newer_noncurrent_versions"),
                    expiration.get("noncurrent_days"))
            for resource in estate.of_type("aws_s3_bucket_lifecycle_configuration")
            if resource.values.get("bucket") == name
            for entry in resource.values.get("rule") or []
            for expiration in entry.get("noncurrent_version_expiration") or []
        )

    return any(
        within_the_bound(condition.get("num_newer_versions"),
                condition.get("days_since_noncurrent_time"))
        for resource in estate.of_type("google_storage_bucket")
        if resource.values.get("name") == name
        for entry in resource.values.get("lifecycle_rule") or []
        for condition in entry.get("condition") or []
    )


def _first(block):
    """The first entry of a plan's block list, or an empty mapping.

    A nested configuration block arrives as a list of mappings, and a block the
    team did not write arrives as an empty list or not at all.
    """
    if isinstance(block, list) and block and isinstance(block[0], dict):
        return block[0]
    return {}
