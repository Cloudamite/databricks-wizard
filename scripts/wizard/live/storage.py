"""PRE-001 in the account: the storage behind each metastore's storage roots.

The storage roots are Databricks facts: the metastore's, each measured
catalog's and each of their schemas'. `storage_roots`
names them, and the reader reads the S3 bucket behind each, so neither can
read a bucket the other does not ask about.

Versioning is a setting of the bucket, so roots sharing one are one outcome,
filed under its metastore with the bucket as its estate address, and answered
from the bucket's reading in the snapshot:

- `disabled` holds when versioning was never enabled or is suspended;
- `bounded` holds when versioning is enabled and an enabled lifecycle rule,
  reaching every root in the bucket, keeps at most 3 noncurrent versions for at
  most 7 days.

A snapshot read with `--no-storage` has no readings, and each bucket is
coverage-side: the team supplies it by reading again. Storage on Azure or GCP is
not read by this build, and is installation-side.
"""

from wizard import outcomes
from wizard.live.estate import ENABLED, Located, metastore_place
from wizard.naming import AWS, AZURE, GCP, listed, storage_named_by, within_the_bound

CLOUD_NAMES = {AZURE: "Azure", GCP: "GCP"}


def storage_roots(estate):
    """`{metastore: [(object, url), ...]}`: each storage root the audit
    measures, by the metastore it is on. A metastore where none has a root maps
    to an empty list."""
    found = {}
    for metastore in estate.metastores:
        name = metastore["name"]
        roots = [(f"metastore {name}", metastore.get("storage_root"))]
        for catalog in estate.catalogs:
            if catalog.metastore == name:
                roots.append((f"catalog {catalog.name}", catalog.storage_root))
                roots += [(f"schema {catalog.name}.{schema.name}", schema.storage_root)
                          for schema in catalog.schemas]
        found[name] = [(held, url) for held, url in roots if url]
    return found


def s3_buckets(estate):
    """Every S3 bucket behind a storage root the audit measures, sorted."""
    found = set()
    for roots in storage_roots(estate).values():
        for _, url in roots:
            cloud, bucket = storage_named_by(url)
            if cloud == AWS:
                found.add(bucket)
    return sorted(found)


def unread_buckets(estate):
    """Each bucket behind a measured `s3://` root with no reading, in a
    snapshot that read storage. The reader writes none."""
    if estate.buckets is None:
        return []
    return [f"  {bucket}: behind a storage root the audit measures, and with no reading"
            for bucket in s3_buckets(estate) if bucket not in estate.buckets]


def storage_root_versioning_disabled(rule, estate):
    return _per_bucket(rule, estate, _disabled)


def storage_root_versioning_bounded(rule, estate):
    return _per_bucket(rule, estate, _bounded)


def _per_bucket(rule, estate, verdict):
    found = []
    for metastore, roots in storage_roots(estate).items():
        place = Located(metastore_place(metastore))
        if not roots:
            found.append(outcomes.unevaluable(
                rule, outcomes.ESTATE_SIDE,
                f"the account returned no storage root for the metastore {metastore}, nor for "
                "any catalog or schema the audit measures on it",
                root=place.root))
            continue

        buckets = {}
        for held, url in roots:
            cloud, bucket = storage_named_by(url)
            if cloud is None:
                found.append(outcomes.unevaluable(
                    rule, outcomes.ESTATE_SIDE,
                    f"the storage root {url!r} of {held} is on a scheme this build does not "
                    "read, so the storage behind it cannot be found",
                    root=place.root))
            else:
                buckets.setdefault((cloud, bucket), []).append((held, url))
        found += [_answered(rule, estate, place, cloud, bucket, using, verdict)
                  for (cloud, bucket), using in sorted(buckets.items())]
    return tuple(found)


def _answered(rule, estate, place, cloud, bucket, using, verdict):
    objects = listed(held for held, _ in using)
    if cloud != AWS:
        return outcomes.unevaluable_on(
            rule, place, estate_address=bucket, cause=outcomes.INSTALLATION_SIDE,
            reason=f"{bucket}, behind the storage root of {objects}, is {CLOUD_NAMES[cloud]} "
                   "storage, which this build does not read")
    if estate.buckets is None:
        return outcomes.unevaluable_on(
            rule, place, estate_address=bucket, cause=outcomes.COVERAGE_SIDE,
            reason=f"storage was not read: the snapshot was read with --no-storage, so "
                   f"{bucket}, behind the storage root of {objects}, has no reading; reading "
                   "the account again without --no-storage, with an AWS credential that "
                   f"reaches {bucket}, supplies it")
    return verdict(rule, place, bucket, objects, estate.buckets[bucket],
                   [_path_in_bucket(url) for _, url in using])


def _disabled(rule, place, bucket, objects, reading, paths):
    if reading.get("versioning") == ENABLED:
        return outcomes.failed(rule, place, bucket, bucket=bucket, objects=objects)
    return outcomes.passed(rule, place, bucket)


def _bounded(rule, place, bucket, objects, reading, paths):
    """Off is a deviation from this state too: it is the prescription's other
    alternative, a different ADR than the one the team holds."""
    if reading.get("versioning") == ENABLED and any(
            _bounds(entry, paths) for entry in reading.get("lifecycle_rules", ())):
        return outcomes.passed(rule, place, bucket)
    return outcomes.failed(rule, place, bucket, bucket=bucket, objects=objects)


def _bounds(entry, paths):
    """Whether one lifecycle rule bounds the noncurrent versions under every
    root in `paths`: enabled, filtered to nothing or to a prefix alone that
    each root lies under, and carrying both of PRE-001's bounds."""
    if entry.get("Status") != ENABLED:
        return False
    prefix = _prefix_of(entry)
    if prefix is None or not all(f"{path}/".startswith(prefix) for path in paths):
        return False
    expiration = entry.get("NoncurrentVersionExpiration") or {}
    return within_the_bound(expiration.get("NewerNoncurrentVersions"),
                            expiration.get("NoncurrentDays"))


def _prefix_of(entry):
    """The prefix a rule applies to — `""` for the whole bucket — or `None` for
    a filter on tags, object size, or a combination, which bounds only some of
    the objects under a root."""
    if "Filter" in entry:
        condition = entry["Filter"] or {}
        if not condition:
            return ""
        return condition["Prefix"] if set(condition) == {"Prefix"} else None
    return entry.get("Prefix", "")


def _path_in_bucket(url):
    """`main-eu` for `s3://acme-uc/main-eu/`: the root's key prefix, without
    its trailing slash; empty for a root at the top of the bucket."""
    rest = url.partition("://")[2]
    return rest.partition("/")[2].rstrip("/")
