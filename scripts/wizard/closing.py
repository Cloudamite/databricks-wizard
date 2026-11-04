"""What the team is told once the set has been written.

**The signature is the guarantee.** `report_for` is handed the path of the
record that just landed, not the run that produced it. The report must be
generated from the set as written, so that it cannot describe an entry
that was not written or omit one that was — and a function with no run in scope
cannot do either. A report built from the run's own memory would agree with the
artefact until the day it did not, and on that day the team believes the screen
and the analyzer reads the file.

**The one thing the file does not hold is advice.** It is kept out of the set
entirely: advice yields no rule, so it never becomes an ADR. The guarantee
above is about *entries*, and advice is not one, so the unattached
advice arrives as the second argument and is the only thing here that did not
come off disk. It is also the only place an unattached advice entry appears at
all — attached advice was shown beside its host during the run, and advice
naming no entry would otherwise be shipped in the corpus and read by nobody.

**Nothing reads this back.** The report is shown once and is not a record.
A second artefact describing the target state is one the set can
disagree with, and what a team keeps is the set.
"""

from pathlib import Path

import yaml

from wizard.card import Declined, LeftOpen, NotApplicable, Report
from wizard.validity import DECLINED

# The states the record uses for an entry nobody was shown, and for the origin
# of one the product adopted on the team's behalf. Both are the written record's
# vocabulary rather than the walk's, because this module reads the file.
INAPPLICABLE = "inapplicable"
CHOSEN = "chosen"
PRESCRIBED = "prescribed"

# Said here because there is nowhere else to say it. A team reading guidance in
# a closing report will otherwise assume the product checks it.
NO_RULE_NOTICE = (
    "This yields no rule. Nothing downstream will check it, and no divergence "
    "report will ever mention it."
)


def report_for(record_path, advice, recorded=()):
    """The closing card, read back off the set as written.

    `record_path` is what `write.write_set` returned; `advice` is the run's, from
    which the unattached are repeated. `recorded` names the ADRs an append found
    already in the set, and the report covers the rest; an append shows no
    unattached advice, so it has none to repeat. Nothing else is in scope,
    so the report cannot describe anything the set does not hold.
    """
    record_path = Path(record_path)
    record = yaml.safe_load(record_path.read_text(encoding="utf-8"))
    every = tuple(record.get("adrs") or ())
    titles = {adr["id"]: adr["title"] for adr in every}
    kept = set(recorded)
    adrs = tuple(adr for adr in every if adr["id"] not in kept)

    return Report(
        entries=len(adrs),
        paths=_paths(record_path),
        chosen=sum(1 for adr in adrs if adr.get("origin") == CHOSEN),
        prescribed=sum(1 for adr in adrs if adr.get("origin") == PRESCRIBED),
        declined=tuple(
            Declined(id=adr["id"], title=adr["title"], rationale=adr["rationale"])
            for adr in adrs
            if adr.get("state") == DECLINED
        ),
        left_open=tuple(
            LeftOpen(id=adr["id"], title=adr["title"], unconstrained=adr["unconstrained"])
            for adr in adrs
            if "unconstrained" in adr
        ),
        inapplicable=tuple(
            NotApplicable(
                id=adr["id"],
                title=adr["title"],
                because=adr["made_inapplicable_by"],
                # An ADR of the set this one builds on is named with its module,
                # and its title is in that set, not this one.
                because_title=titles.get(adr["made_inapplicable_by"]),
            )
            for adr in adrs
            if adr.get("state") == INAPPLICABLE
        ),
        unattached_advice=tuple(a for a in advice if a.relates_to is None),
        no_rule_notice=NO_RULE_NOTICE,
        left_as_recorded=len(every) - len(adrs),
    )


def _paths(record_path):
    """The record and every document beside it, as they are on disk.

    Read from the directory rather than derived from the entries: the set is
    what landed, and a list rebuilt from the record would describe the documents
    the write *meant* to produce.
    """
    directory = record_path.parent
    return (str(record_path),) + tuple(
        str(path) for path in sorted(directory.glob("*.md"))
    )
