"""What makes a deviation the same finding as yesterday's.

An **identity** is the answer to *is this the same finding as the one in the
baseline?* The exception register records an exception for a deviation and
the gate fails a build on one that is new and has none; both are matching operations against
yesterday's finding, so an identity that moved between runs would break them
in opposite directions at once — exceptions stop matching their deviations, the
gate fires on drift the team already accepted, and the team's next move is to
switch it off.

It is established here, at the point a deviation is created, rather than in the
gate: a report that assigns identity unstably cannot be made stable later by
anything downstream of it.

**Four components, and a projection.** Which decision, what was checked, where,
and what it was checked on. The root is one of them because an estate is several
root modules and one estate address can occur in more than one —
`databricks_catalog.main` in `dev` is not the one in `prod`. The Terraform
address is *not* one of them, which is what makes a deviation survive a `moved`
block: `moved` blocks are ordinary hygiene, and a product that lost a team's
history every time they tidied a module would be punishing the refactor it
should be indifferent to.

**The components are stored and a digest is not.** An exception is a silence,
until withdrawn, approved by a person in a pull request, so what is being
silenced has to be legible to them. `rendered` produces the display form; it is
not a fifth field, for the reason a resolved failure message is not one either.

Nothing here reads a clock, calls `hash()`, or touches an object address or a
uuid. `hash()` is the trap the requirement names: Python salts string hashing
per process, so an identity built on it is stable within a run, stable across a
test suite that never restarts the interpreter, and different on the next
invocation — green everywhere until a baseline written yesterday meets a run
today.
"""

from dataclasses import dataclass

from wizard.outcomes import FAIL

# What separates the components in the display form. Wide enough to read at a
# glance in a pull request, and not a character an ADR id, an evaluator handle,
# a root name or an estate address carries.
SEPARATOR = " · "


@dataclass(frozen=True)
class Identity:
    """The four components, in the order they are read.

    Adding a fifth field, or dropping one, is a change to what identity means rather than an
    implementation detail — it changes which findings a year of exceptions
    still covers.
    """

    adr: str
    evaluator: str
    root: str
    estate_address: str


def identity_of(outcome):
    """`outcome`'s identity, or `None` where it is not a deviation.

    Only a deviation has one. A non-result is not a finding to record an
    exception for or to baseline, and an identity on it would invite both — so
    this returns `None` rather than a placeholder.

    Every component is read off the outcome and the rule it came from. Where
    evaluation could not produce a reproducible estate address it has already
    made the outcome UNEVALUATED, so no deviation without
    a stable identity ever reaches here.
    """
    if outcome.verdict != FAIL:
        return None
    return Identity(
        adr=outcome.rule.adr,
        evaluator=outcome.rule.evaluator,
        root=outcome.root,
        estate_address=outcome.estate_address,
    )


def rendered(identity):
    """The four components on one line, for a reader.

    Display only: `ADR-003 · catalog_isolation_isolated · prod · analytics` in a
    pull request can be reviewed; a sixteen-character digest cannot, and the
    reviewer approves it anyway.
    """
    return SEPARATOR.join((
        identity.adr,
        identity.evaluator,
        identity.root,
        identity.estate_address,
    ))
