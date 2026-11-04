"""A snapshot read against its declaration: the estate the audit measures.

`read_snapshot` refuses a snapshot it cannot trust, or one holding what the
reader never writes, and
`mismatches` one that does not describe the declaration.
`Estate` is what the live evaluators are handed: the declared workspaces with
their environments, and the catalogs that are the estate's, each knowing the
place its outcomes are filed in.

The snapshot's values are the API's, verbatim; this
is where they are interpreted, once, so that no evaluator interprets them again.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from wizard.validity import CLOUDS, CannotRun

# Version 2 added the catalogs' and schemas' storage roots, and version 3 the
# external locations, storage credentials and the metastore's storage-root
# credential, version 4 the bucket readings, and version 5 every Unity Catalog
# object's owner. An older snapshot
# carries none of them, and read as one would say that the account has none,
# or that storage was not read, so it is refused.
# `snapshot.py` writes this version.
SNAPSHOT_VERSION = 5
SNAPSHOT_KEYS = ("schema_version", "estate", "workspaces", "metastores")

ACCOUNT = "account"

# The catalogs a platform team creates. `catalogs.list()` returns others —
# `system`, internal, Delta Sharing and foreign catalogs — which are counted
# rather than measured.
MEASURED_TYPES = ("MANAGED_CATALOG", "MANAGED_ONLINE_CATALOG")

OPEN, ISOLATED = "OPEN", "ISOLATED"
READ_ONLY, READ_WRITE = "BINDING_TYPE_READ_ONLY", "BINDING_TYPE_READ_WRITE"

# The kinds of storage credential whose identity the reader reads. A credential of one of them carries its identity; one of any
# other kind is written with its name alone.
IDENTITY_KINDS = ("aws_iam_role", "azure_managed_identity", "azure_service_principal",
                  "databricks_gcp_service_account")

# S3's versioning statuses. A bucket whose versioning was never enabled has
# none, which the snapshot writes as an absent key.
ENABLED, SUSPENDED = "Enabled", "Suspended"

# Created by Databricks in every catalog, and cannot be dropped, so no rule
# measures it; `default` can be, and is measured.
INFORMATION_SCHEMA = "information_schema"


def workspace_place(name):
    return f"workspace:{name}"


def metastore_place(name):
    return f"metastore:{name}"


def read_snapshot(path):
    """The snapshot at `path`, or `CannotRun` naming it."""
    name = Path(path).name
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise CannotRun(f"the snapshot {name} could not be read: {exc.strerror}") from None
    except ValueError as exc:
        raise CannotRun(f"the snapshot {name} is not readable JSON: {exc}") from None
    if not isinstance(document, dict) or any(key not in document for key in SNAPSHOT_KEYS):
        raise CannotRun(f"{name} is not a snapshot: a snapshot carries "
                        f"{', '.join(SNAPSHOT_KEYS)}")
    version = document["schema_version"]
    if version != SNAPSHOT_VERSION or isinstance(version, bool):
        raise CannotRun(f"the snapshot {name} has schema_version {version!r}; this build "
                        f"reads snapshot version {SNAPSHOT_VERSION} only. Read the account "
                        "again.")
    found = unread(document)
    if found:
        raise CannotRun(f"the snapshot {name} holds what the reader never writes, so no rule "
                        "can read it; read the account again:\n" + "\n".join(found))
    return document


def unread(document):
    """Each measured catalog whose isolation mode, or whose binding's type, is
    not one the reader writes, each external location or storage credential
    without what the reader always writes, and each
    bucket whose versioning status is not. Only a
    hand-edited snapshot holds one, and no evaluator guesses what it means."""
    found = []
    for what, owned in _owned(document):
        if not owned.get("owner"):
            found.append(f"  {what}: no owner")
    for bucket in document.get("buckets", ()):
        status = bucket.get("versioning")
        if status not in (None, ENABLED, SUSPENDED):
            found.append(f"  {bucket.get('name')}: versioning status {status!r}, not "
                         f"{ENABLED} or {SUSPENDED}")
    for metastore in document["metastores"]:
        for location in metastore.get("external_locations", ()):
            for key, what in (("url", "URL"), ("credential", "credential name")):
                if not location.get(key):
                    found.append(f"  {location.get('name')}: an external location with no "
                                 f"{what}")
        for credential in metastore.get("storage_credentials", ()):
            if credential.get("kind") in IDENTITY_KINDS and not credential.get("identity"):
                found.append(f"  {credential.get('name')}: a storage credential of kind "
                             f"{credential['kind']} with no identity")
        for catalog in metastore.get("catalogs", ()):
            if catalog.get("type") not in MEASURED_TYPES:
                continue
            mode = catalog.get("isolation_mode")
            if mode not in (OPEN, ISOLATED):
                found.append(f"  {catalog.get('name')}: isolation mode {_given(mode)}, not "
                             f"{ISOLATED} or {OPEN}")
            for binding in catalog.get("bindings", ()):
                kind = binding.get("binding_type")
                if kind not in (READ_ONLY, READ_WRITE):
                    bound = binding.get("workspace", binding.get("workspace_id"))
                    found.append(f"  {catalog.get('name')}: its binding to {bound} has binding "
                                 f"type {_given(kind)}, not {READ_ONLY} or {READ_WRITE}")
    return found


def _owned(document):
    """`(what, object)` for every Unity Catalog object the reader writes an owner for."""
    for metastore in document["metastores"]:
        yield f"metastore {metastore.get('name')}", metastore
        for location in metastore.get("external_locations", ()):
            yield f"external location {location.get('name')}", location
        for credential in metastore.get("storage_credentials", ()):
            yield f"storage credential {credential.get('name')}", credential
        for catalog in metastore.get("catalogs", ()):
            yield f"catalog {catalog.get('name')}", catalog
            for schema in catalog.get("schemas", ()):
                yield f"schema {catalog.get('name')}.{schema.get('name')}", schema


def _given(value):
    return "missing" if value is None else repr(value)


def mismatches(document, declaration):
    """Every way the snapshot does not describe the declaration."""
    found = []
    if document["estate"] != declaration["name"]:
        found.append(f"the snapshot is of the estate {document['estate']!r}, and the "
                     f"declaration declares {declaration['name']!r}")
    in_snapshot = {w["name"] for w in document["workspaces"] if w.get("declared")}
    in_declaration = {w["name"] for w in declaration["workspaces"]}
    if in_declaration - in_snapshot:
        found.append("declared, and not in the snapshot: "
                     + ", ".join(sorted(in_declaration - in_snapshot)))
    if in_snapshot - in_declaration:
        found.append("in the snapshot, and not declared: "
                     + ", ".join(sorted(in_snapshot - in_declaration)))
    return found


@dataclass(frozen=True)
class Located:
    """Where an outcome is filed. The shape `outcomes.passed` and its siblings
    read off a resource: a place, and no Terraform address."""

    root: str
    address: Optional[str] = None


@dataclass(frozen=True)
class Binding:
    """A catalog's binding: the workspace by name where the account listed it,
    by id where it did not, and its environment where the declaration labels
    the workspace."""

    workspace: Optional[str]
    workspace_id: Optional[int]
    binding_type: str
    environment: Optional[str]

    @property
    def named(self):
        return self.workspace if self.workspace is not None else str(self.workspace_id)

    @property
    def writes(self):
        return self.binding_type == READ_WRITE


@dataclass(frozen=True)
class Schema:
    """`storage_root` is `None` where the schema has no managed storage of its
    own, which the snapshot writes as an absent key."""

    name: str
    tables: Tuple[str, ...]
    storage_root: Optional[str] = None
    owner: Optional[str] = None


@dataclass(frozen=True)
class Catalog:
    """One of the estate's catalogs, and the metastore it lives in."""

    name: str
    metastore: str
    isolation_mode: str
    bindings: Tuple[Binding, ...]
    schemas: Tuple[Schema, ...]
    storage_root: Optional[str] = None
    owner: Optional[str] = None

    @property
    def place(self):
        return Located(metastore_place(self.metastore))


class Estate:
    """The declaration and the snapshot, read together."""

    def __init__(self, declaration, document):
        self.name = declaration["name"]
        self.workspaces = tuple(w["name"] for w in declaration["workspaces"])
        self.environments = {w["name"]: w["environment"]
                             for w in declaration["workspaces"] if w.get("environment")}
        listed = document["workspaces"]
        self.undeclared = tuple(sorted(w["name"] for w in listed if not w.get("declared")))
        self.metastore_of = {w["name"]: w.get("metastore") for w in listed if w.get("declared")}
        self.principal = document.get("principal")
        self.metastores = tuple(document["metastores"])
        self.catalogs, self.not_measured = self._catalogs()
        # Each bucket's reading by name; `None` where the snapshot was read with
        # `--no-storage` and records no reading at all.
        self.buckets = (None if "buckets" not in document
                        else {b["name"]: b for b in document["buckets"]})

    @property
    def account(self):
        return Located(ACCOUNT)

    def clouds(self):
        """The clouds the metastores run on, in the cloud table's order."""
        found = {m.get("cloud") for m in self.metastores}
        return tuple(cloud for cloud in CLOUDS if cloud in found)

    def placed(self, environment):
        """The place of the metastore the workspaces labelled `environment`
        are on, or `None` where no one metastore is."""
        found = {self.metastore_of.get(name)
                 for name, labelled in self.environments.items() if labelled == environment}
        return Located(metastore_place(found.pop())) if len(found) == 1 else None

    def _visible(self, catalog):
        return catalog.get("isolation_mode") == OPEN or any(
            b.get("workspace") in self.workspaces for b in catalog.get("bindings", ()))

    def _catalogs(self):
        measured, not_measured = [], {}
        for metastore in self.metastores:
            for catalog in metastore.get("catalogs", ()):
                if not self._visible(catalog):
                    continue
                kind = catalog.get("type")
                if kind in MEASURED_TYPES:
                    measured.append(self._catalog(metastore["name"], catalog))
                else:
                    not_measured[kind] = not_measured.get(kind, 0) + 1
        return tuple(measured), dict(sorted(not_measured.items(), key=lambda i: str(i[0])))

    def _catalog(self, metastore, catalog):
        bindings = tuple(
            Binding(workspace=b.get("workspace"), workspace_id=b.get("workspace_id"),
                    binding_type=b["binding_type"],
                    environment=self.environments.get(b.get("workspace")))
            for b in catalog.get("bindings", ()))
        schemas = tuple(Schema(s["name"], tuple(s.get("tables", ())), s.get("storage_root"),
                               s.get("owner"))
                        for s in catalog.get("schemas", ()) if s["name"] != INFORMATION_SCHEMA)
        return Catalog(catalog["name"], metastore, catalog["isolation_mode"],
                       bindings, schemas, catalog.get("storage_root"), catalog.get("owner"))
