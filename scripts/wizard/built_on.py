"""The set a walk builds on: read, checked, and offered to the walk as answers.

A product team decides inside the space the platform team left open, so a walk
for a module that builds on another starts from the set that module produced.
It is required, not optional: answers given without the platform's decisions in
view could contradict them, and nothing would say so.

**What the walk takes from it is answers and names, never copies.** Each entry
the set records is offered as the answer it holds, under the ADR number the set
gave it, qualified with the module — `platform-core/ADR-003` — because both sets
number from `ADR-001`. The new set records only the module and the digest of the
set it built on, and never where that set was found.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from wizard.adr_set import set_digest
from wizard.card import Because
from wizard.modules import PLATFORM_FOLDER, module_of
from wizard.target import RECORD_NAME
from wizard.validity import CannotRun, read_mapping


@dataclass(frozen=True)
class Answer:
    """What the set built on records for one corpus entry.

    `answer` is the chosen option's key, or `None` for an entry the set records
    as inapplicable. `prescribed` lets `accepted` match any adopted state of a
    prescription, exactly as it does within one walk.
    """

    ref: str
    answer: Optional[str]
    prescribed: bool


@dataclass(frozen=True)
class BuiltOn:
    """The set a walk builds on, as the walk and the write need it."""

    module: str
    digest: str
    answers: Dict[str, Answer]
    parameters: Dict[str, Tuple[Tuple[str, ...], Because]]

    def satisfied(self, entry_id, keys):
        """`None` if the answer recorded for `entry_id` is one of `keys`, else
        the `Because` naming the ADR whose answer it is not."""
        recorded = self.answers.get(entry_id)
        if recorded is None:
            return Because(f"{self.module}/{entry_id}", None)
        if recorded.answer is None:
            return Because(recorded.ref, None)
        if recorded.answer in keys:
            return None
        if "accepted" in keys and recorded.prescribed and recorded.answer != "declined":
            return None
        return Because(recorded.ref, recorded.answer)


def record_path(repository):
    """Where the set built on is read from: the monorepo's `platform/` folder."""
    return Path(repository) / PLATFORM_FOLDER / RECORD_NAME


def digest_at(repository):
    """The digest of the set in `platform/`, or `None` if there is none to read."""
    path = record_path(repository)
    if not path.is_file():
        return None
    try:
        return set_digest(read_mapping(path))
    except CannotRun:
        return None


def read(repository, module):
    """The set `module` produced, from `platform/`, or `CannotRun` saying why not.

    It must be there, it must pass the validator, and it must come from
    `module`. A set recording `module: 1` was written from `platform-core`.
    """
    from wizard.adr_set import validate  # the reader the validator itself uses

    path = record_path(repository)
    needed = f"this walk needs the set {module} produced, in {PLATFORM_FOLDER}/"
    if not path.is_file():
        raise CannotRun(f"{path} does not exist; {needed}")
    failures = validate(path)
    if failures:
        raise CannotRun(f"{path} is not a valid ADR set ({len(failures)} "
                        f"{'failure' if len(failures) == 1 else 'failures'}; run validate.py "
                        f"on it to see them); {needed}")
    document = read_mapping(path)
    recorded = module_of(document.get("module"))
    if recorded != module:
        raise CannotRun(f"{path} was written from the module {recorded!r}; {needed}")

    answers, parameters = {}, {}
    for adr in document["adrs"]:
        ref = f"{module}/{adr['id']}"
        chosen = [o["key"] for o in adr.get("options") or [] if o.get("status") == "chosen"]
        answer = chosen[0] if chosen else None
        answers[adr["corpus_entry"]] = Answer(ref, answer, adr.get("origin") == "prescribed")
        for name, values in (adr.get("parameters") or {}).items():
            parameters[name] = (tuple(values), Because(ref, answer))
    return BuiltOn(module, set_digest(document), answers, parameters)
