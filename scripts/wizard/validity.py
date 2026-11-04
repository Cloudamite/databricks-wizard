"""The published wording of every validity rule, and the shape of a failure.

A failure must state the rule it broke *in that rule's published wording*, so
these strings are transcribed from the published validity tables of the
corpus, the ADR set, the estate declaration and the exception register, with
markdown backticks dropped and nothing else paraphrased. They are the contract:
the test suite holds its own copy and asserts equality.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

# The corpus's validity table.
CORPUS_RULES = {
    "required_fields": "id, kind, title present; kind is one of the three",
    "vendor_citation": "vendor.source and vendor.checked present, unless vendor.strength is silent",
    "decision_field": "decision present and non-empty",
    "why_field": "why present and non-empty",
    "rule_xor_alternatives": "exactly one of rule or alternatives present",
    "options": (
        "≥2 options, each with key, label, and exactly one of rule or unconstrained; keys unique"
    ),
    "unconstrained_stated": "unconstrained, where present, is a non-empty string",
    "a_rule": "at least one option carries a rule",
    "alternatives": "≥2 alternatives, each with key, label, rule; keys unique",
    "vendor_default": (
        "at most one vendor_default: true among the states that can be offered together"
    ),
    "product_preferred": (
        "at most one product_preferred: true among the states that can be offered together"
    ),
    "fingerprint_reviewed": "fingerprint_reviewed present",
    "available_when_resolves": (
        "every available_when names an entry and keys that exist — an option key, "
        "an alternative key, or the reserved accepted / declined on a prescription"
    ),
    "available_when_across": (
        "an available_when key naming another module is qualified <module>/<entry id>, "
        "the module is the one the manifest's builds_on names, and the entry and keys "
        "exist there"
    ),
    "acyclic": (
        "the available_when graph is acyclic, counting entry-level and option-level "
        "declarations as edges of one graph"
    ),
    "no_rule_because": "no_rule_because present",
    "advice_has_no_rule": "no rule",
    "rule_fields": (
        "rule.summary, rule.failure_message, rule.evaluator, rule.enforceability, "
        "rule.scope, rule.clouds present"
    ),
    "rule_scope": "rule.scope is one of root, estate",
    "rule_clouds": "every cloud in rule.clouds is one of aws, azure, gcp",
    "rule_substrates": (
        "rule.substrates, where present, is a non-empty list of terraform, bundle"
    ),
    "rule_absence_message": "rule.absence_message, where present, is a non-empty string",
    "rule_evaluator_unique": "no two rules in one entry name the same evaluator",
    "parameters_well_formed": (
        "every declared parameter has a name and a question, and names are unique "
        "within the option declaring them"
    ),
    "rule_uses_resolves": (
        "every rule.uses names a parameter some entry in this module, or in the module "
        "it builds on, declares"
    ),
}

# The ADR set's validity table.
ADR_SET_RULES = {
    "set_fields": "schema_version, module, corpus.version, corpus.digest present",
    "product_name": (
        "product, where present, is lowercase letters and digits in groups joined by "
        "single hyphens"
    ),
    "builds_on_shape": (
        "builds_on, where present, gives module and a digest of the form sha256: and 64 "
        "hex digits"
    ),
    "entry_digests": (
        "corpus_entry_digest is recorded by every ADR or by none, and where present has "
        "the form sha256: and 64 hex digits"
    ),
    "id_format": "id unique and matching ADR-\\d{3}",
    "corpus_entry_unique": "corpus_entry unique — one ADR per corpus entry, never two",
    "origin_and_state": "origin is chosen or prescribed; state is one of the three",
    "options_well_formed": (
        "every option has a key, keys unique; every status is chosen or pruned"
    ),
    "one_chosen": "exactly one option is chosen",
    "pruned_provenance": (
        "a pruned option names the entry that pruned it: unqualified, an entry in this "
        "set; qualified, the module builds_on names"
    ),
    "state_agrees": "state is declined exactly when the chosen option is declined",
    "options_absent": "options absent",
    "rationale": "rationale present and non-empty",
    "made_inapplicable_by": (
        "made_inapplicable_by names an entry: unqualified, in this set; qualified, of the "
        "module builds_on names"
    ),
    "rule_or_unconstrained": "exactly one of rule or unconstrained present",
    "unconstrained_stated": (
        "unconstrained, where present, is a non-empty string, and the entry's origin is chosen"
    ),
    "rule_fields": (
        "rule, where present, carries summary, failure_message, evaluator, enforceability, "
        "scope, clouds"
    ),
    "rule_scope": "rule.scope is one of root, estate",
    "rule_clouds": "every cloud in rule.clouds is one of aws, azure, gcp",
    "rule_substrates": (
        "rule.substrates, where present, is a non-empty list of terraform, bundle"
    ),
    "rule_absence_message": "rule.absence_message, where present, is a non-empty string",
    "rule_absent": "rule and unconstrained absent",
    "vendor_citation": "vendor.source and vendor.checked present, unless vendor.strength is silent",
    "parameters_well_formed": (
        "every recorded parameter names a parameter and gives a non-empty list of "
        "distinct, non-empty strings"
    ),
    "parameter_recorded_once": (
        "no parameter name is recorded by more than one ADR — a name is one fact per set"
    ),
}

# The option a prescription's opt-out selects. It compiles to no rule, which is
# what makes a declined entry the same shape as an adopted one.
# The estate declaration's validity table.
#
# Self-contained by design: no rule here reads the ADR set. That the
# declaration's substrate must agree with the set's is a cross-artefact check
# and belongs to the analyzer, which has both. A table
# that referenced another file could not be run against the declaration alone,
# and standalone checkability is the point of having one — this is the only
# artefact a team writes by hand.
ESTATE_RULES = {
    "schema_version": "schema_version present and an integer",
    "name": "name present and non-empty",
    "substrate": "substrate present and non-empty",
    "roots": "roots present and non-empty",
    "root_name": "every root has a name, present and non-empty",
    "root_names_unique": "root names are unique",
    "root_environment": (
        "every root environment, where present, is a non-empty string"
    ),
    "state": "state, where present, is a mapping of exactly bucket and region",
    "state_values": "state.bucket and state.region are non-empty strings",
}

# The exception register's validity table.
#
# Self-contained, for the declaration's reason: a register is written by hand
# as often as by the exceptions command. The two rules that need the
# declaration are kept apart in `REGISTER_AGAINST_RULES`, applied only by a
# caller that has one.
REGISTER_RULES = {
    "schema_version": "schema_version present and a version this build knows",
    "estate": "estate present and a non-empty string",
    "exceptions": "exceptions present and a mapping, possibly empty",
    "top_level": "no top-level key but these three",
    "sections": (
        "every section name a non-empty string, and every section a list, possibly empty"
    ),
    "identity": (
        "identity present, holding exactly adr, evaluator and estate_address, each a "
        "non-empty string"
    ),
    "reason": "reason present, a non-empty string, with no line break",
    "issue": "issue, where present, an absolute http or https URL with no user or password",
    "entry_keys": "no key in an exception but identity, reason and issue",
    "identity_unique": "no two exceptions in one section with the same identity",
    "duplicate_key": "no key twice in one mapping",
}

# The live estate declaration's validity table.
#
# Self-contained for the estate declaration's reason, and closed where that one
# is open: a key this table does not name is defective, so a `host` written into
# the file cannot look as though it chose the account the reader reaches.
LIVE_RULES = {
    "schema_version": "schema_version is the integer 1",
    "name": "name is a non-empty string",
    "workspaces": "workspaces present, a list, and non-empty",
    "workspace_name": "every workspace's name is a non-empty string",
    "workspace_names_unique": "no two workspaces share a name",
    "workspace_environment": (
        "every workspace's environment, where present, is a non-empty string"
    ),
    "keys": (
        "no key but schema_version, name and workspaces at the top level, "
        "or name, environment and note in a workspace"
    ),
}

# The exception register's rules against the declaration.
REGISTER_AGAINST_RULES = {
    "estate_matches": "estate equals the declaration's name",
    "sections_declared": "every section names a root the declaration declares",
}

# What a top-level key says the file is. Each is required by its own schema,
# so this reads what a document declares itself to be rather than guessing from
# a path — an inference the analyzer refuses, where two interchangeable
# paths could only be told apart by the order they were given in.
# Each key is also required by its artefact's validity table, so an absent one
# surfaces as *unrecognised* rather than as *invalid*. That is the honest
# result: a file declaring none has not said what it is, and checking it
# against a table it never claimed would report failures its author cannot act
# on. `roots: []` still reaches the rule, being the key present and the claim
# made explicitly.
ARTEFACT_KEYS = (("adrs", "adr-set"), ("roots", "estate"), ("exceptions", "register"),
                 ("workspaces", "live-declaration"))

# The key that may not share a file with another artefact's. The first three were told apart by key order and no file has carried two;
# a live declaration and an estate declaration are the pair a team is likeliest
# to merge by hand, so that pair is refused rather than resolved by order.
LIVE_KEY = "workspaces"


def read_mapping(path):
    """A YAML document that must be a mapping, or `CannotRun`.

    Shared by every reader of a single file, and by the entry point, which
    reads one to learn which artefact it is before handing it to the reader
    that checks it. One loader means one wording for *could not be read*,
    whichever artefact the caller turned out to be holding.
    """
    path = Path(path)
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CannotRun(f"{path.name} could not be read: {exc}") from None
    if not isinstance(document, dict):
        raise CannotRun(f"{path.name} is not a mapping")
    return document


def artefact_of(document):
    """Which validity table a mapping is to be read against, or None.

    One place knows this, so an entry point and a reader cannot come to
    different conclusions about the same file.
    """
    if not isinstance(document, dict):
        return None
    if LIVE_KEY in document:
        others = [key for key, _ in ARTEFACT_KEYS if key != LIVE_KEY and key in document]
        if others:
            carried = ", ".join([LIVE_KEY, *others])
            raise CannotRun(
                f"the file carries {carried}, so it is more than one artefact; a live "
                "estate declaration is a file of its own"
            )
    for key, artefact in ARTEFACT_KEYS:
        if key in document:
            return artefact
    return None


DECLINED = "declined"

# The vendor strength that claims nothing. On a decision it means the question
# is the team's alone; on a prescription it means the product is asserting on
# its own authority, and there is then no citation to demand — the rule catches
# an entry borrowing the vendor's authority, not one declining to.
SILENT = "silent"


def is_stated(text):
    """Present, a string, and not only whitespace.

    Shared by every rule that requires something to have been *said* rather than
    merely to exist as a key. A rule satisfied by `"   "` asserts that a string
    is not blank, which is not what any of them mean.
    """
    return isinstance(text, str) and bool(text.strip())

# The statuses an option may carry. An option with none was selectable and the
# team did not take it, which is the ordinary case and therefore unmarked.
OPTION_STATUSES = ("chosen", "pruned")

KINDS = ("decision", "prescription", "advice")

# Reserved dependency keys on a prescription. `accepted` is a wildcard over any
# adopted state rather than a key an entry declares, so adding an alternative to
# a prescription does not require editing the entries that depend on it.
RESERVED_KEYS = ("accepted", "declined")

RULE_FIELDS = ("summary", "failure_message", "evaluator", "enforceability", "scope", "clouds")

# What a rule is evaluated over. Closed and shipped for the same reason CLOUDS
# is: a third value would name a boundary the analyzer has no way to assemble.
# `root` is each supplied plan on its own; `estate` is the union of them all,
# and is evaluable only when every declared root was supplied.
SCOPES = ("root", "estate")

# The cloud identifiers a rule may claim a fingerprint for. Closed and shipped:
# a corpus that could name a fourth would be claiming a fingerprint the
# analyzer has no provider to detect, so the rule would match no estate ever.
# The analyzer fixes the same three on its side.
CLOUDS = ("aws", "azure", "gcp")

# The substrates a rule may declare itself bound to. Closed and shipped for the
# same reason CLOUDS is, and read the same way: `substrates` absent means the
# rule is true of every substrate, which is the ordinary case. Only an entry
# whose subject is the IaC layer itself — a destroy guard, who owns a grant
# list — names one, and naming one is what lets the analyzer report
# *no dialect for this estate* rather than measure the wrong thing.
SUBSTRATES = ("terraform", "bundle")


def scope_failures(rule):
    """Whether a rule block names a scope this product can evaluate.

    Presence is `rule_fields`' business, exactly as an absent `clouds` is — a
    missing scope and a misspelt one are different mistakes, and reporting the
    first one twice would have a maintainer fixing it against two lines.
    """
    scope = rule.get("scope")
    if not scope:
        return []
    return [] if scope in SCOPES else ["rule_scope"]


def cloud_failures(rule):
    """Whether a rule block names a cloud this product can detect.

    Presence and non-emptiness of `clouds` is `rule_fields`' business — an
    empty list is falsy, so a rule claiming no clouds fails there rather than
    here. What is left is the vocabulary: a typo in a cloud name.
    """
    clouds = rule.get("clouds")
    if not clouds:
        # Absent or empty is `rule_fields`, and reporting it twice would have a
        # maintainer fixing one mistake against two lines.
        return []
    if not isinstance(clouds, list) or any(c not in CLOUDS for c in clouds):
        return ["rule_clouds"]
    return []


def substrate_failures(rule):
    """Whether a rule block's `substrates`, if it declares one, is well formed.

    Unlike `clouds` this field is optional, so absence is valid and is not
    `rule_fields`' business. Present-but-empty is a failure here rather than
    there: a rule claiming no substrate at all could never be evaluated, and
    the mistake is in this field rather than in a missing one.
    """
    declared = rule.get("substrates")
    if declared is None:
        return []
    if not isinstance(declared, list) or not declared:
        return ["rule_substrates"]
    return [] if all(s in SUBSTRATES for s in declared) else ["rule_substrates"]


def absence_message_failures(rule):
    """Whether a rule block's `absence_message`, if it declares one, is a sentence.

    Optional like `substrates`, so absence is valid. Present and empty, null or
    not a string is a failure rather than a silent fall-back to
    `failure_message`: a maintainer who wrote the key meant to say something,
    and the report would otherwise quietly say something else.
    """
    if "absence_message" not in rule:
        return []
    message = rule["absence_message"]
    return [] if isinstance(message, str) and message.strip() else ["rule_absence_message"]


class CannotRun(Exception):
    """The check could not be performed — bad usage, or an artefact that could
    not be read or parsed.

    Distinct from every failure below, because *invalid* and *could not run*
    are different results and a CI stage that conflates them passes green on an
    agent where nothing was checked at all.
    """


class Refused(Exception):
    """Something the team can supply. Exit `1`."""


@dataclass(frozen=True)
class Failure:
    """One broken rule.

    `entries` is a list because a rule that applies to the corpus rather than to
    an entry — a dependency cycle — implicates several entries in the order that
    exhibits it. It is empty when `id` is itself what is missing, and `file`
    names the entry instead.
    """

    rule: str
    entries: List[str] = field(default_factory=list)
    file: Optional[str] = None

    def as_dict(self):
        return {"rule": self.rule, "entries": list(self.entries), "file": self.file}
