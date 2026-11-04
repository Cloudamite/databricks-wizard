"""The identity-level family: which cloud identity reaches each catalog's storage.

DEC-009. A catalog's effective root is read as the storage-level family reads
it, its own else the metastore's, and then the identity that reaches it:

- **A root of its own** through the `databricks_external_location` whose `url`
  is its longest prefix on whole path segments, that location's
  `credential_name`, and the `databricks_storage_credential` of that name.
- **An inherited root** through the metastore's own credential, the
  `databricks_metastore_data_access` the estate declares. Where it declares
  none, every inheriting catalog still shares it (`reach.Unread`).

The identity is the credential's `aws_iam_role[0].role_arn`; an Azure managed
identity's `managed_identity_id`, else its `access_connector_id`; an Azure
service principal's `application_id`; or a GCP service account's `email`
(`databricks/databricks` 1.133.0, `terraform providers schema -json`). Two
credentials over one identity reach exactly what one would, so identities are
compared, never credentials.

**One outcome per catalog**, filed by its name, as DEC-008's are.
"""

from wizard import outcomes
from wizard.evaluators.reading import declared, metastore_root, stated
from wizard.naming import environments_of, listed, split_name
from wizard.reach import FAIL, PASS, Unread, covering, judged

CATALOG = "databricks_catalog"
METASTORE = "databricks_metastore"
LOCATION = "databricks_external_location"
CREDENTIAL = "databricks_storage_credential"
DATA_ACCESS = "databricks_metastore_data_access"

# Each kind of identity block, and the attributes that name the identity in it,
# first stated first.
IDENTITY = (
    ("aws_iam_role", ("role_arn",)),
    ("azure_managed_identity", ("managed_identity_id", "access_connector_id")),
    ("azure_service_principal", ("application_id",)),
    ("databricks_gcp_service_account", ("email",)),
)


def catalog_identities_unshared(rule, estate):
    """DEC-009's `per-catalog`: no identity reaches two catalogs' storage."""
    def message(catalog, identity, forbidden, sharing):
        return {"resource": f"catalog {catalog.values['name']}", "identity": str(identity),
                "catalogs": listed(f"catalog {other.values['name']}" for other in forbidden)}

    return _per_catalog(rule, estate, lambda catalog, others: others, message)


def shared_identities_one_environment(rule, estate):
    """DEC-009's `by-environment`: an identity reaches catalogs of one environment.

    The environment is read from the catalog's name as DEC-008's
    `by-environment` reads it.
    """
    recorded = environments_of(rule)

    def forbids(catalog, others):
        mine = _environment(catalog, recorded)
        return [other for other in others if _environment(other, recorded) != mine]

    def message(catalog, identity, forbidden, sharing):
        return {"identity": str(identity),
                "catalogs": listed(other.values["name"] for other in sharing)}

    return _per_catalog(rule, estate, forbids, message,
                        unplaced=lambda catalog: _environment(catalog, recorded) is None)


def _per_catalog(rule, estate, forbids, message, unplaced=lambda catalog: False):
    """One outcome per catalog, from the identity that reaches its effective root."""
    catalogs = declared(estate, CATALOG)
    if not catalogs:
        return (_disclosed(rule, estate),)

    inherited, inheritable = metastore_root(estate)
    locations = [(location.values["url"], location.values.get("credential_name"))
                 for location in declared(estate, LOCATION)
                 if stated(location.values.get("url"))]
    credentials = {credential.values["name"]: _identity(credential.values)
                   for credential in declared(estate, CREDENTIAL)
                   if stated(credential.values.get("name"))}
    found, reaches = [], []
    for catalog in catalogs:
        name = catalog.values.get("name")
        if not stated(name):
            found.append(outcomes.unevaluable_on(
                rule, catalog,
                reason=f"{catalog.address} has no name known at plan time, so whether it "
                       "shares an identity cannot be said of any catalog"))
            continue
        if unplaced(catalog) or "storage_root" not in catalog.values:
            found.append(_disclosed(rule, estate, catalog, name))
            continue
        root = catalog.values["storage_root"]
        if root is None:
            if not inheritable:
                found.append(_disclosed(rule, estate, catalog, name))
                continue
            if inherited is None:
                found.append(outcomes.unevaluable_on(
                    rule, catalog, estate_address=name,
                    reason=f"catalog {name} declares no storage root and neither does the "
                           "metastore, so this estate does not say where its storage is"))
                continue
            identity = _metastore_identity(estate)
        else:
            identity = credentials.get(covering(root, locations))
        if identity is None:
            found.append(_disclosed(rule, estate, catalog, name))
            continue
        reaches.append((catalog, identity))

    for catalog, identity, verdict, forbidden, sharing in judged(reaches, forbids):
        name = catalog.values["name"]
        if verdict == PASS:
            found.append(outcomes.passed(rule, catalog, name))
        elif verdict == FAIL:
            found.append(outcomes.failed(rule, catalog, name,
                                         **message(catalog, identity, forbidden, sharing)))
        else:
            found.append(_disclosed(rule, estate, catalog, name))
    return tuple(found)


def _metastore_identity(estate):
    """The identity behind the metastore's root: its data access's where the
    estate declares exactly one, and otherwise the one every inheriting catalog
    shares without the estate saying which."""
    accesses = declared(estate, DATA_ACCESS)
    if len(accesses) == 1:
        identity = _identity(accesses[0].values)
        if identity is not None:
            return identity
    metastore = declared(estate, METASTORE)[0].values.get("name")
    return Unread(metastore if stated(metastore) else "of this estate")


def _identity(values):
    """The identity a credential's block names, or `None` where it names none
    known at plan time."""
    for kind, attributes in IDENTITY:
        blocks = values.get(kind)
        if not blocks:
            continue
        block = blocks[0] if isinstance(blocks, list) and isinstance(blocks[0], dict) else {}
        return next((block[attribute] for attribute in attributes
                     if stated(block.get(attribute))), None)
    return None


def _environment(catalog, recorded):
    """The recorded environment a `<domain>_<environment>` name ends in, or `None`."""
    _, environment = split_name(catalog.values["name"])
    return environment if environment in recorded else None


def _disclosed(rule, estate, resource=None, estate_address=None):
    return outcomes.unevaluable_as_disclosed(
        rule, estate.root,
        otherwise=f"{estate.subject} does not say which identity reaches this storage",
        resource=resource, estate_address=estate_address)
