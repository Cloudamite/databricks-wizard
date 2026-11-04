"""PRE-003 and DEC-008 in the account: where managed storage is rooted, and who
shares a bucket.

The plan dialect's family (`wizard/evaluators/storage_level.py`) read against the
account's objects. Two facts, both Databricks': the storage root of each
metastore (its summary) and of each measured catalog. An account has no value
unknown until apply, so a root the account did not return is a root the object
does not have — the snapshot writes it as an absent key.

A catalog's effective root is its own, else its metastore's, and the unit of
sharing is the bucket the root names. One outcome per catalog, filed where the
catalog lives, as the plan dialect files it by name.
"""

from wizard import outcomes
from wizard.live.estate import Located, metastore_place
from wizard.naming import environments_of, listed, split_name, storage_named_by


def metastore_storage_root_absent(rule, estate):
    """PRE-003: no metastore carries a storage root, and every catalog its own."""
    if not estate.metastores and not estate.catalogs:
        return (_disclosed(rule),)
    found = []
    for metastore in estate.metastores:
        name, place = metastore["name"], Located(metastore_place(metastore["name"]))
        if metastore.get("storage_root"):
            found.append(outcomes.failed(rule, place, name, resource=f"metastore {name}"))
        else:
            found.append(outcomes.passed(rule, place, name))
    for catalog in estate.catalogs:
        if catalog.storage_root:
            found.append(outcomes.passed(rule, catalog.place, catalog.name))
        else:
            found.append(outcomes.failed(rule, catalog.place, catalog.name,
                                         resource=f"catalog {catalog.name}"))
    return tuple(found)


def catalog_buckets_unshared(rule, estate):
    """DEC-008's `one-to-one`: no two catalogs keep their storage in one bucket."""
    def message(catalog, bucket, forbidden, sharing):
        return {"resource": f"catalog {catalog.name}", "bucket": bucket,
                "catalogs": listed(f"catalog {other.name}" for other in forbidden)}

    return _per_catalog(rule, estate, lambda catalog, others: others, message)


def shared_buckets_one_environment(rule, estate):
    """DEC-008's `by-environment`: catalogs share a bucket only within an
    environment, read from a `<domain>_<environment>` name."""
    recorded = environments_of(rule)

    def environment(catalog):
        _, named = split_name(catalog.name)
        return named if named in recorded else None

    def shares(catalog, others):
        return [other for other in others if environment(other) != environment(catalog)]

    def message(catalog, bucket, forbidden, sharing):
        return {"bucket": bucket, "catalogs": listed(c.name for c in sharing)}

    return _per_catalog(rule, estate, shares, message,
                        unplaced=lambda catalog: environment(catalog) is None)


def _per_catalog(rule, estate, shares, message, unplaced=lambda catalog: False):
    """One outcome per catalog, from the bucket its effective root names.

    `shares(catalog, others)` is the catalogs in the same bucket this rule
    forbids it to share with; `message` supplies a failure's placeholders.
    """
    if not estate.catalogs:
        return (_disclosed(rule),)

    roots = {m["name"]: m.get("storage_root") for m in estate.metastores}
    found, placed, buckets = [], [], {}
    for catalog in estate.catalogs:
        if unplaced(catalog):
            found.append(outcomes.unevaluable_as_disclosed(
                rule, catalog.place.root, resource=catalog.place,
                estate_address=catalog.name,
                otherwise=f"{catalog.name} is named for no recorded environment"))
            continue
        url = catalog.storage_root or roots.get(catalog.metastore)
        if not url:
            found.append(outcomes.unevaluable_on(
                rule, catalog.place, estate_address=catalog.name,
                reason=f"the account returned no storage root for catalog {catalog.name}, nor "
                       f"for the metastore {catalog.metastore} it would inherit one from"))
            continue
        cloud, bucket = storage_named_by(url)
        if cloud is None:
            found.append(outcomes.unevaluable_on(
                rule, catalog.place, estate_address=catalog.name,
                reason=f"the storage root {url!r} of catalog {catalog.name} is on a scheme this "
                       "build does not read, so the bucket behind it cannot be named"))
            continue
        buckets.setdefault(bucket, []).append(catalog)
        placed.append((catalog, bucket))

    for catalog, bucket in placed:
        forbidden = shares(catalog, [c for c in buckets[bucket] if c is not catalog])
        if forbidden:
            found.append(outcomes.failed(rule, catalog.place, catalog.name,
                                         **message(catalog, bucket, forbidden,
                                                   buckets[bucket])))
        else:
            found.append(outcomes.passed(rule, catalog.place, catalog.name))
    return tuple(found)


def _disclosed(rule):
    return outcomes.unevaluable_as_disclosed(
        rule, None, otherwise="the account returned no metastore and no catalog the audit "
                              "measures")
