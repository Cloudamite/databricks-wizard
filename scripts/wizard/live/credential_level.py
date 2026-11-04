"""DEC-009 in the account: which cloud identity reaches each catalog's storage.

The plan dialect's family (`wizard/evaluators/credential_level.py`) read against
the account's objects. A catalog's effective root is its own, else its
metastore's, as DEC-008 reads it in the account. Its identity is then:

- for a root of its own, the identity of the credential named by the external
  location whose `url` is the root's longest prefix on whole path segments;
- for an inherited root, the identity of the metastore's storage-root
  credential, which every inheriting catalog shares (`reach.Unread` where the
  snapshot does not hold it).

One outcome per catalog, filed where the catalog lives.
"""

from wizard import outcomes
from wizard.naming import environments_of, listed, split_name
from wizard.reach import FAIL, PASS, Unread, covering, judged


def catalog_identities_unshared(rule, estate):
    """DEC-009's `per-catalog`: no identity reaches two catalogs' storage."""
    def message(catalog, identity, forbidden, sharing):
        return {"resource": f"catalog {catalog.name}", "identity": str(identity),
                "catalogs": listed(f"catalog {other.name}" for other in forbidden)}

    return _per_catalog(rule, estate, lambda catalog, others: others, message)


def shared_identities_one_environment(rule, estate):
    """DEC-009's `by-environment`: an identity reaches catalogs of one
    environment, read from a `<domain>_<environment>` name."""
    recorded = environments_of(rule)

    def environment(catalog):
        _, named = split_name(catalog.name)
        return named if named in recorded else None

    def forbids(catalog, others):
        return [other for other in others if environment(other) != environment(catalog)]

    def message(catalog, identity, forbidden, sharing):
        return {"identity": str(identity), "catalogs": listed(c.name for c in sharing)}

    return _per_catalog(rule, estate, forbids, message,
                        unplaced=lambda catalog: environment(catalog) is None)


def _per_catalog(rule, estate, forbids, message, unplaced=lambda catalog: False):
    if not estate.catalogs:
        return (_disclosed(rule),)

    metastores = {m["name"]: m for m in estate.metastores}
    found, reaches = [], []
    for catalog in estate.catalogs:
        if unplaced(catalog):
            found.append(_disclosed_on(rule, catalog,
                                       f"{catalog.name} is named for no recorded environment"))
            continue
        metastore = metastores.get(catalog.metastore, {})
        identities = {c["name"]: c.get("identity")
                      for c in metastore.get("storage_credentials", ())}
        if catalog.storage_root:
            locations = [(l["url"], l["credential"])
                         for l in metastore.get("external_locations", ())]
            identity = identities.get(covering(catalog.storage_root, locations))
            missing = (f"the account returned no external location covering the storage root "
                       f"of catalog {catalog.name}, or no identity for its credential")
        elif metastore.get("storage_root"):
            identity = (identities.get(metastore.get("storage_root_credential"))
                        or Unread(catalog.metastore))
            missing = None
        else:
            found.append(outcomes.unevaluable_on(
                rule, catalog.place, estate_address=catalog.name,
                reason=f"the account returned no storage root for catalog {catalog.name}, nor "
                       f"for the metastore {catalog.metastore} it would inherit one from"))
            continue
        if identity is None:
            found.append(_disclosed_on(rule, catalog, missing))
            continue
        reaches.append((catalog, identity))

    for catalog, identity, verdict, forbidden, sharing in judged(reaches, forbids):
        if verdict == PASS:
            found.append(outcomes.passed(rule, catalog.place, catalog.name))
        elif verdict == FAIL:
            found.append(outcomes.failed(rule, catalog.place, catalog.name,
                                         **message(catalog, identity, forbidden, sharing)))
        else:
            found.append(_disclosed_on(
                rule, catalog, f"the identity reaching catalog {catalog.name} cannot be "
                               "compared with the metastore's, which the account did not name"))
    return tuple(found)


def _disclosed_on(rule, catalog, otherwise):
    return outcomes.unevaluable_as_disclosed(
        rule, catalog.place.root, resource=catalog.place, estate_address=catalog.name,
        otherwise=otherwise)


def _disclosed(rule):
    return outcomes.unevaluable_as_disclosed(
        rule, None, otherwise="the account returned no catalog the audit measures")
