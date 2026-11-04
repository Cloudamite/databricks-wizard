#!/usr/bin/env python3
"""Read a Databricks account, and the storage behind it, into a snapshot.

    uv run --project <skill>/scripts --locked --group audit <skill>/scripts/snapshot.py \
        --declaration live.yaml --out snapshot.json --databricks-profile NAME \
        (--aws-profile NAME | --no-storage)

The one part of the product that reaches an account with credentials, and the
only file that imports the Databricks SDK or the AWS SDK. It issues no write,
and it names no account and holds no credential of its own: both come from the
profiles it is told to read as — the account from the host and account
id of the profile `--databricks-profile` names, its credential by any means the
SDK supports, and the AWS credential from the profile `--aws-profile` names.
Nothing in the environment chooses either: the variables that would are removed
before an SDK is imported.

It reads the workspaces the live estate declaration names, the
metastore each is assigned, and the catalogs visible to them, and writes what
it read to `--out`. Then it reads the S3 bucket behind each storage root the
audit measures — its versioning status and lifecycle rules — unless told
`--no-storage`. The audit (`audit.py`) reads that file and never the account.
The calls it makes are the read calls below, and nothing else.

**Every declared workspace is read, or nothing is written.** A declared
workspace the account does not list most often means the configuration reaches
another account; one it lists but cannot be read means the principal is not the
one the audit needs. Either way the remedy is the configuration, so the reader
attempts every declared workspace, names each it could not read, and writes
nothing. So is a catalog the audit measures with no isolation mode, or with a
binding with no binding type: the audit would have to guess what it means. And
so is every bucket: one left unread would be audited as one with nothing to
say. A team whose credential cannot reach the buckets says so with
`--no-storage`; a failed read never becomes that.

Exit codes:

    0  every declared workspace was read, and the snapshot was written
    2  could not run — bad usage, a profile not named, a defective declaration, a
       profile that names no account, an account that cannot be reached or refuses the
       principal, a declared workspace not read, a measured catalog or binding
       returned without the field the audit reads, a bucket not read, an output
       directory that does not exist, or a missing dependency

There is no exit `1`: a snapshot is the whole of the estate or it is not written.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

CANNOT_RUN = 2

try:
    import yaml  # noqa: F401
except ImportError:
    from wizard.environment import missing_yaml
    missing_yaml("read the live estate declaration", CANNOT_RUN)

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from databricks.sdk import AccountClient
    from databricks.sdk.core import Config
except ImportError:
    from wizard.environment import missing_sdk
    missing_sdk(CANNOT_RUN)

from wizard import live_declaration, profiles  # noqa: E402
from wizard.files import write  # noqa: E402
from wizard.live.estate import (  # noqa: E402
    ENABLED, MEASURED_TYPES, SNAPSHOT_VERSION, SUSPENDED, Estate,
)
from wizard.live.storage import s3_buckets  # noqa: E402
from wizard.validity import CannotRun, Refused  # noqa: E402

NOT_LISTED = "not listed by the account"

# The kinds of storage credential whose identity the audit reads, each with the
# attributes that name it, first returned first.
IDENTITIES = (
    ("aws_iam_role", ("role_arn",)),
    ("azure_managed_identity", ("managed_identity_id", "access_connector_id")),
    ("azure_service_principal", ("application_id",)),
    ("databricks_gcp_service_account", ("email",)),
)

# Where the account comes from, said whenever the SDK could not reach one.
ACCOUNT_FROM = "the account is named by the profile's host and account_id, in ~/.databrickscfg"

# Said whenever a bucket could not be read: reading without storage is the
# team's choice to make, never what a failed read turns into.
WITHOUT_STORAGE = "to read the account without its storage, run with --no-storage"

# S3's answer for a bucket with no lifecycle configuration: no rules, which is a
# reading rather than a failure.
NO_LIFECYCLE = "NoSuchLifecycleConfiguration"

# What the audit reads of a lifecycle rule; the rest of
# the rule is not kept.
RULE_KEYS = ("Filter", "NoncurrentVersionExpiration", "Prefix", "Status")

# Anything resembling a host, a key or a token, removed from an exception's
# message before it is printed: an AWS access key id, a dotted name, which every
# Databricks host is, a Databricks token, or a long opaque string.
_SCRUBBED = (
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "<key>"),
    (re.compile(r"\b[\w-]+(?:\.[\w-]+)+\b"), "<host>"),
    (re.compile(r"\bdapi[0-9a-f]+\b|\b[\w-]{24,}\b"), "<token>"),
)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="snapshot.py",
        description="Read the workspaces a live estate declaration names into a snapshot.",
    )
    parser.add_argument("--declaration", required=True, metavar="PATH",
                        help="the live estate declaration naming the estate's workspaces")
    parser.add_argument("--out", required=True, metavar="PATH",
                        help="where the snapshot is written")
    profiles.add_arguments(parser, ("databricks",))
    storage = parser.add_mutually_exclusive_group()
    storage.add_argument("--aws-profile", metavar="NAME",
                         help="the AWS configuration profile to read the buckets through; a "
                              "profile, never a credential")
    storage.add_argument("--no-storage", action="store_true",
                         help="read no bucket: PRE-001 is then reported unevaluated")
    args = parser.parse_args(argv)
    # Before an SDK is imported: both read `os.environ` in this process.
    profiles.act_as(os.environ, args.aws_profile, args.databricks_profile)
    try:
        profiles.require(os.environ, Path.home(),
                         ("databricks",) if args.no_storage else profiles.BOTH)
    except Refused as exc:
        print(f"cannot run: {exc}", file=sys.stderr)
        return CANNOT_RUN
    aws = None if args.no_storage else _aws_sdk()

    try:
        declaration = live_declaration.read(args.declaration)
        out = _out(args.out)
        snapshot = read(declaration, args.databricks_profile)
        if aws is not None:
            snapshot["buckets"] = read_buckets(aws, declaration, snapshot, args.aws_profile)
        write(out, json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    except CannotRun as exc:
        print(f"cannot run: {exc}", file=sys.stderr)
        return CANNOT_RUN
    print(f"snapshot of {declaration['name']} written to {out}")
    return 0


def _aws_sdk():
    """The AWS SDK, imported only when storage is read, so `--no-storage`
    needs none."""
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        from wizard.environment import missing_sdk
        missing_sdk(CANNOT_RUN, "The AWS SDK (boto3)", "read the storage behind the storage roots")
    return boto3, ClientError


def _out(path):
    """`--out`, checked before the account is read, so a run that could not
    write what it read makes no call at all."""
    out = Path(path)
    if not out.parent.is_dir():
        raise CannotRun(f"--out is in a directory that does not exist: {out.parent}")
    return out


def read(declaration, profile):
    """Read the account into the snapshot document, or `CannotRun`."""
    through = f"read through profile {profile!r}"
    account = account_client(profile, through)
    try:
        listed = {workspace.workspace_name: workspace for workspace in account.workspaces.list()}
    except Exception as exc:
        raise CannotRun(f"the account could not be read: {reason(exc)}; {through}") from None
    named = {workspace.workspace_id: name for name, workspace in listed.items()}

    declared = [workspace["name"] for workspace in declaration["workspaces"]]
    failures = {name: NOT_LISTED for name in declared if name not in listed}
    reading = _Reading(named)
    for name in declared:
        if name in listed:
            try:
                reading.workspace(name, account.get_workspace_client(listed[name]))
            except Exception as exc:
                failures[name] = reason(exc)

    if failures:
        lines = "\n".join(f"  {name}: {failures[name]}" for name in declared if name in failures)
        noun = "workspace was" if len(failures) == 1 else "workspaces were"
        raise CannotRun(
            f"{len(failures)} declared {noun} not read, so no snapshot was written; "
            f"{through}\n{lines}"
        )
    if reading.unread:
        noun = "object was" if len(reading.unread) == 1 else "objects were"
        raise CannotRun(
            f"{len(reading.unread)} measured {noun} returned without what the audit reads, so "
            f"no snapshot was written; {through}\n" + "\n".join(sorted(reading.unread))
        )
    return reading.document(declaration["name"], listed)


def account_client(profile, through):
    """The account client, or `CannotRun` saying where the account comes from.

    The configuration is resolved first, so one that names no account, or names a
    workspace's host rather than the account console's, is found before the
    account client is built. `live.py workspaces` builds its client here too."""
    try:
        config = Config(profile=profile)
    except Exception as exc:
        raise CannotRun(
            f"the SDK could not authenticate to an account: {reason(exc)}; {through}; "
            f"{ACCOUNT_FROM}"
        ) from None
    lacking = [key for key in ("host", "account_id") if not getattr(config, key, None)]
    if lacking:
        raise CannotRun(f"the profile {profile!r} names no account: it has no "
                        f"{' and no '.join(lacking)}; {ACCOUNT_FROM}")
    if profiles.reach(config.host) != "account console":
        raise CannotRun(f"the profile {profile!r} reaches a workspace, {config.host}, not the "
                        f"account console; {ACCOUNT_FROM}")
    return AccountClient(config=config)


def read_buckets(aws, declaration, document, profile):
    """Each bucket behind an `s3://` storage root the audit measures, read once,
    or `CannotRun` naming every bucket not read."""
    boto3, client_error = aws
    through = f"read through AWS profile {profile!r}"
    names = s3_buckets(Estate(declaration, document))
    if not names:
        return []
    try:
        s3 = boto3.Session(profile_name=profile).client("s3")
    except Exception as exc:
        raise CannotRun(f"the AWS SDK could not be configured: {reason(exc)}; {through}; "
                        f"{WITHOUT_STORAGE}") from None

    readings, failures = [], {}
    for name in names:
        try:
            readings.append(_bucket(s3, client_error, name))
        except Exception as exc:
            failures[name] = reason(exc)
    if failures:
        noun = "bucket was" if len(failures) == 1 else "buckets were"
        lines = "\n".join(f"  {name}: {failures[name]}" for name in names if name in failures)
        raise CannotRun(
            f"{len(failures)} {noun} not read behind the storage roots, so no snapshot was "
            f"written; {through}; {WITHOUT_STORAGE}\n{lines}")
    return readings


class _UnknownStatus(Exception):
    """A versioning status S3 does not document, which no verdict rests on."""


def _bucket(s3, client_error, name):
    """One bucket's reading: its versioning status, absent where versioning was
    never enabled, and the parts of its lifecycle rules the audit reads."""
    status = s3.get_bucket_versioning(Bucket=name).get("Status")
    if status not in (None, ENABLED, SUSPENDED):
        raise _UnknownStatus(f"versioning status {status!r}, not {ENABLED} or {SUSPENDED}")
    try:
        rules = s3.get_bucket_lifecycle_configuration(Bucket=name).get("Rules", [])
    except client_error as exc:
        if exc.response.get("Error", {}).get("Code") != NO_LIFECYCLE:
            raise
        rules = []
    kept = sorted(({key: rule[key] for key in RULE_KEYS if key in rule} for rule in rules),
                  key=lambda rule: json.dumps(rule, sort_keys=True))
    return {"name": name, **_present(versioning=status), "lifecycle_rules": kept}


class _Reading:
    """What the declared workspaces showed, gathered as they are read.

    A metastore's catalogs are listed through every declared workspace assigned
    to it, since the API lists through a workspace only the catalogs bound to it
    or OPEN; each catalog is read once, through the first declared workspace
    that listed it.

    A measured catalog returned with no isolation mode, or with a binding with
    no binding type, is collected in `unread`, as is an
    external location with no URL or credential name and a storage credential
    of a kind the audit reads with no identity. A storage root is not: a
    catalog or schema with no managed storage of its own has none, and is
    written without the key.
    """

    def __init__(self, named):
        self.named = named
        self.principal = None
        self.metastores = {}
        self.assigned = {}
        self.unread = []

    def workspace(self, name, client):
        if self.principal is None:
            self.principal = client.current_user.me().user_name
        summary = client.metastores.summary()
        metastore = self.metastores.setdefault(
            summary.name,
            {"name": summary.name,
             **_present(cloud=_value(summary.cloud), storage_root=summary.storage_root,
                        storage_root_credential=summary.storage_root_credential_name,
                        owner=self._owner(summary, f"metastore {summary.name}")),
             "catalogs": {}, "external_locations": {}, "storage_credentials": {}},
        )
        self.assigned[name] = summary.name
        for catalog in client.catalogs.list():
            if catalog.name not in metastore["catalogs"]:
                metastore["catalogs"][catalog.name] = self._catalog(client, catalog)
        # Bound to other workspaces, either is hidden from a plain list.
        for location in client.external_locations.list(include_unbound=True):
            if location.name not in metastore["external_locations"]:
                metastore["external_locations"][location.name] = self._location(location)
        for credential in client.storage_credentials.list(include_unbound=True):
            if credential.name not in metastore["storage_credentials"]:
                metastore["storage_credentials"][credential.name] = self._credential(credential)

    def _location(self, location):
        if not location.url:
            self.unread.append(f"  {location.name}: an external location returned with no URL")
        if not location.credential_name:
            self.unread.append(f"  {location.name}: an external location returned with no "
                               "credential name")
        return {"name": location.name,
                **_present(url=location.url or None,
                           credential=location.credential_name or None,
                           owner=self._owner(location, f"external location {location.name}"))}

    def _credential(self, credential):
        """Its name, and the kind and identity of a kind the audit reads; a
        credential of any other kind is written with its name alone."""
        for kind, attributes in IDENTITIES:
            block = getattr(credential, kind, None)
            if block is None:
                continue
            identity = next((getattr(block, attribute, None) for attribute in attributes
                             if getattr(block, attribute, None)), None)
            if identity is None:
                self.unread.append(f"  {credential.name}: a storage credential returned with "
                                   "no identity")
            return {"name": credential.name, "kind": kind,
                    **_present(identity=identity, owner=self._owner(
                        credential, f"storage credential {credential.name}"))}
        return {"name": credential.name,
                **_present(owner=self._owner(credential, f"storage credential {credential.name}"))}

    def _catalog(self, client, catalog):
        kind, mode = _value(catalog.catalog_type), _value(catalog.isolation_mode)
        bindings = [self._binding(binding)
                    for binding in client.workspace_bindings.get_bindings("catalog", catalog.name)]
        if kind in MEASURED_TYPES:
            if mode is None:
                self.unread.append(f"  {catalog.name}: returned with no isolation mode")
            self.unread += [
                f"  {catalog.name}: its binding to {_bound(binding)} returned with no "
                "binding type"
                for binding in bindings if "binding_type" not in binding]
        schemas = [
            {"name": schema.name,
             **_present(storage_root=schema.storage_root,
                        owner=self._owner(schema, f"schema {catalog.name}.{schema.name}")),
             "tables": sorted(table.name for table in client.tables.list(
                 catalog_name=catalog.name, schema_name=schema.name,
                 omit_columns=True, omit_properties=True))}
            for schema in client.schemas.list(catalog_name=catalog.name)
        ]
        return {
            "name": catalog.name,
            **_present(type=kind, isolation_mode=mode, storage_root=catalog.storage_root,
                       owner=self._owner(catalog, f"catalog {catalog.name}")),
            "bindings": sorted(bindings, key=_binding_order),
            "schemas": sorted(schemas, key=lambda s: s["name"]),
        }

    def _owner(self, found, what):
        """The object's owner, which the account returns for every Unity Catalog object;
        one returned without it is named, and no snapshot is written."""
        owner = getattr(found, "owner", None) or None
        if owner is None:
            self.unread.append(f"  {what}: returned with no owner")
        return owner

    def _binding(self, binding):
        # By the name the account lists; a workspace it does not list keeps its
        # id, since there is no name to give it.
        workspace = self.named.get(binding.workspace_id)
        where = {"workspace": workspace} if workspace is not None else {
            "workspace_id": binding.workspace_id}
        return {**where, **_present(binding_type=_value(binding.binding_type))}

    def document(self, estate, listed):
        workspaces = []
        for name in sorted(listed):
            if name in self.assigned:
                workspaces.append({"name": name, "declared": True,
                                   "metastore": self.assigned[name]})
            else:
                workspaces.append({"name": name, "declared": False})
        metastores = [{**metastore,
                       **{part: sorted(metastore[part].values(), key=lambda o: o["name"])
                          for part in ("catalogs", "external_locations",
                                       "storage_credentials")}}
                      for _, metastore in sorted(self.metastores.items())]
        return {"schema_version": SNAPSHOT_VERSION, "estate": estate,
                **_present(principal=self.principal),
                "workspaces": workspaces, "metastores": metastores}


def _binding_order(binding):
    """By workspace name; a binding known only by id after every named one."""
    if "workspace" in binding:
        return (0, binding["workspace"], 0)
    return (1, "", binding["workspace_id"])


def _bound(binding):
    """The workspace a binding binds: by name, or by id where it has no name."""
    return binding.get("workspace", binding.get("workspace_id"))


def _value(field):
    """An API value verbatim: an enum's value, or the value itself."""
    return getattr(field, "value", field)


def _present(**fields):
    """The fields the API returned. Absent, not null, so a reader can tell *not
    returned* from a value."""
    return {key: value for key, value in fields.items() if value is not None}


def reason(exc):
    """An exception's class and message, with anything resembling a host or a
    token removed."""
    message = str(exc)
    for pattern, replacement in _SCRUBBED:
        message = pattern.sub(replacement, message)
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


if __name__ == "__main__":
    raise SystemExit(main())
