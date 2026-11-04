"""The schema family: what the schemas under a catalog are named for.

DEC-003's two states, measured against the layers the team recorded.
The product ships no medallion vocabulary of its own: a team using `raw`,
`clean` and `curated` would otherwise get a deviation on every schema they own,
which is the *rule fires on a legitimate configuration* failure, worse than no
rule at all.

**`holds_exactly` is shared with the axis family, and that is not an accident.**
DEC-002's `domain` state and DEC-003's `layer-per-schema` state make the same
claim about the same resources — every catalog holds one schema per recorded
name and no other — and differ only in which recorded list they read. Two target
states, two handles, one implementation: a handle names what is expected, and
nothing says two expectations cannot be measured the same way. A second copy
would be a second place for the absence case to drift.
"""

from wizard import outcomes
from wizard.evaluators.reading import stated
from wizard.naming import LAYERS, SEPARATOR, listed, recorded

CATALOG = "databricks_catalog"
SCHEMA = "databricks_schema"
TABLE = "databricks_sql_table"


def schema_layer_per_schema(rule, estate):
    """DEC-003's `layer-per-schema` state: the schemas are the layers.

    Every catalog holds one schema per recorded layer and no other. Offered only
    where the catalog axis leaves the schemas free — under DEC-002's `domain`
    state the schemas already carry the environment, and the corpus stops
    offering this state there rather than letting two rules contradict each
    other.
    """
    return holds_exactly(rule, estate, recorded(rule, LAYERS))


def holds_exactly(rule, estate, recorded_names):
    """Every catalog holds one schema per recorded name, and no other.

    Shared by DEC-002's `domain` state and DEC-003's `layer-per-schema` state.
    A schema outside the list is a deviation on the resource that declares it; a
    recorded name no schema carries is a deviation with no resource, placed in
    the root the catalog was declared in — no labelled
    root is needed, because the catalog it belongs to is right there.

    **A schema whose name or catalog is unknown at plan time may be the missing
    one.** It earns its own non-result, and so does every absence it could
    explain: the ones in its catalog, or in every catalog where which catalog it
    is in is itself unknown.
    """
    catalogs = estate.of_type(CATALOG)
    schemas = estate.of_type(SCHEMA)
    if not recorded_names or not catalogs or not schemas:
        return (disclosed(rule, estate, SCHEMA),)

    found = []
    unknown = [s for s in schemas
               if not stated(s.values.get("name")) or not stated(s.values.get("catalog_name"))]
    found.extend(unnamed(rule, s, "schema") for s in unknown)

    for catalog, held in _by_catalog(rule, catalogs, schemas, found):
        carried = set()
        for resource in held:
            name = resource.values.get("name")
            carried.add(name)
            address = f"{catalog.name}.{name}"
            if name in recorded_names:
                found.append(outcomes.passed(rule, resource, address))
            else:
                found.append(outcomes.failed(rule, resource, address,
                                             schema=name, catalog=catalog.name))
        absent = [f"{catalog.name}.{name}" for name in recorded_names if name not in carried]
        could_be = [s for s in unknown
                    if not stated(s.values.get("catalog_name"))
                    or s.values.get("catalog_name") == catalog.name]
        if absent and could_be:
            found.append(undecided(rule, estate, absent, could_be, "schema"))
            continue
        for address in absent:
            name = address[len(catalog.name) + 1:]
            found.append(outcomes.missing(
                rule, catalog.resource.root, address, schema=name, catalog=catalog.name))
    return tuple(found)


def schema_layer_in_table_name(rule, estate):
    """DEC-003's `layer-in-table-name` state: the layer is a table-name prefix.

    Two clauses, both read here: no schema is named for a recorded layer, and
    every table name declared in the configuration begins with one.

    **A table nobody declared is not a deviation.** Table names are generated in
    code for anything a pipeline writes, which is the normal case and what the
    rule discloses; this measures the ones the configuration does declare and is
    silent about the rest, rather than reporting an estate for being written the
    way most estates are.
    """
    recorded_layers = recorded(rule, LAYERS)
    schemas = estate.of_type(SCHEMA)
    if not recorded_layers or not schemas:
        return (disclosed(rule, estate, SCHEMA),)

    found = []
    for resource in schemas:
        name = resource.values.get("name")
        parent = resource.values.get("catalog_name")
        if not stated(name) or not stated(parent):
            found.append(unnamed(rule, resource, "schema"))
            continue

        address = f"{parent}.{name}"
        if name in recorded_layers:
            found.append(outcomes.failed(rule, resource, address,
                                         schema=name, catalog=parent))
        else:
            found.append(outcomes.passed(rule, resource, address))

    for resource in estate.of_type(TABLE):
        name = resource.values.get("name")
        schema = resource.values.get("schema_name")
        parent = resource.values.get("catalog_name")
        if not stated(name) or not stated(schema) or not stated(parent):
            found.append(unnamed(rule, resource, "table"))
            continue

        address = f"{parent}.{schema}.{name}"
        if _prefixed(name, recorded_layers):
            found.append(outcomes.passed(rule, resource, address))
        else:
            found.append(outcomes.failed(rule, resource, address,
                                         schema=schema, catalog=parent))
    return tuple(found)


def _prefixed(name, recorded_layers):
    """Whether a table name begins with a recorded layer and the separator.

    The separator is required: a table called `bronzed_orders` is not a bronze
    table, and a rule that read it as one would pass an estate that follows no
    convention at all.
    """
    return any(name.startswith(f"{layer}{SEPARATOR}") for layer in recorded_layers)


def disclosed(rule, estate, of_type):
    return outcomes.unevaluable_as_disclosed(
        rule, estate.root, otherwise=f"{estate.subject} declares no {of_type} resources")


def undecided(rule, estate, absent, unknown, kind):
    """The non-result for absences a resource of unknown name could explain.

    Shared by every family that finds a deviation by absence and reads names:
    an unnamed resource may be the missing one, so reporting the absence would
    be a deviation the applied plan could contradict.
    """
    return outcomes.unevaluable(
        rule, outcomes.ESTATE_SIDE,
        f"no {kind} is named {listed(absent)}, but "
        f"{listed([r.address for r in unknown])} has a name not known at plan time and "
        "may be it",
        root=estate.root)


def unnamed(rule, resource, kind):
    return outcomes.unevaluable_on(
        rule, resource,
        reason=f"the name of {resource.address} is not known at plan time, so the {kind} "
               "has no identity a deviation could be recorded against")


def _by_catalog(rule, catalogs, schemas, found):
    """Each readable catalog paired with the schemas declaring themselves in it."""
    held = []
    for resource in catalogs:
        name = resource.values.get("name")
        if not stated(name):
            found.append(unnamed(rule, resource, "catalog"))
            continue
        held.append((_Catalog(name, resource), tuple(
            schema for schema in schemas
            if schema.values.get("catalog_name") == name
            and stated(schema.values.get("name"))
        )))
    return held


class _Catalog:
    """A catalog's platform name and the resource that declared it."""

    def __init__(self, name, resource):
        self.name = name
        self.resource = resource
