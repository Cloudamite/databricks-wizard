"""DEC-001b in the account: what each of the estate's catalogs is reachable from.

Each catalog's outcome is filed under its metastore, with its name as the
estate address, since catalog names are unique within a metastore. The one
outcome filed elsewhere is a binding that lets a lower environment write to a
production catalog: it is filed under the workspace it binds, which is where it
would be removed.
"""

from wizard import outcomes
from wizard.live.estate import ISOLATED, OPEN, Located, workspace_place
from wizard.naming import environments_of, named_for


def catalog_isolation_open(rule, estate):
    """No catalog is ISOLATED. A catalog's mode is ISOLATED or OPEN: the audit
    refuses a snapshot holding any other."""
    if not estate.catalogs:
        return (_disclosed(rule),)
    return tuple(
        outcomes.passed(rule, catalog.place, catalog.name) if catalog.isolation_mode == OPEN
        else outcomes.failed(rule, catalog.place, catalog.name, catalog=catalog.name)
        for catalog in estate.catalogs)


def catalog_isolation_isolated(rule, estate):
    """Every catalog ISOLATED, and bound to at least one workspace.

    Bound is not checked: an ISOLATED catalog bound to no declared workspace is
    outside the estate, so every one measured here is."""
    if not estate.catalogs:
        return (_disclosed(rule),)
    return tuple(_isolated(rule, catalog) for catalog in estate.catalogs)


def catalog_isolation_read_only(rule, estate):
    """Every catalog ISOLATED and bound, and no binding from a lower environment
    writes to a production catalog.

    A binding's environment is the label the declaration gives the workspace it
    binds. A writable binding to a production catalog from
    a workspace with no label, or known only by id, cannot be placed, and the
    catalog earns no verdict rather than one resting on a guess.
    """
    recorded = environments_of(rule)
    if not estate.catalogs or not estate.environments:
        return (outcomes.unevaluable_as_disclosed(
            rule, None, otherwise="the estate holds no catalogs, or the declaration labels no "
                                  "workspace with the environment it holds"),)
    production, lower = recorded[-1], set(recorded[:-1])

    found = []
    for catalog in estate.catalogs:
        held = _isolated(rule, catalog)
        if held.verdict != outcomes.PASS or not named_for(catalog.name, production):
            found.append(held)
            continue
        writable = [b for b in catalog.bindings if b.writes]
        from_below = [b for b in writable if b.environment in lower]
        unplaced = [b for b in writable if b.environment is None]
        if from_below:
            found += [outcomes.failed(rule, Located(workspace_place(b.workspace)), catalog.name,
                                      catalog=catalog.name) for b in from_below]
        elif unplaced:
            found.append(outcomes.unevaluable_on(
                rule, catalog.place, estate_address=catalog.name,
                reason=f"{catalog.name} is writable from "
                       f"{', '.join(sorted(b.named for b in unplaced))}, which the declaration "
                       "labels with no environment, so whether a lower environment can write "
                       "to it cannot be said; labelling the workspace is what resolves it"))
        else:
            found.append(held)
    return tuple(found)


def _isolated(rule, catalog):
    if catalog.isolation_mode == ISOLATED:
        return outcomes.passed(rule, catalog.place, catalog.name)
    return outcomes.failed(rule, catalog.place, catalog.name, catalog=catalog.name)


def _disclosed(rule):
    return outcomes.unevaluable_as_disclosed(rule, None,
                                             otherwise="the estate holds no catalogs")
