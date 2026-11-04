"""The corpus validity table, implemented.

Hand-written rather than JSON Schema: a defective corpus halts the run,
"naming each defective entry and the rule it broke", and that message goes to a
maintainer who has to fix something. JSON Schema would turn a precise complaint
into `oneOf failed at #/entries/3`.

One entry yields at most one failure per rule. A maintainer fixing a corpus
wants the list of broken rules, not the same rule restated once per option.
"""

import hashlib
import json
from pathlib import Path

import yaml

from wizard.validity import (
    CORPUS_RULES,
    KINDS,
    RESERVED_KEYS,
    RULE_FIELDS,
    absence_message_failures,
    cloud_failures,
    scope_failures,
    substrate_failures,
    SILENT,
    CannotRun,
    Failure,
    is_stated,
)


MANIFEST_NAME = "corpus.yaml"

# All three are required of a corpus, and two of them leave it: `version` and
# `module` are copied into every set authored against this corpus. There is no `substrate`: an entry records a decision about a
# team's architecture, not about the tool that declares it, and the rules that
# *are* bound to one say so themselves through `rule.substrates`.
MANIFEST_FIELDS = ("schema_version", "version", "module")


def load_manifest(root):
    """Read `corpus/corpus.yaml`, or say this is not a corpus.

    A missing or incomplete manifest is `CannotRun` rather than a failure of
    the validity table: the table is applied per entry and its failures name an
    entry and the rule it broke, and a manifest names none. It is also what
    makes the failure cheap — a team meets it before the first card instead of
    after a completed run, which the write would then throw away.
    """
    path = Path(root) / MANIFEST_NAME
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CannotRun(f"{root} is not a corpus: {MANIFEST_NAME} — {exc}") from None
    if not isinstance(document, dict):
        raise CannotRun(f"{root} is not a corpus: {MANIFEST_NAME} is not a mapping")

    missing = [f for f in MANIFEST_FIELDS if not document.get(f)]
    if missing:
        raise CannotRun(
            f"{root} is not a corpus: {MANIFEST_NAME} declares no {', '.join(missing)}"
        )
    return document


def digest_of(entries):
    """A digest of the corpus, over the parsed entries rather than the bytes.

    Reflowed YAML, a reworded comment and a reordered mapping leave it alone;
    a changed rule, quote, option or citation date moves it. Hashing the files
    would be simpler and would mark every existing set stale for a typo fix in
    a comment — and under write-once a team cannot re-author to clear it, so a
    spurious staleness signal is a dead end rather than a nuisance.

    Advice counts. It is absent from the set and part of the corpus a team was
    walked through, and a digest ignoring it would report no change where what
    the team is shown had changed.
    """
    canonical = "\n".join(
        json.dumps(entry, sort_keys=True, ensure_ascii=False, default=str)
        for _, entry in entries
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def entry_digest(entry):
    """The digest of one entry, taken as `digest_of` takes the corpus's.

    Each ADR records the digest of the entry it came from, so a set can be told
    which of its entries have changed since it was written, not only that
    something has.
    """
    return digest_of([(None, entry)])


def entry_digests(entries):
    """`{entry id: digest}` for every entry that has an id."""
    return {entry["id"]: entry_digest(entry) for _, entry in entries if entry.get("id")}


def load(root):
    """Read a corpus directory into `[(relative path, entry), ...]`, ordered by
    path so that everything downstream is deterministic."""
    root = Path(root)
    entries_dir = root / "entries"
    if not entries_dir.is_dir():
        raise CannotRun(f"{root} is not a corpus: no entries/ directory")

    loaded = []
    for path in sorted(entries_dir.glob("*.yaml")):
        relative = path.relative_to(root).as_posix()
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise CannotRun(f"{relative} could not be read: {exc}") from None
        if not isinstance(document, dict):
            raise CannotRun(f"{relative} is not a mapping")
        loaded.append((relative, document))
    return loaded


# --- Shapes ----------------------------------------------------------------


def is_graded(entry):
    return "alternatives" in entry


def branches(entry):
    """A decision's options, or a graded prescription's alternatives — the two
    have the same shape and the table states the same rule for both."""
    return entry.get("options") if entry.get("kind") == "decision" else entry.get("alternatives")


def declared_keys(entry):
    """The keys a dependent entry may name for this entry."""
    kind = entry.get("kind")
    if kind == "decision":
        return {o.get("key") for o in entry.get("options") or [] if isinstance(o, dict)}
    if kind == "prescription":
        keys = set(RESERVED_KEYS)
        if is_graded(entry):
            keys |= {a.get("key") for a in entry.get("alternatives") or [] if isinstance(a, dict)}
        return keys
    return set()


def dependencies(entry):
    """Every `available_when` declaration on the entry, from both levels.

    An `available_when` on an individual option is an ordering constraint
    exactly as an entry-level one is, so both are edges of one graph.
    """
    declarations = []
    for source in (entry, *(b for b in (branches(entry) or []) if isinstance(b, dict))):
        available_when = source.get("available_when")
        if isinstance(available_when, dict):
            declarations.append(available_when)
    return declarations


def rules_in(entry):
    found = []
    if isinstance(entry.get("rule"), dict):
        found.append(entry["rule"])
    for branch in branches(entry) or []:
        if isinstance(branch, dict) and isinstance(branch.get("rule"), dict):
            found.append(branch["rule"])
    return found


def parameters_in(entry):
    """`[(option key | None, [declaration, ...]), ...]` — what this entry asks for.

    A parameter is declared on the state that needs it, because it is the state
    that gives it meaning: the environments exist under DEC-002's `environment`
    option and under its `both` option, and a team choosing `domain` is asked the
    same question for a different reason. An entry-level `rule` may declare them
    too, which is a single-state prescription asking for the names its one target
    state is about.
    """
    found = []
    if entry.get("parameters") is not None:
        found.append((None, entry.get("parameters")))
    for branch in branches(entry) or []:
        if isinstance(branch, dict) and branch.get("parameters") is not None:
            found.append((branch.get("key"), branch.get("parameters")))
    return found


def declared_parameters(entry):
    """Every parameter name this entry can record, whichever state declares it."""
    return {
        declaration.get("name")
        for _, declarations in parameters_in(entry)
        if isinstance(declarations, list)
        for declaration in declarations
        if isinstance(declaration, dict) and is_stated(declaration.get("name"))
    }


def parameter_failures(declarations):
    """Whether a `parameters` block is well formed, as one boolean."""
    if not isinstance(declarations, list) or not declarations:
        return True
    names = []
    for declaration in declarations:
        if not isinstance(declaration, dict):
            return True
        if not is_stated(declaration.get("name")) or not is_stated(declaration.get("question")):
            return True
        names.append(declaration["name"])
    return len(set(names)) != len(names)


def uses_in(rule):
    """The parameter names a rule declares it reads, as written.

    Returned unchecked: whether each names a parameter is the whole corpus's to
    say, and a declaration that is not a name at all fails that check rather
    than vanishing here.
    """
    return list(rule.get("uses") or [])


def well_formed_branches(collection, unconstrained=False):
    """≥2 branches, each with a key, a label and a rule; keys unique.

    `unconstrained` admits a branch carrying that field in place of its rule,
    which only a decision's options may:
    exactly one of the two, so a branch carrying both is as defective as one
    carrying neither. Whether the sentence says anything is a rule of its own.
    """
    if not isinstance(collection, list) or len(collection) < 2:
        return False
    keys = []
    for branch in collection:
        if not isinstance(branch, dict):
            return False
        if not all(branch.get(f) for f in ("key", "label")):
            return False
        stands_in = unconstrained and "unconstrained" in branch
        if stands_in == bool(branch.get("rule")):
            return False
        keys.append(branch["key"])
    return len(set(keys)) == len(keys)


def marked_twice(collection, marker):
    """Whether one card can offer two states that both carry `marker`.

    Two markers, and they say different things: `vendor_default` is what the
    vendor recommends, and `product_preferred` is what this product would
    choose where the vendor declines to. A team is shown both and neither
    decides anything — an option carrying one is still refused, chosen or
    pruned exactly like any other.

    Counted per card rather than per entry: two states that can never be
    offered together — a variant for each answer to an earlier entry — may each
    carry the marker, because no team ever sees both.
    """
    marked = [b for b in collection or [] if isinstance(b, dict) and b.get(marker)]
    return any(offered_together(a, b) for i, a in enumerate(marked) for b in marked[i + 1:])


def offered_together(first, second):
    """Whether one card can offer both states.

    Never, when both depend on the same earlier entry and no answer to it
    satisfies both. Anything else can coincide, so it counts as together.
    """
    a = first.get("available_when") if isinstance(first.get("available_when"), dict) else {}
    b = second.get("available_when") if isinstance(second.get("available_when"), dict) else {}
    return not any(
        isinstance(a[target], list) and isinstance(b[target], list)
        and not set(a[target]) & set(b[target])
        for target in a.keys() & b.keys()
    )


# --- Entry-level rules -----------------------------------------------------


def check_entry(path, entry):
    entry_id = entry.get("id")
    # An entry with no `id` is identified by its file path, because there is
    # nothing else to call it.
    name = [entry_id] if entry_id else []

    def failure(key):
        return Failure(CORPUS_RULES[key], list(name), path)

    failures = []
    kind = entry.get("kind")

    if not all(entry.get(f) for f in ("id", "kind", "title")) or kind not in KINDS:
        failures.append(failure("required_fields"))
        if kind not in KINDS:
            # Nothing kind-specific can be checked against a kind that does not
            # exist, and guessing would report rules the maintainer never broke.
            return failures

    vendor = entry.get("vendor") if isinstance(entry.get("vendor"), dict) else {}

    # The rule catches attribution, not absence. An entry reporting the vendor's
    # position has to produce it; one declaring the vendor silent is claiming
    # nothing and has nothing to cite. A missing `strength` attributes by
    # default, because an entry that says nothing about where its position came
    # from is not thereby exempt from saying.
    if kind in ("prescription", "advice") and vendor.get("strength") != SILENT:
        if not well_formed_source(vendor.get("source")) or not vendor.get("checked"):
            failures.append(failure("vendor_citation"))

    if kind == "prescription":
        if not entry.get("decision"):
            failures.append(failure("decision_field"))
        # Accepting a prescription is free and declining one costs a written
        # rationale. That asymmetry is defensible only if the team is
        # declining something that was argued rather than merely asserted, so
        # the argument is required whether or not a citation stands behind it.
        if not is_stated(entry.get("why")):
            failures.append(failure("why_field"))
        if ("rule" in entry) == ("alternatives" in entry):
            failures.append(failure("rule_xor_alternatives"))
        if is_graded(entry):
            if not well_formed_branches(entry.get("alternatives")):
                failures.append(failure("alternatives"))
            if marked_twice(entry.get("alternatives"), "vendor_default"):
                failures.append(failure("vendor_default"))
            if marked_twice(entry.get("alternatives"), "product_preferred"):
                failures.append(failure("product_preferred"))

    if kind == "decision":
        options = entry.get("options")
        if not well_formed_branches(options, unconstrained=True):
            failures.append(failure("options"))
        if isinstance(options, list):
            stated = [o for o in options if isinstance(o, dict)]
            if any("unconstrained" in o and not is_stated(o["unconstrained"]) for o in stated):
                failures.append(failure("unconstrained_stated"))
            # Every option left open would be a question whose every answer
            # measures nothing, which is advice and has a kind of its own.
            if stated and all("rule" not in o for o in stated):
                failures.append(failure("a_rule"))
        if marked_twice(entry.get("options"), "vendor_default"):
            failures.append(failure("vendor_default"))
        if marked_twice(entry.get("options"), "product_preferred"):
            failures.append(failure("product_preferred"))

    if kind == "advice":
        if not entry.get("fingerprint_reviewed"):
            failures.append(failure("fingerprint_reviewed"))
        if not entry.get("no_rule_because"):
            failures.append(failure("no_rule_because"))
        if "rule" in entry:
            failures.append(failure("advice_has_no_rule"))

    entry_rules = rules_in(entry)
    if any(not all(r.get(f) for f in RULE_FIELDS) for r in entry_rules):
        failures.append(failure("rule_fields"))
    # A handle is the whole identity of a check in the evaluator registry:
    # the compiled rule carries no option key, so two of an entry's
    # states sharing a handle are two target states the analyzer cannot tell
    # apart. Within the entry, not across the corpus — two entries asserting the
    # same state each carry their own ADR, and neither compiled rule is
    # ambiguous.
    handles = [r.get("evaluator") for r in entry_rules if r.get("evaluator")]
    if len(set(handles)) != len(handles):
        failures.append(failure("rule_evaluator_unique"))
    for broken in dict.fromkeys(
        b for r in entry_rules
        for b in (scope_failures(r) + cloud_failures(r) + substrate_failures(r)
                  + absence_message_failures(r))
    ):
        failures.append(failure(broken))

    if any(parameter_failures(declarations) for _, declarations in parameters_in(entry)):
        failures.append(failure("parameters_well_formed"))

    return failures


def well_formed_source(source):
    """Presence and well-formedness only. Fetching it would fail on a network
    blip and pass differently on Tuesday; whether the vendor still says what it
    said is what `vendor.checked` records."""
    return isinstance(source, str) and source.startswith(("http://", "https://"))


# --- Corpus-level rules ----------------------------------------------------


def split_qualified(target):
    """`("platform-core", "DEC-002")` for a key into another module, else
    `(None, target)`."""
    module, sep, entry_id = str(target).partition("/")
    return (module, entry_id) if sep else (None, target)


def check_dependencies(loaded, built_on=None):
    """`available_when` resolves, and the graph it forms is acyclic.

    `built_on` is `(module name, its loaded entries)` for a module whose manifest
    builds on another. A key into that module is qualified with its name, is
    satisfied by the set it produced rather than by this walk, and so is no edge
    of the graph: it was settled before the walk began.
    """
    by_id = {e["id"]: e for _, e in loaded if e.get("id")}
    other_name, other_loaded = built_on if built_on else (None, [])
    other = {e["id"]: e for _, e in other_loaded if e.get("id")}
    every_declared = set().union(
        *(declared_parameters(e) for e in (*by_id.values(), *other.values()))
    )

    failures = []
    graph = {}

    for path, entry in loaded:
        entry_id = entry.get("id")
        if not entry_id:
            continue
        unresolved = across = False
        targets = set()
        for declaration in dependencies(entry):
            for target, keys in sorted(declaration.items()):
                module, target_id = split_qualified(target)
                if module is not None:
                    if (module != other_name or target_id not in other
                            or not isinstance(keys, list)
                            or any(k not in declared_keys(other[target_id]) for k in keys)):
                        across = True
                    continue
                if target not in by_id:
                    unresolved = True
                    continue
                targets.add(target)
                allowed = declared_keys(by_id[target])
                if not isinstance(keys, list) or any(k not in allowed for k in keys):
                    unresolved = True
        if unresolved:
            failures.append(
                Failure(CORPUS_RULES["available_when_resolves"], [entry_id], path)
            )
        if across:
            failures.append(
                Failure(CORPUS_RULES["available_when_across"], [entry_id], path)
            )
        graph[entry_id] = sorted(targets)

        # `uses` resolves here rather than in `check_entry`, for the reason
        # `available_when` does: a rule may read a parameter another entry
        # declares, and only the whole corpus knows whether any entry declares
        # it. A name is one fact across the set, so the entry is not named.
        if any(
            not isinstance(name, str) or name not in every_declared
            for rule in rules_in(entry)
            for name in uses_in(rule)
        ):
            failures.append(
                Failure(CORPUS_RULES["rule_uses_resolves"], [entry_id], path)
            )

    # A cycle is a property of the set, so it is attributed to no single file —
    # the useful report is its membership, in the order that exhibits it.
    for cycle in find_cycles(graph):
        failures.append(Failure(CORPUS_RULES["acyclic"], cycle, None))
    return failures


def find_cycles(graph):
    """Every cycle in the graph, each as the sequence that exhibits it.

    Self-dependency is a one-member cycle and comes out of the same walk, so
    this is genuine cycle detection rather than a comparison of distinct ids.
    """
    UNVISITED, ON_PATH, DONE = 0, 1, 2
    colour = {}
    stack = []
    cycles = []
    seen = set()

    def visit(node):
        colour[node] = ON_PATH
        stack.append(node)
        for target in graph.get(node, []):
            state = colour.get(target, UNVISITED)
            if state == ON_PATH:
                cycle = stack[stack.index(target):] + [target]
                if frozenset(cycle) not in seen:
                    seen.add(frozenset(cycle))
                    cycles.append(cycle)
            elif state == UNVISITED:
                visit(target)
        stack.pop()
        colour[node] = DONE

    for node in sorted(graph):
        if colour.get(node, UNVISITED) == UNVISITED:
            visit(node)
    return cycles


# --- Entry point -----------------------------------------------------------


def validate_loaded(loaded, built_on=None):
    """Every rule the corpus breaks, given entries already read.

    Split from `validate` so a run can load once and keep the entries it will
    present, without a second read that could see a different corpus.
    """
    failures = []
    for path, entry in loaded:
        failures.extend(check_entry(path, entry))
    failures.extend(check_dependencies(loaded, built_on))
    return failures


def built_on_of(root, manifest):
    """`(module name, its loaded entries)` for the module `manifest` builds on,
    read from beside `root`; `None` for a module that builds on nothing."""
    name = manifest.get("builds_on")
    if not name:
        return None
    return name, load(Path(root).parent / name)


def is_module(root):
    """A module directory holds its own manifest; a corpus root holds modules."""
    return (Path(root) / MANIFEST_NAME).exists()


def validate(root):
    """Every rule broken, by one module or by every module under a corpus root.

    Under a root, each module's failures name their file under the module's
    directory, so a maintainer reading the report knows which module to open.
    The manifests are checked first, together: a broken one stops everything.
    """
    root = Path(root)
    if is_module(root):
        return validate_loaded(load(root), built_on_of(root, load_manifest(root)))

    from wizard.modules import catalog  # a leaf importing this module
    failures = []
    for name in catalog(root):
        for failure in validate(root / name):
            failures.append(Failure(failure.rule, failure.entries,
                                    f"{name}/{failure.file}" if failure.file else name))
    return failures
