"""The human rendering of a divergence report.

`render` takes the structured report and nothing else. That is the whole of this
module's design, and it is a signature rather than a promise: with no
`Preparation`, no outcome sequence and no path in scope, a rendering that
recounted the deviations or re-read a plan could not be written here. A second
implementation of the report would agree with the first until the day it did
not, and the day it does not, the team believes the screen.

**What it may do is label.** The rendering groups or labels by cause and says
what resolves each, so the class-to-remedy
table below is presentation, not a fact recomputed from data the report already
carries. The report says which class an outcome is in; this says what a team
does about that class.

**Three things it must never say.** *Passing*, *clean*, or anything a reader
could take for either, in a run that did not evaluate everything — a conformant
estate and an unmeasurable one are different positions, and collapsing them is
how a team comes to trust a gate that is checking nothing. And a deviation count
is never a build verdict: a team reading a non-zero exit and a list, with
nothing telling them otherwise, will wire it up as a pass/fail step, and the
product would then fail their build on day-one drift.

**The head is the position**, never the first deviation. Where no cloud was
recognised it leads with that one fact rather than repeating it against every
rule.
"""

from wizard.divergence import LIVE, place_key
from wizard.outcomes import (
    COVERAGE_SIDE,
    ESTATE_SIDE,
    INSTALLATION_SIDE,
    PRODUCT_SIDE,
)

# What each class means for the reader, in the order a team should read them:
# theirs to fix today first, then the one that may fix itself, then the two that
# wait on someone else. Naming the class is insufficient if acting on it
# requires knowing the product's internals.
REMEDIES = (
    (COVERAGE_SIDE, "awaiting a plan for a root this estate declares — "
                    "a change to your pipeline, today"),
    (ESTATE_SIDE, "awaiting the estate; this may resolve on its own as the estate grows"),
    (PRODUCT_SIDE, "awaiting a fingerprint a corpus maintainer must author; "
                   "no upgrade delivers one until they do"),
    (INSTALLATION_SIDE, "awaiting an upgrade of this product"),
)

# An audit has no plans and no roots: what it was not shown is the storage a
# snapshot was read without.
LIVE_REMEDIES = tuple(
    (cause, "awaiting the storage this snapshot was read without — read the account "
            "again with storage, today")
    if cause == COVERAGE_SIDE else (cause, remedy)
    for cause, remedy in REMEDIES)

# Wrapped where it is written rather than by a wrapper at render time: these
# are the two paragraphs in the whole output, and a wrapping pass would be a
# second thing to keep true for the sake of two strings.
MEASUREMENT = (
    "This count is a measurement, not a build verdict. Deciding what fails a\n"
    "build means evaluating this report against the exceptions your team has\n"
    "already recorded."
)

NO_CLOUD = (
    "No cloud this product recognises was configured by the plans supplied, so\n"
    "every rule below is reported product-side for that one reason."
)

RULE = "-" * 78


def render(report):
    """The report as a page, derived from the report and from nothing else."""
    lines = []
    lines += _head(report)
    lines += _by_root(report)
    lines += _deviations(report)
    lines += _unevaluated(report)
    lines += _not_enforced(report)
    return "\n".join(_spaced(lines)).rstrip() + "\n"


def _spaced(lines):
    """One blank line between blocks, never two.

    Each section ends its own entries with a blank and the next begins with
    one, which is the right shape for each read alone and two blanks where they
    meet. Collapsing here keeps that local correctness.
    """
    spaced = []
    for line in lines:
        if line == "" and spaced and spaced[-1] == "":
            continue
        spaced.append(line)
    return spaced


def _head(report):
    """The position: the counts, the clouds, and what this was measured against.

    The unevaluated total stands beside the deviation count rather than below
    the list, because *zero deviations, four rules unevaluated* and *zero
    deviations, zero rules unevaluated* are different facts about a team's
    position.
    """
    counts = report["counts"]
    estate = report["estate"]
    against = report["measured_against"]

    live = against["substrate"] == LIVE
    title = "Audit of the live account" if live else "Divergence report"
    lines = [
        f"{title} — estate {estate['name']!r}",
        RULE,
        f"{counts['deviations']} {_plural(counts['deviations'], 'deviation')}"
        f"    {counts['unevaluated']} unevaluated"
        f"    {counts['conformant']} conformant"
        f"    {counts['not_enforced']} not enforced",
    ]

    if counts["unevaluated"]:
        lines.append("  by cause: " + "    ".join(
            f"{cause} {counts['by_cause'][cause]}"
            for cause, _ in REMEDIES if counts["by_cause"][cause]))

    lines += [
        "",
        f"clouds detected: {_listed(estate['clouds']) or 'none'}",
        f"substrate: {against['substrate']}",
        *(_live_scope(estate) if live else [
            f"roots covered: {_listed(estate['covered_roots']) or 'none'}"
            f"  of {_listed(estate['declared_roots'])} declared",
            *_placeholders(estate['placeholders'])]),
        f"measured against: module {against['module']}, "
        f"corpus {against['corpus']['version']} ({against['corpus']['digest']})",
    ]

    if not estate["clouds"]:
        lines += ["", NO_CLOUD]
    if counts["deviations"]:
        lines += ["", MEASUREMENT]
    return lines


def _placeholders(placeholders):
    """Which roots' variables were placeholders, copied from the report."""
    if not placeholders:
        return ["placeholder values: none; every plan carried the team's own values"]
    return ["placeholder values:",
            *(f"  {root}: {', '.join(names)}" for root, names in placeholders.items()),
            "  These roots measure the Terraform as written, not the values you deploy with."]


def _live_scope(estate):
    """What an audit read, and as whom: the principal bounds every claim in it,
    since a catalog it cannot see is absent rather than conformant."""
    lines = [f"read as: {estate.get('principal') or 'not recorded'}",
             f"workspaces measured: {_listed(estate['declared_workspaces'])}"]
    if estate["undeclared_workspaces"]:
        lines.append("workspaces listed, not declared, not measured: "
                     f"{_listed(estate['undeclared_workspaces'])}")
    if estate["catalogs_not_measured"]:
        lines.append("catalogs not measured: " + ", ".join(
            f"{kind} {count}" for kind, count in estate["catalogs_not_measured"].items()))
    return lines


UNPLACED = {"root": "not placed in one root", "place": "not placed in one place"}


def _by_root(report):
    """The position one root at a time, copied from `counts.by_root`.

    Root-scoped rules run once per root, so a non-result in `account` says
    nothing about `dev`. Printed beneath the estate's position rather than in
    place of it: the head is still the estate's, and this is where a reader
    finds which root a number belongs to.
    """
    rows = report["counts"].get("by_root") or []
    if not rows:
        return []
    place = place_key(report["measured_against"])
    lines = ["", f"By {place}", RULE]
    width = max(len(_place_label(row[place], place)) for row in rows)
    for row in rows:
        causes = ", ".join(f"{cause} {row['by_cause'][cause]}"
                           for cause, _ in REMEDIES if row["by_cause"].get(cause))
        lines.append(
            f"{_place_label(row[place], place):<{width}}"
            f"    {row['deviations']} {_plural(row['deviations'], 'deviation')}"
            f"    {row['unevaluated']} unevaluated" + (f" ({causes})" if causes else "") +
            f"    {row['conformant']} conformant")
    return lines


def _place_label(value, place):
    return value if value is not None else UNPLACED[place]


def _heading(value, place):
    """A group's heading: `root account`, or the unplaced label as itself."""
    return f"{place} {value}" if value is not None else UNPLACED[place]


def _by_place(report, entries, key):
    """`entries` grouped under the place each belongs to, in `counts.by_root`'s
    order: `(heading, entries)` pairs, one per place that has any.

    `key` reads an entry's place. Grouped rather than tagged, so that a reader
    looking for `account` reads one block rather than scanning every line.
    """
    place = place_key(report["measured_against"])
    order = [row[place] for row in report["counts"].get("by_root") or []]
    order += [value for value in dict.fromkeys(key(e) for e in entries) if value not in order]
    groups = []
    for value in order:
        held = [e for e in entries if key(e) == value]
        if held:
            groups.append((_heading(value, place), held))
    return groups


def _deviations(report):
    if not report["deviations"]:
        return []
    lines = ["", "Deviations", RULE]
    place = place_key(report["measured_against"])
    for heading, held in _by_place(report, report["deviations"],
                                   lambda d: d["identity"][place]):
        lines.append(heading)
        for deviation in held:
            identity = deviation["identity"]
            lines += [
                "  " + " · ".join((identity["adr"], identity["evaluator"],
                                   identity["estate_address"])),
                f"      {deviation['message']}",
            ]
            lines += _expected(deviation["expected"], "      ")
            # A deviation found by *absence* has no block to point a team at.
            # The line is omitted rather than printed
            # empty: "found at: None" reads as a defect in the tool, and sends a
            # reader looking for a resource whose whole finding is that it is not
            # there.
            if deviation.get("terraform_address"):
                lines.append(f"      found at: {deviation['terraform_address']}")
        lines.append("")
    return lines


def _expected(summary, indent="    "):
    """The rule's summary, indented under its own label.

    A summary states a target state in clauses and carries the newlines between
    them, so printing it into one line put every clause after the first hard
    against the left margin — under the label, and reading like the start of a
    new entry. Rendering is where that is fixed: the report carries the
    maintainer's words unchanged, and this is a page.
    """
    first, *rest = (summary or "").rstrip().split("\n")
    return [f"{indent}expected: {first}"] + [f"{indent}          {line}" for line in rest]


def _unevaluated(report):
    """The non-results, grouped by class, each group saying what resolves it.

    Grouped rather than interleaved so that a team reading a report of
    non-results — which a fresh estate's first report is expected to be — can
    see at once which of them are theirs.
    """
    if not report["unevaluated"]:
        return []
    lines = ["", "Not evaluated", RULE]
    place = place_key(report["measured_against"])
    remedies = LIVE_REMEDIES if report["measured_against"]["substrate"] == LIVE else REMEDIES
    for cause, remedy in remedies:
        of_this_cause = [e for e in report["unevaluated"] if e["cause"] == cause]
        if not of_this_cause:
            continue
        lines += [f"{cause} ({len(of_this_cause)}) — {remedy}"]
        for heading, held in _by_place(report, of_this_cause, lambda e: e[place]):
            lines.append(f"  {heading}")
            for entry in held:
                lines += [f"    {entry['adr']} · {entry['evaluator']}",
                          f"        {entry['reason']}"]
        lines.append("")
    return lines


def _not_enforced(report):
    """The entries the set carries and does not enforce, with why.

    Listed so that *measured and conformant* stays distinguishable from *not
    measured at all*: an entry absent from the report cannot be told from an
    entry the team never saw.
    """
    if not report["not_enforced"]:
        return []
    lines = ["", "Carried, not enforced", RULE]
    for entry in report["not_enforced"]:
        because = entry.get("rationale") or entry.get("unconstrained") or (
            f"made inapplicable by {entry['made_inapplicable_by']}"
            if entry.get("made_inapplicable_by") else "no rule was compiled from it")
        lines += [f"{entry['adr']} · {entry['state']} · {entry['title']}",
                  f"    {because}"]
    lines.append("")
    return lines


def _plural(count, noun):
    return noun if count == 1 else f"{noun}s"


def _listed(values):
    return ", ".join(values)
