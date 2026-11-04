"""The storage-level family: where managed storage is rooted, and who shares a bucket.

PRE-003 and DEC-008. Both read the same two facts — the `storage_root` of the
metastore and of each catalog, and the bucket a root names — and neither reads
anything the cloud provider holds about that bucket, which is PRE-001's
business.

- `databricks_metastore.storage_root` and `databricks_catalog.storage_root`,
  each optional and **not computed** (`databricks/databricks` 1.133.0,
  `terraform providers schema -json`). So a root the block does not set plans
  as `null`, and a root absent from `values` is one unknown until apply. The
  two are different facts here, unlike in most families: `null` is *declares
  none*, which PRE-003 asks of the metastore, and absent is no verdict.

**The unit is the bucket, not the path.** Two catalogs at different prefixes of
one bucket have different storage roots and one bucket-wide key, policy,
versioning and Object Lock, which is what isolation is for.

**A catalog's effective root is measured**: its own, else the metastore's.
Catalogs inheriting one metastore root share its bucket, so DEC-008's rules read
the layout the files actually take, whatever PRE-003 was answered.

**One outcome per catalog**, filed by its name. Sharing is a relation between
catalogs, and the catalog is what a team moves to resolve it; an outcome per
bucket would leave the deviation without the thing to act on.

Only managed catalogs are read. A catalog read through a data source is declared
elsewhere, and its storage is not this estate's to root.
"""

from wizard import outcomes
from wizard.evaluators.reading import declared, metastore_root, stated
from wizard.naming import environments_of, listed, split_name, storage_named_by

METASTORE = "databricks_metastore"
CATALOG = "databricks_catalog"


def metastore_storage_root_absent(rule, estate):
    """PRE-003: the metastore declares no storage root, and every catalog its own.

    The metastore is the account's and usually created outside the estate. Where
    it is not declared, its clause is the disclosed non-result and the catalogs
    are still measured — the rule's two clauses are about different resources,
    and one being unreadable says nothing about the other.
    """
    metastores, catalogs = declared(estate, METASTORE), declared(estate, CATALOG)
    found = []
    if not metastores:
        found.append(_disclosed(rule, estate))
    for metastore in metastores:
        found.append(_rooted(rule, metastore, holds=lambda root: root is None))
    for catalog in catalogs:
        found.append(_rooted(rule, catalog, holds=lambda root: root is not None))
    return tuple(found)


def catalog_buckets_unshared(rule, estate):
    """DEC-008's `one-to-one`: no two catalogs keep their storage in one bucket."""
    def message(catalog, bucket, forbidden, sharing):
        return {"resource": f"catalog {catalog.values['name']}", "bucket": bucket,
                "catalogs": listed(f"catalog {other.values['name']}" for other in forbidden)}

    return _per_catalog(rule, estate, lambda catalog, others: others, message)


def shared_buckets_one_environment(rule, estate):
    """DEC-008's `by-environment`: catalogs share a bucket only within an environment.

    The environment is read from the catalog's name as DEC-002's `both` answer
    names it, `<domain>_<environment>`, against the environments the set
    recorded — the one axis this option is offered under.
    """
    recorded = environments_of(rule)

    def shares(catalog, others):
        mine = _environment(catalog, recorded)
        return [other for other in others if _environment(other, recorded) != mine]

    def message(catalog, bucket, forbidden, sharing):
        return {"bucket": bucket, "catalogs": listed(_names(sharing))}

    return _per_catalog(rule, estate, shares, message,
                        unplaced=lambda catalog: _environment(catalog, recorded) is None)


def _per_catalog(rule, estate, shares, message, unplaced=lambda catalog: False):
    """One outcome per catalog, from the bucket its effective root names.

    `shares(catalog, others)` is the catalogs among those in the same bucket
    that this rule forbids it to share with; none means the catalog conforms.
    `message` supplies a failure's placeholders.
    """
    catalogs = declared(estate, CATALOG)
    if not catalogs:
        return (_disclosed(rule, estate),)

    inherited, inheritable = metastore_root(estate)
    found, buckets, placed = [], {}, []
    for catalog in catalogs:
        name = catalog.values.get("name")
        if not stated(name):
            found.append(outcomes.unevaluable_on(
                rule, catalog,
                reason=f"{catalog.address} has no name known at plan time, so whether it "
                       "shares a bucket cannot be said of any catalog"))
            continue
        if unplaced(catalog):
            found.append(_disclosed(rule, estate, catalog, name))
            continue
        if "storage_root" not in catalog.values:
            found.append(_disclosed(rule, estate, catalog, name))
            continue
        url = catalog.values["storage_root"]
        if url is None:
            if not inheritable:
                found.append(_disclosed(rule, estate, catalog, name))
                continue
            url = inherited
            if url is None:
                found.append(outcomes.unevaluable_on(
                    rule, catalog, estate_address=name,
                    reason=f"catalog {name} declares no storage root and neither does the "
                           "metastore, so this estate does not say where its storage is"))
                continue
        cloud, bucket = storage_named_by(url) if stated(url) else (None, None)
        if cloud is None:
            found.append(outcomes.unevaluable_on(
                rule, catalog, estate_address=name,
                reason=f"the storage root {url!r} of catalog {name} is on a scheme this build "
                       "does not read, so the bucket behind it cannot be named"))
            continue
        buckets.setdefault(bucket, []).append(catalog)
        placed.append((catalog, name, bucket))

    for catalog, name, bucket in placed:
        others = [other for other in buckets[bucket] if other is not catalog]
        forbidden = shares(catalog, others)
        if not forbidden:
            found.append(outcomes.passed(rule, catalog, name))
            continue
        found.append(outcomes.failed(rule, catalog, name,
                                     **message(catalog, bucket, forbidden, buckets[bucket])))
    return tuple(found)


def _rooted(rule, resource, holds):
    """PRE-003's verdict on one resource, from whether it declares a root."""
    kind = resource.type.removeprefix("databricks_")
    name = resource.values.get("name")
    address = name if stated(name) else None
    if "storage_root" not in resource.values:
        return outcomes.unevaluable_as_disclosed(
            rule, resource.root, otherwise=f"the storage root of {resource.address} is unknown "
                                           "until apply",
            resource=resource, estate_address=address)
    if address is None:
        return outcomes.unevaluable_on(
            rule, resource,
            reason=f"{resource.address} has no name known at plan time, so the {kind} this "
                   "verdict would be about cannot be named")
    root = resource.values["storage_root"]
    root = root if stated(root) else None
    if holds(root):
        return outcomes.passed(rule, resource, address)
    return outcomes.failed(rule, resource, address, resource=f"{kind} {address}")


def _environment(catalog, recorded):
    """The recorded environment a `<domain>_<environment>` name ends in, or `None`."""
    _, environment = split_name(catalog.values["name"])
    return environment if environment in recorded else None


def _names(catalogs):
    return [catalog.values["name"] for catalog in catalogs]


def _disclosed(rule, estate, resource=None, estate_address=None):
    return outcomes.unevaluable_as_disclosed(
        rule, estate.root,
        otherwise=f"{estate.subject} does not say where this storage is rooted",
        resource=resource, estate_address=estate_address)
