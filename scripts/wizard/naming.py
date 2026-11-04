"""What both dialects need: statements about names and recorded parameters.

The Terraform evaluators (`wizard/evaluators/`) and the audit's (`wizard/live/`)
measure the same decisions on different objects, and share nothing else. What they do share is here: how a
name splits into its axis parts, what a rule recorded, what a storage root URL
names, and PRE-001's bound on noncurrent versions. None of it is about a plan or
an account.
"""

# What separates a domain, a business unit or a layer from the rest of a name.
# One character, fixed by the product and stated on the card that asks for the
# environments, because a convention every team follows exactly is the only
# thing that makes an estate measurable without asking for every name.
SEPARATOR = "_"

ENVIRONMENTS = "environments"
LAYERS = "layers"

AWS, GCP, AZURE = "aws", "gcp", "azure"


def split_name(name):
    """`(prefix, environment)` — a name read as `<prefix>_<environment>`.

    The prefix is empty for a bare name, and the environment half is whatever
    follows the last separator, recorded or not — which it is, is the caller's
    question.
    """
    prefix, _, environment = name.rpartition(SEPARATOR)
    return prefix, environment


def recorded(rule, name):
    """What the set recorded under `name`, in the order the team gave it.

    Environments are given least to most production-like, so the last is
    production.
    """
    return tuple(dict(rule.parameters).get(name) or ())


def environments_of(rule):
    """The environments the set recorded, in the order the team gave them."""
    return recorded(rule, ENVIRONMENTS)


def named_for(name, environment):
    """Whether a catalog is named for `environment`, under the environment axis
    (`prod`) or under both (`orders_prod`)."""
    return name == environment or name.endswith(f"{SEPARATOR}{environment}")


def listed(names):
    """`a`, `a and b`, `a, b and c` — sorted, for a sentence to carry."""
    names = sorted(names)
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"


def storage_named_by(url):
    """The cloud and the name of the storage a storage-root URL points at.

    `s3://bucket/path`, `gs://bucket/path` and
    `abfss://container@account.dfs.core.windows.net/path`. Azure names a
    container on a storage account, and versioning is a property of the
    account, so it is the account this returns.
    """
    scheme, _, rest = url.partition("://")
    if not rest:
        return None, None
    host = rest.split("/", 1)[0]
    if scheme == "s3":
        return AWS, host
    if scheme == "gs":
        return GCP, host
    if scheme == "abfss":
        _, _, account = host.partition("@")
        return (AZURE, account.split(".", 1)[0]) if account else (None, None)
    return None, None


# The vendor's own graded fallback, quoted in PRE-001: "retaining three versions
# and implementing a lifecycle management policy that retains versions for 7 days
# or less".
MOST_VERSIONS = 3
MOST_DAYS = 7


def within_the_bound(versions, days):
    """Both bounds present and inside PRE-001's.

    A missing bound is not a bound: a policy keeping three versions for as long
    as they live, or seven days of however many versions there are, is unbounded
    in the direction it does not name.
    """
    return (isinstance(versions, int) and not isinstance(versions, bool)
            and isinstance(days, int) and not isinstance(days, bool)
            and versions <= MOST_VERSIONS and days <= MOST_DAYS)
