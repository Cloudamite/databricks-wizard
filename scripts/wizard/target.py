"""Where a set lands in a team's repository, and how presence is established.

Two modules need this and neither can own it. The gate that refuses a run
against a repository that already holds a set lives in `run.py`,
before anything is asked; the write that produces one lives in
`write.py`, after everything has been answered. Naming the path in the writer
would make the gate import it — dragging the renderer, PyYAML and the validity
table into a check that opens nothing — and would invert the engine's
layering, where the write sits downstream of a
finished run. Naming it in both would let the two disagree, and the first
symptom of that is a gate guarding a path nothing writes to.

So it is named once, here, in a leaf that imports nothing from the package.

**Presence is the artefact existing at its path, never the artefact parsing.**
A set which is present and unreadable must
stop the run rather than read as a clean repository, and the dangerous
implementation is the one that reads the file, fails, and concludes there is
nothing there. A check that never opens the file cannot make that mistake.
"""

import os
from pathlib import Path

# Where a set lands in the team's repository, and what the record is called.
#
# `docs/decisions` is where a set lands when no module was named: the estate
# skill's walk, until it reads its set from the ADR monorepo. A walk for a
# module lands in the folder `modules.folder_for` gives it, and every function
# here takes that folder.
SET_DIRECTORY = Path("docs/decisions")
RECORD_NAME = "adr-set.yaml"

# Where the write assembles a set before publishing it, beside the target so
# that publishing is one rename on one filesystem.
#
# A fixed, dotted, self-describing name rather than a random one: a process
# killed between assembling and publishing leaves this directory behind either
# way, and one directory a human can recognise — and that the next write
# removes before staging — beats an unbounded pile of `tmp8xk2p9` under `docs/`.
STAGING_NAME = ".adr-set-staging"


def set_directory(repository, folder=SET_DIRECTORY):
    """The directory a set lands in, under `repository`."""
    return Path(repository) / folder


def record_path(repository, folder=SET_DIRECTORY):
    """The machine-readable record, under `repository`."""
    return set_directory(repository, folder) / RECORD_NAME


def staging_directory(repository, folder=SET_DIRECTORY):
    """Where the write assembles a set — beside the target, never inside it.

    Inside would make the staging directory part of what is published, and the
    publish is a rename of the whole thing.
    """
    return set_directory(repository, folder).parent / STAGING_NAME


def existing_set(repository, folder=SET_DIRECTORY):
    """The record if the repository already holds one, else `None`.

    `os.path.lexists` rather than `Path.exists()`, and the difference is a
    requirement rather than a preference. `exists()` follows symlinks and returns
    `False` for a broken one — so a broken symlink at the record's path, which
    is a set that is present and unreadable if anything is, would report a
    clean repository and the run would proceed to write over it. That is the
    failure this guards against, in its most literal form.
    """
    path = record_path(repository, folder)
    return path if os.path.lexists(path) else None


def occupied(repository, folder=SET_DIRECTORY):
    """The set directory if it exists and holds anything, else `None`.

    A repository with `ADR-003-something.md` and no record has no *set* — the
    record is what a set is — but it has a directory this product cannot
    publish into. The write is atomic because it assembles the whole set beside
    the target and renaming it into place in one syscall, and `rename(2)` onto
    a directory that holds files fails. Nothing portable lands nine files into
    an occupied directory atomically.

    So the run refuses, at the same gate and for the same reason as an existing
    set: the alternative is to publish file-by-file and give up the guarantee
    on a path nobody is watching.

    An empty directory is not occupied. `rename(2)` replaces an existing empty
    directory, so there is nothing here to refuse.
    """
    directory = set_directory(repository, folder)
    if not directory.is_dir():
        return None
    return directory if any(directory.iterdir()) else None
