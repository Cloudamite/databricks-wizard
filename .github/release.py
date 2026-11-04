#!/usr/bin/env python3
"""Release this skill as a Claude Code plugin.

    python3 .github/release.py check
    python3 .github/release.py draft
    python3 .github/release.py advance

Run by the release workflows from the repository's root; they pass the facts
of their run through the environment and decide nothing themselves.

`check` reads the version from .claude-plugin/plugin.json and stops if it is
not X.Y.Z, or if a published release already has it. A published release is
immutable: its tag can never move, and its version can never be released again.
A draft of the version is allowed, and a later `draft` replaces it.

`draft` runs `check` again. On any branch but main it stops there and tags
nothing. On main it tags the tested commit (GITHUB_SHA) v<version>, pushes only
the tag, and creates a draft release on it. It never publishes: a maintainer
does that in GitHub, after reading the draft.

`advance` runs when a release is published. It moves the branch `release`,
which the plugin marketplace reads, to the release's tag (RELEASE_TAG). The push
is never forced, so `release` only moves forward, and an older release
published after a newer one is not offered to users.

Exit 0 done, 1 refused or failed. Standard library only; it shells out to git
and the GitHub CLI.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN = "main"
BRANCH = "release"
# A runner has no git identity, and an annotated tag needs one.
AS_BOT = ["git", "-c", "user.name=github-actions[bot]",
          "-c", "user.email=github-actions[bot]@users.noreply.github.com"]


class Refused(Exception):
    """The release stops here; the message says why."""


def run(command):
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise Refused(f"{' '.join(command)} failed:\n{result.stdout}{result.stderr}")
    return result.stdout


def version():
    manifest = ROOT / ".claude-plugin" / "plugin.json"
    found = json.loads(manifest.read_text(encoding="utf-8")).get("version")
    if not isinstance(found, str) or not re.fullmatch(r"\d+\.\d+\.\d+", found):
        raise Refused(f"{manifest.relative_to(ROOT)} gives the version {found!r}; "
                      "a release needs one of the form X.Y.Z, such as 0.1.0")
    return found


def state(tag):
    """None, "draft" or "published". Listed rather than looked up by tag: GitHub
    does not find a draft by its tag name until it is published."""
    listed = json.loads(run(["gh", "release", "list", "--limit", "1000",
                             "--json", "tagName,isDraft"]))
    for release in listed:
        if release["tagName"] == tag:
            return "draft" if release["isDraft"] else "published"
    return None


def check():
    tag = f"v{version()}"
    found = state(tag)
    if found == "published":
        raise Refused(f"{tag} is published, and a published release never changes: its "
                      "version can never be released again. Release a new version: raise "
                      "`version` in .claude-plugin/plugin.json and publish the skill again.")
    print(f"{tag} has a draft release, which this release replaces." if found == "draft"
          else f"{tag} has no release yet.")
    return tag, found


def draft():
    tag, found = check()
    ref = os.environ["GITHUB_REF_NAME"]
    if ref != MAIN:
        print(f"Only {MAIN} is released. This run on {ref} passed its checks, and tagged and "
              "drafted nothing.")
        return
    tested = os.environ["GITHUB_SHA"]
    if found == "draft":
        run(["gh", "release", "delete", tag, "--cleanup-tag", "--yes"])
        subprocess.run(["git", "tag", "-d", tag], cwd=ROOT, capture_output=True)
    run([*AS_BOT, "tag", "-a", tag, tested, "-m", f"Release {tag}"])
    run(["git", "push", "origin", f"refs/tags/{tag}"])
    notes = (f"Commit {tested} passed the plugin's validation and the smoke checks. "
             f"Publishing this release offers {tag} to everyone who installs the plugin.")
    run(["gh", "release", "create", tag, "--draft", "--verify-tag", "--title", tag,
         "--notes", notes])
    print(f"Created {tag} as a draft on {tested}. Read it, then publish it in GitHub.")


def advance():
    tag = os.environ["RELEASE_TAG"]
    commit = run(["git", "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}"]).strip()
    run(["git", "push", "origin", f"{commit}:refs/heads/{BRANCH}"])
    print(f"{BRANCH} is now {tag} ({commit}): the plugin offers it to users.")


COMMANDS = {"check": check, "draft": draft, "advance": advance}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or argv[0] not in COMMANDS:
        print(f"usage: release.py {{{','.join(COMMANDS)}}}", file=sys.stderr)
        return 1
    try:
        COMMANDS[argv[0]]()
    except Refused as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
