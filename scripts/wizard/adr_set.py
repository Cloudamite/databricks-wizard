"""The ADR-set validity table, implemented.

The analyzer refuses to run against an invalid set rather than measuring an
estate against something it cannot interpret, so this is the same machinery as
the corpus table run against a different list of rules.

Enforcement keys on whether `rule` is present — never on `origin`, never on
`state`. Nothing here branches on how an entry arrived.

The outcome of an entry is held in its options: exactly one is `chosen`, an
option an earlier answer removed is `pruned` and names what removed it, and an
option with no status was selectable and not taken. That is what these rules
check, and it is why there is no `decision` string and no `answer_key` to
disagree with them.
"""

import hashlib
import json
import re
from pathlib import Path

from wizard.validity import (
    ADR_SET_RULES,
    DECLINED,
    OPTION_STATUSES,
    RULE_FIELDS,
    absence_message_failures,
    cloud_failures,
    scope_failures,
    substrate_failures,
    SILENT,
    CannotRun,
    Failure,
    is_stated,
    read_mapping,
)

ID_PATTERN = re.compile(r"^ADR-\d{3}$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
PRODUCT_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
STATES = ("adopted", "declined", "inapplicable")
ORIGINS = ("chosen", "prescribed")


def adr_number(entry):
    """`ADR-050` sorts after `ADR-002`, by the number rather than the string.

    Here rather than in either consumer because it is a property of the set's
    id scheme, and two consumers order by it: compilation, so a rule set comes
    out in ADR order, and the report, so the entries it carries do. Two copies
    of one sort key is one that can come to disagree.

    The schema requires three digits, so a string sort would agree today.
    Keying on the number means it still agrees on the day a set carries four.
    """
    digits = "".join(c for c in str(entry.get("id", "")) if c.isdigit())
    return (int(digits) if digits else 0, str(entry.get("id", "")))


def set_digest(document):
    """A digest of the set, over the parsed document rather than its bytes.

    The report records it so that a command given a report and a set can check
    that the report measured that set; the corpus digest cannot, because two
    sets written from one corpus share it. Taken as `corpus.digest_of` takes the
    corpus's, so a reflowed file or an edited comment is the same set.

    The ADRs are taken in id order, so a set whose entries were reordered is the
    same set: an entry's position is not a fact about it.

    One implementation: the analyzer and every command that compares a report
    with a set call this one.
    """
    document = {**document, "adrs": sorted(document.get("adrs") or [], key=adr_number)}
    canonical = json.dumps(document, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def well_formed_parameters(recorded):
    """Whether an ADR's recorded parameters are values a rule can be read against.

    Absent is well formed: most ADRs record none, and a rule reading a parameter
    nothing recorded is compilation's case rather than the set's.

    An empty list is not. A rule reading it would measure every estate against
    nothing and pass, which is the shape of a check that is switched off and
    looks like one that holds. Duplicates are refused for the same reason one
    level down: two environments of one name make the catalog carrying them
    ambiguous, and a deviation found on it would have two identities.
    """
    if recorded is None:
        return True
    if not isinstance(recorded, dict) or not recorded:
        return False
    for name, values in recorded.items():
        if not is_stated(name):
            return False
        if not isinstance(values, list) or not values:
            return False
        if any(not is_stated(value) for value in values):
            return False
        if len(set(values)) != len(values):
            return False
    return True


def validate(path):
    document = read_mapping(path)
    name = Path(path).name
    failures = []

    def failure(key, entries=()):
        return Failure(ADR_SET_RULES[key], list(entries), name)

    corpus = document.get("corpus") if isinstance(document.get("corpus"), dict) else {}
    if not all(document.get(f) for f in ("schema_version", "module")) or not all(
        corpus.get(f) for f in ("version", "digest")
    ):
        failures.append(failure("set_fields"))

    if "product" in document and not (isinstance(document["product"], str)
                                      and PRODUCT_PATTERN.match(document["product"])):
        failures.append(failure("product_name"))

    built_on = document.get("builds_on")
    if "builds_on" in document and not (
            isinstance(built_on, dict) and is_stated(built_on.get("module"))
            and is_digest(built_on.get("digest"))):
        failures.append(failure("builds_on_shape"))
    # A reference into the set this one builds on is qualified with its module,
    # and only that module: an unqualified number is always this set's.
    across = (f"{built_on['module']}/" if isinstance(built_on, dict)
              and is_stated(built_on.get("module")) else None)

    adrs = document.get("adrs")
    if not isinstance(adrs, list):
        raise CannotRun(f"{name} declares no adrs list")

    entries = [a for a in adrs if isinstance(a, dict)]
    if len(entries) != len(adrs):
        raise CannotRun(f"{name} contains an ADR that is not a mapping")

    known_ids = {a.get("id") for a in entries}
    seen_ids, seen_corpus_entries = set(), set()

    def names_an_entry(reference):
        if isinstance(reference, str) and across and reference.startswith(across):
            return ID_PATTERN.match(reference[len(across):]) is not None
        return reference in known_ids

    # Every ADR or none: none is a set written before entry digests.
    digests = [a.get("corpus_entry_digest") for a in entries]
    if (any(d is not None for d in digests)
            and not all(is_digest(d) for d in digests)):
        failures.append(failure("entry_digests"))

    for adr in entries:
        adr_id = adr.get("id")
        here = [adr_id] if adr_id else []

        def broke(key):
            failures.append(failure(key, here))

        if not isinstance(adr_id, str) or not ID_PATTERN.match(adr_id) or adr_id in seen_ids:
            broke("id_format")
        seen_ids.add(adr_id)

        corpus_entry = adr.get("corpus_entry")
        if not corpus_entry or corpus_entry in seen_corpus_entries:
            broke("corpus_entry_unique")
        seen_corpus_entries.add(corpus_entry)

        state = adr.get("state")
        if adr.get("origin") not in ORIGINS or state not in STATES:
            broke("origin_and_state")

        if not well_formed_parameters(adr.get("parameters")):
            broke("parameters_well_formed")

        options = adr.get("options")
        options = options if isinstance(options, list) else []
        options = [o for o in options if isinstance(o, dict)]
        keys = [o.get("key") for o in options]
        if not all(keys) or len(set(keys)) != len(keys) or not all(
            o.get("status") in OPTION_STATUSES
            for o in options
            if o.get("status") is not None
        ):
            broke("options_well_formed")

        chosen = [o for o in options if o.get("status") == "chosen"]

        for option in options:
            if option.get("status") != "pruned":
                continue
            because = option.get("because") if isinstance(option.get("because"), dict) else {}
            if not names_an_entry(because.get("entry")):
                broke("pruned_provenance")
                break

        if state in ("adopted", "declined"):
            if len(chosen) != 1:
                broke("one_chosen")
            elif (chosen[0].get("key") == DECLINED) != (state == "declined"):
                broke("state_agrees")

        if state == "inapplicable" and "options" in adr:
            broke("options_absent")

        if state == "adopted":
            # An option left open carries its sentence where another carries a
            # rule, and never both: the rule is the chosen option's. Only a decision's options may be left open, and a
            # decision is the one kind whose entries arrive `chosen`.
            if ("rule" in adr) == ("unconstrained" in adr):
                broke("rule_or_unconstrained")
            if "unconstrained" in adr and (not is_stated(adr["unconstrained"])
                                           or adr.get("origin") != "chosen"):
                broke("unconstrained_stated")
            rule = adr.get("rule")
            if "rule" in adr and (not isinstance(rule, dict)
                                  or not all(rule.get(f) for f in RULE_FIELDS)):
                broke("rule_fields")
            if isinstance(rule, dict):
                for broken in (scope_failures(rule) + cloud_failures(rule)
                               + substrate_failures(rule) + absence_message_failures(rule)):
                    broke(broken)

        if state == "declined" and not adr.get("rationale"):
            broke("rationale")

        if state == "inapplicable" and not names_an_entry(adr.get("made_inapplicable_by")):
            broke("made_inapplicable_by")

        if state in ("declined", "inapplicable") and ("rule" in adr or "unconstrained" in adr):
            broke("rule_absent")

        if adr.get("origin") == "prescribed" and state != "inapplicable":
            # Two exemptions, for two different reasons. A citation is the
            # evidence behind an assertion, and an entry that never applied
            # asserts nothing — it was never presented, so there is no citation
            # a team was shown for it. An entry the vendor was silent on was
            # asserted on the product's own authority and claimed nothing to
            # cite. What is left is an entry invoking the vendor without
            # producing them, which is the only one borrowing authority it
            # does not have.
            vendor = adr.get("vendor") if isinstance(adr.get("vendor"), dict) else {}
            if vendor.get("strength") != SILENT:
                if not vendor.get("source") or not vendor.get("checked"):
                    broke("vendor_citation")

    failures.extend(
        failure("parameter_recorded_once", recorders)
        for recorders in recorded_twice(entries).values()
    )
    return failures


def is_digest(value):
    return isinstance(value, str) and DIGEST_PATTERN.match(value) is not None


def recorded_twice(entries):
    """`{name: [ADR id, ...]}` for each parameter name more than one ADR records.

    A rule reads a parameter by name, so two records of one name would leave
    compilation choosing between them — and the walk refuses to produce that,
    which leaves a hand-edited set as the only way to reach it.
    """
    recorders = {}
    for adr in entries:
        recorded = adr.get("parameters")
        for name in recorded if isinstance(recorded, dict) else ():
            recorders.setdefault(name, []).append(adr.get("id"))
    return {name: ids for name, ids in recorders.items() if len(ids) > 1}
