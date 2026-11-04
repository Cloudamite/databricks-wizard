#!/usr/bin/env python3
"""Install this skill where Claude Code finds it.

Run it from a clone of this repository:

    python3 install.py

It asks one question, the folder to install into, and offers the folder
Claude Code reads your own skills from. It copies the skill there, then builds
the skill's Python environment with uv. Run it again to upgrade: it asks before
replacing an existing folder, and replaces it whole.

A script can give the answers on standard input:

    printf '%s\\ny\\n' ~/.claude/skills/databricks-wizard | python3 install.py

Exit 0 installed, 1 declined or the environment could not be built, 2 could
not run. Standard library only: no environment exists yet.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
INSTALLED, DECLINED, CANNOT_RUN = 0, 1, 2


class CannotRun(Exception):
    pass


def skill_name():
    match = re.search(r"^name:\s*(\S+)\s*$", (HERE / "SKILL.md").read_text(encoding="utf-8"),
                      re.MULTILINE)
    if match is None:
        raise CannotRun(f"{HERE / 'SKILL.md'} names no skill")
    return match.group(1)


def ask(question):
    try:
        return input(question).strip()
    except EOFError:
        print(file=sys.stderr)
        raise CannotRun("no answer was given, so nothing was installed") from None


def copy(target, include):
    """Copy the skill beside `target` whole, then move it into place.

    The old folder is moved aside first and put back if the move fails, so a
    failure at any point leaves the target as it was.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".{target.name}.installing"
    replaced = target.parent / f".{target.name}.replaced"
    shutil.rmtree(staging, ignore_errors=True)
    try:
        staging.mkdir()
        for entry in include:
            source = HERE / entry
            if source.is_dir():
                shutil.copytree(source, staging / entry,
                                ignore=shutil.ignore_patterns(".venv", "__pycache__"))
            else:
                shutil.copy2(source, staging / entry)
    except OSError as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise CannotRun(f"the skill could not be copied, so nothing was changed: {exc}") from None
    if target.exists():
        os.replace(target, replaced)
    try:
        os.replace(staging, target)
    except OSError as exc:
        if replaced.exists():
            os.replace(replaced, target)
        shutil.rmtree(staging, ignore_errors=True)
        raise CannotRun(f"the skill could not be moved into place, so nothing was changed: "
                        f"{exc}") from None
    shutil.rmtree(replaced, ignore_errors=True)


def post_install(target, steps):
    """Run each post-install command against the installed folder; True if all pass."""
    for step in steps:
        command = [arg.replace("${SKILL_DIR}", str(target)) for arg in step["command"]]
        if command[0] == "python":
            command[0] = sys.executable
        if subprocess.run(command).returncode != 0:
            print(f"The skill is copied to {target}, but cannot run yet. Fix what is reported "
                  f"above, then run:\n  {' '.join(command)}", file=sys.stderr)
            return False
    return True


def main():
    name = skill_name()
    install = json.loads((HERE / ".skill-install.json").read_text(encoding="utf-8"))
    default = f"~/.claude/skills/{name}"
    answer = ask(f"Where should {name} be installed? [{default}]: ") or default
    target = Path(os.path.abspath(Path(answer).expanduser()))
    if target.exists():
        replace = ask(f"{target} already exists. Replace it? [y/N]: ")
        if replace.lower() not in ("y", "yes"):
            print(f"Nothing was installed; {target} is as it was.")
            return DECLINED
    copy(target, install["include"])
    if not post_install(target, install.get("post_install", [])):
        return DECLINED
    print(f"Installed {name} in {target}.\n"
          f"In Claude Code, start it with /{name} describe")
    return INSTALLED


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CannotRun as exc:
        print(f"cannot install: {exc}", file=sys.stderr)
        sys.exit(CANNOT_RUN)
