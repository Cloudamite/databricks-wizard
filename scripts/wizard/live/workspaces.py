"""DEC-001a in the account: the declared workspaces' names against the axis.

The same target states the Terraform dialect measures, read off the names the
declaration gives and the account lists: a workspace per environment is named
for it, one per business unit and environment is named `<unit>_<environment>`
(`naming.split_name`). Every outcome is filed under `account`, where workspaces
live, and a missing workspace is a deviation there too — the account is where
it would have been created.

Only declared workspaces are measured. The declaration
refuses two workspaces of one name, so no name here occurs twice.
"""

from wizard import outcomes
from wizard.naming import SEPARATOR, environments_of, split_name


def workspace_axis_environment(rule, estate):
    """Exactly one workspace named for each environment; others pass."""
    return _by_name(rule, estate, lambda name, recorded: True,
                    expected=lambda recorded, named: list(recorded))


def workspace_axis_unit(rule, estate):
    """No workspace is named for an environment."""
    return _by_name(rule, estate, lambda name, recorded: split_name(name)[1] not in recorded)


def workspace_axis_both(rule, estate):
    """Every workspace is `<unit>_<environment>`, and every unit has one in
    every recorded environment."""
    def follows(name, recorded):
        unit, environment = split_name(name)
        return bool(unit) and environment in recorded

    def expected(recorded, named):
        units = sorted({split_name(name)[0] for name in named if follows(name, recorded)})
        return [f"{unit}{SEPARATOR}{environment}" for unit in units for environment in recorded]

    return _by_name(rule, estate, follows, expected)


def workspace_axis_single(rule, estate):
    """Exactly one declared workspace. A count deviation lands on every
    workspace that constitutes it, so identity needs one workspace."""
    count = len(estate.workspaces)
    if count == 1:
        return tuple(outcomes.passed(rule, estate.account, name) for name in estate.workspaces)
    return tuple(outcomes.failed(rule, estate.account, name, count=count)
                 for name in estate.workspaces)


def _by_name(rule, estate, holds, expected=None):
    recorded = environments_of(rule)
    found = [outcomes.passed(rule, estate.account, name) if holds(name, recorded)
             else outcomes.failed(rule, estate.account, name, workspace=name)
             for name in estate.workspaces]
    if expected is not None:
        found += [outcomes.missing(rule, estate.account.root, name, workspace=name)
                  for name in expected(recorded, estate.workspaces)
                  if name not in estate.workspaces]
    return tuple(found)
