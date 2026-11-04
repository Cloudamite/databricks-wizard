"""What every evaluator needs to read a plan, and nothing about any one rule.

This module exists so that the family modules and the registry can share code
without importing each other: the registry imports every family, so a family
importing the registry would close a cycle. What lives here is the reading of a
plan's values, which is the one thing every family does the same way.
"""


def stated(value):
    """Whether the plan expresses this attribute as a usable string.

    Absent and `null` are one case here: an attribute unknown until apply is
    missing from `values`, one the block does not set is present and `None`, and
    neither can be read now. Choosing *which* attribute a resource names is where
    they differ. The empty string is a third
    spelling of it, and a value of the wrong type is a fourth — neither is a
    fact a verdict can rest on.
    """
    return isinstance(value, str) and value != ""


MANAGED = "managed"


def declared(estate, kind):
    """The resources of `kind` the estate declares: a data source is read
    elsewhere, and what it reads is not this estate's."""
    return [resource for resource in estate.of_type(kind) if resource.mode == MANAGED]


def metastore_root(estate):
    """`(the metastore's root, whether a catalog can be said to inherit it)`.

    Inheritable only where exactly one metastore is declared and its root is
    known: one undeclared or unknown leaves a catalog without a root of its own
    with nowhere this estate says its storage is.
    """
    metastores = declared(estate, "databricks_metastore")
    if len(metastores) != 1 or "storage_root" not in metastores[0].values:
        return None, False
    root = metastores[0].values["storage_root"]
    return (root if stated(root) else None), True
