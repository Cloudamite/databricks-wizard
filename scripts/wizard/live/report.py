"""The audit's report: the analyzer's report document, saying what an audit
measured.

`estate` holds the declared workspaces, the workspaces listed and not
declared, the visible catalogs not measured by type, the clouds and the
principal the snapshot was read as — no host, no account id. Outcomes carry
their place under `place` and no Terraform address key.
"""

from wizard.divergence import LIVE, assemble, measured_against


def report(document, estate, outcomes):
    """The structured report of one audit of `estate` against the set `document`."""
    measured = {
        "name": estate.name,
        "declared_workspaces": list(estate.workspaces),
        "undeclared_workspaces": list(estate.undeclared),
        "catalogs_not_measured": dict(estate.not_measured),
        "clouds": list(estate.clouds()),
    }
    if estate.principal is not None:
        measured["principal"] = estate.principal
    return assemble(document, measured_against(document, LIVE), measured, outcomes,
                    addresses=False)
