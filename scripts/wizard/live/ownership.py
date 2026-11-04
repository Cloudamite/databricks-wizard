"""PRE-004 in the account: Unity Catalog is owned by a group the team names.

The plan dialect's family (`wizard/evaluators/ownership.py`) read against the
account's objects: the owner of each metastore, of each storage credential and
external location in it, and of each measured catalog and its schemas. The
account returns an owner for every object, so the snapshot always carries one.
Filed where each object lives: its metastore.
"""

from wizard import outcomes
from wizard.live.estate import Located, metastore_place
from wizard.naming import recorded

OWNER_GROUP = "owner_group"


def unity_catalog_owned_by_group(rule, estate):
    """Every Unity Catalog object of the estate is owned by a group the set records."""
    groups = recorded(rule, OWNER_GROUP)
    found = []

    def measure(place, what, owner):
        if owner in groups:
            found.append(outcomes.passed(rule, place, what))
        else:
            found.append(outcomes.failed(rule, place, what, resource=what))

    for metastore in estate.metastores:
        place = Located(metastore_place(metastore["name"]))
        measure(place, f"metastore {metastore['name']}", metastore.get("owner"))
        for credential in metastore.get("storage_credentials", ()):
            measure(place, f"storage credential {credential['name']}", credential.get("owner"))
        for location in metastore.get("external_locations", ()):
            measure(place, f"external location {location['name']}", location.get("owner"))
    for catalog in estate.catalogs:
        measure(catalog.place, f"catalog {catalog.name}", catalog.owner)
        for schema in catalog.schemas:
            measure(catalog.place, f"schema {catalog.name}.{schema.name}", schema.owner)
    if not found:
        found.append(outcomes.unevaluable_as_disclosed(
            rule, None, otherwise="the account holds no Unity Catalog object of the estate's"))
    return tuple(found)
