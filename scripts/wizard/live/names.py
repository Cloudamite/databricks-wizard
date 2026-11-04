"""DEC-002 and DEC-003 in the account: what the catalogs, schemas and tables are
named for.

Measured against the environments and layers the team recorded, on
the estate's catalogs and every schema in them but `information_schema`.
A catalog, schema or table is filed under its metastore.

**A missing catalog is placed by its environment.** It belongs in the metastore
of the workspaces the declaration labels with that environment. Where no
workspace is labelled with it, or the ones that are sit on more than one
metastore, the deviation cannot be placed, and the rule says so instead of
filing it where it did not earn it.

Under DEC-003's `layer-in-table-name` state every table the account holds is
measured, where the Terraform dialect measures only those a configuration
declares: the audit measures what exists.
"""

from wizard import outcomes
from wizard.naming import LAYERS, SEPARATOR, environments_of, listed, recorded, split_name


def catalog_axis_environment(rule, estate):
    """The catalogs are the environments."""
    names = environments_of(rule)
    if not estate.catalogs:
        return (_disclosed(rule),)
    found = [outcomes.passed(rule, c.place, c.name) if c.name in names
             else outcomes.failed(rule, c.place, c.name, catalog=c.name)
             for c in estate.catalogs]
    present = {c.name for c in estate.catalogs}
    return tuple(found + _absent(rule, estate, [(n, n) for n in names if n not in present]))


def catalog_axis_both(rule, estate):
    """Every catalog is `domain_environment`, and every domain has one in every
    recorded environment."""
    names = environments_of(rule)
    if not estate.catalogs:
        return (_disclosed(rule),)
    found, domains = [], {}
    for catalog in estate.catalogs:
        domain, environment = split_name(catalog.name)
        if domain and environment in names:
            domains.setdefault(domain, set()).add(environment)
            found.append(outcomes.passed(rule, catalog.place, catalog.name))
        else:
            found.append(outcomes.failed(rule, catalog.place, catalog.name, catalog=catalog.name))
    absent = [(f"{domain}{SEPARATOR}{environment}", environment)
              for domain in sorted(domains) for environment in names
              if environment not in domains[domain]]
    return tuple(found + _absent(rule, estate, absent))


def catalog_axis_domain(rule, estate):
    """A catalog per domain, the environments as its schemas."""
    return holds_exactly(rule, estate, environments_of(rule))


def schema_layer_per_schema(rule, estate):
    """The schemas are the layers."""
    return holds_exactly(rule, estate, recorded(rule, LAYERS))


def holds_exactly(rule, estate, names):
    """Every catalog holds one schema per recorded name, and no other."""
    if not estate.catalogs:
        return (_disclosed(rule),)
    found = []
    for catalog in estate.catalogs:
        held = {schema.name for schema in catalog.schemas}
        for schema in catalog.schemas:
            address = f"{catalog.name}.{schema.name}"
            if schema.name in names:
                found.append(outcomes.passed(rule, catalog.place, address))
            else:
                found.append(outcomes.failed(rule, catalog.place, address,
                                             schema=schema.name, catalog=catalog.name))
        found += [outcomes.missing(rule, catalog.place.root, f"{catalog.name}.{name}",
                                   schema=name, catalog=catalog.name)
                  for name in names if name not in held]
    return tuple(found)


def schema_layer_in_table_name(rule, estate):
    """No schema is named for a layer, and every table name begins with one."""
    layers = recorded(rule, LAYERS)
    if not estate.catalogs:
        return (_disclosed(rule),)
    found = []
    for catalog in estate.catalogs:
        for schema in catalog.schemas:
            address = f"{catalog.name}.{schema.name}"
            if schema.name in layers:
                found.append(outcomes.failed(rule, catalog.place, address,
                                             schema=schema.name, catalog=catalog.name))
            else:
                found.append(outcomes.passed(rule, catalog.place, address))
            for table in schema.tables:
                where = f"{address}.{table}"
                if any(table.startswith(f"{layer}{SEPARATOR}") for layer in layers):
                    found.append(outcomes.passed(rule, catalog.place, where))
                else:
                    found.append(outcomes.failed(rule, catalog.place, where,
                                                 schema=schema.name, catalog=catalog.name))
    return tuple(found)


def _absent(rule, estate, expected):
    """A deviation per missing catalog, in the metastore of the workspaces
    labelled with its environment, or one non-result for those it cannot place."""
    found, unplaced = [], []
    for address, environment in expected:
        place = estate.placed(environment)
        if place is None:
            unplaced.append(address)
        else:
            found.append(outcomes.missing(rule, place.root, address, catalog=address))
    if unplaced:
        found.append(outcomes.unevaluable(
            rule, outcomes.ESTATE_SIDE,
            f"the estate holds no catalog named {listed(unplaced)}, and the declaration "
            "labels no one metastore's workspaces with the environment each belongs to, so "
            "the deviation cannot be placed; labelling the workspaces is what resolves it"))
    return found


def _disclosed(rule):
    return outcomes.unevaluable_as_disclosed(rule, None,
                                             otherwise="the estate holds no catalogs")
