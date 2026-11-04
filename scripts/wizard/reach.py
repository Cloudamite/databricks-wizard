"""Which cloud identity reaches which catalog's storage: what both dialects decide alike.

DEC-009. The Terraform evaluators (`wizard/evaluators/credential_level.py`) and
the audit's (`wizard/live/credential_level.py`) read a catalog's identity from
different objects, and share nothing else. What they
share is here: which external location covers a root, and how a verdict follows
from identities some of which are not known.

**An identity the estate does not name can still be shared.** Every catalog
inheriting one metastore's root reaches it through the metastore's own
credential, so any two of them share an identity whatever it is. `Unread`
stands for it. Comparing it with an identity that is known says nothing either
way, and that, not the unread identity itself, is what leaves a verdict open.
"""

from dataclasses import dataclass

PASS, FAIL, UNDECIDED = "pass", "fail", "undecided"


@dataclass(frozen=True)
class Unread:
    """The identity every catalog inheriting `metastore`'s root shares, where
    the estate does not say which it is."""

    metastore: str

    def __str__(self):
        return f"the storage-root credential of metastore {self.metastore}"


def covers(prefix, url):
    """Whether a location on `prefix` covers `url`, on whole path segments:
    `s3://acme-pro` does not cover `s3://acme-prod/x`."""
    prefix = prefix.rstrip("/")
    return url == prefix or url.startswith(prefix + "/")


def covering(url, locations):
    """Of `(prefix, item)` pairs, the item whose prefix is the longest to cover
    `url`, or `None` where none does."""
    found = [(len(prefix.rstrip("/")), item) for prefix, item in locations
             if covers(prefix, url)]
    return max(found, key=lambda pair: pair[0])[1] if found else None


def judged(reaches, forbids):
    """`(catalog, identity, verdict, forbidden, sharing)` for each `(catalog, identity)`.

    `forbids(catalog, others)` is the catalogs among `others` this rule forbids
    `catalog` to share an identity with. Those that certainly share it decide a
    FAIL; where none does, those that might share it leave the verdict
    UNDECIDED; otherwise it is a PASS. `sharing` is every catalog certainly
    sharing the identity, `catalog` among them.
    """
    found = []
    for catalog, identity in reaches:
        others = [(other, theirs) for other, theirs in reaches if other is not catalog]
        certain = [other for other, theirs in others if theirs == identity]
        possible = [other for other, theirs in others
                    if theirs != identity and _unread(identity, theirs)]
        sharing = [catalog] + certain
        forbidden = forbids(catalog, certain)
        if forbidden:
            found.append((catalog, identity, FAIL, forbidden, sharing))
        elif forbids(catalog, possible):
            found.append((catalog, identity, UNDECIDED, (), sharing))
        else:
            found.append((catalog, identity, PASS, (), sharing))
    return found


def _unread(mine, theirs):
    return isinstance(mine, Unread) or isinstance(theirs, Unread)
