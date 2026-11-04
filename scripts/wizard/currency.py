"""Whether a set is current with the module the skill ships.

A team that upgrades the skill can get a corpus with new, changed or removed
entries. The set it wrote earlier still measures as before, because it holds
what the team was shown and chose, so this never decides validity. It says
what moved: the questions the set never answered, the entries whose cards have
changed since the team chose from them, and the entries the corpus no longer
ships.

Advice is left out. A set records none, so a new or changed advice entry asks
the team nothing.
"""

from pathlib import Path

from wizard import corpus as corpus_module
from wizard.modules import module_of

ADVICE = "advice"


def compare(document, corpus_root):
    """The notice for a valid set, as data; `None` when the skill ships no
    module of the name the set records.

    `changed` is `None` for a set written before entry digests: new and removed
    entries can be told from the ids alone, a changed one cannot, and
    `corpus_digest_matches` says whether anything did.
    """
    module = module_of(document.get("module"))
    root = Path(corpus_root) / str(module)
    if not corpus_module.is_module(root):
        return None

    return notice_for(document, corpus_module.load_manifest(root), corpus_module.load(root))


def notice_for(document, manifest, entries):
    """The notice for `document` against one module, read already: its manifest
    and its loaded `entries`. The walk that appends to a set has both in hand."""
    module = module_of(document.get("module"))
    shipped = {e["id"]: e for _, e in entries if e.get("id") and e.get("kind") != ADVICE}
    adrs = document["adrs"]
    recorded = {adr["corpus_entry"] for adr in adrs}

    notice = {
        "module": module,
        "recorded_version": document["corpus"]["version"],
        "shipped_version": manifest["version"],
        "new": sorted(set(shipped) - recorded),
    }
    if all("corpus_entry_digest" in adr for adr in adrs):
        notice["changed"] = [
            {"adr": adr["id"], "corpus_entry": adr["corpus_entry"]}
            for adr in adrs
            if adr["corpus_entry"] in shipped
            and corpus_module.entry_digest(shipped[adr["corpus_entry"]])
            != adr["corpus_entry_digest"]
        ]
    else:
        notice["changed"] = None
        notice["corpus_digest_matches"] = (
            corpus_module.digest_of(entries) == document["corpus"]["digest"])
    notice["removed"] = [
        {"adr": adr["id"], "corpus_entry": adr["corpus_entry"]}
        for adr in adrs if adr["corpus_entry"] not in shipped
    ]
    return notice


def render(notice, module_recorded):
    """The notice as the lines that follow `<set> is valid`."""
    if notice is None:
        return [f"This skill ships no module {module_recorded!r}, so nothing was compared."]

    versions = (f"Written against {notice['module']} {notice['recorded_version']}; "
                f"this skill ships {notice['shipped_version']}.")
    changed = notice["changed"]
    moved = notice["new"] or notice["removed"] or changed or (
        changed is None and not notice["corpus_digest_matches"])
    if not moved:
        return [f"It is current with {notice['module']} {notice['shipped_version']}."]

    lines = [versions]
    if notice["new"]:
        lines.append(f"  new, not in this set:    {', '.join(notice['new'])}")
    if changed:
        lines.append("  changed since chosen:    " + ", ".join(
            f"{c['corpus_entry']} ({c['adr']})" for c in changed))
    if changed is None and not notice["corpus_digest_matches"]:
        lines.append("  entries may have changed; this set records no per-entry digests "
                     "to say which")
    if notice["removed"]:
        lines.append("  removed from the corpus: " + ", ".join(
            f"{r['corpus_entry']} ({r['adr']})" for r in notice["removed"]))
    return lines
