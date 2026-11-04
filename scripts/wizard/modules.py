"""The shipped modules: which there are, what each is, and where a set lands.

The corpus root holds one directory per module, each a corpus of its own with a
manifest that names the module, its type and what it decides. A walk is for one
module, named before the first card, and nothing is walked by default.

**Every manifest is checked before anything is listed or walked.** A list
missing one module because its manifest is broken would let a team pick
another, believing it was the only choice. So a defect in any manifest stops
the list and every walk alike, and the report names each manifest at fault.

**The type chooses what is offered, and nothing else.** Nothing that reads a set
needs it, so a set records the module and never the type.
"""

import re
from pathlib import Path

import yaml

from wizard.corpus import MANIFEST_NAME
from wizard.validity import CannotRun

PLATFORM = "platform"
PRODUCT = "product"
TYPES = (PLATFORM, PRODUCT)

# What every manifest under a corpus root carries. `builds_on` is optional.
REQUIRED = ("schema_version", "version", "module", "type", "summary")

# The module a set recording `module: 1` was written from. The shipped corpus
# was one module before modules, and its manifest said so with a number.
FIRST = 1
FIRST_IS = "platform-core"

# Where each type's set lands under the ADR monorepo's root.
PLATFORM_FOLDER = Path("platform")
PRODUCTS_FOLDER = Path("products")

# One or more groups of lowercase letters and digits, joined by single hyphens.
# The name is a folder, so it must be the same folder on every machine.
PRODUCT_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
PRODUCT_NAME_RULE = ("a product name is one or more groups of lowercase letters and digits, "
                     "joined by single hyphens — for example orders or customer-360")


def module_of(recorded):
    """The module a set's `module` field names, reading `1` as `platform-core`."""
    return FIRST_IS if recorded == FIRST else recorded


def is_product_name(name):
    return isinstance(name, str) and PRODUCT_NAME.match(name) is not None


def folder_for(module_type, product=None):
    """The folder a set of this type lands in, relative to the monorepo root."""
    if module_type == PLATFORM:
        return PLATFORM_FOLDER
    return PRODUCTS_FOLDER / product


def catalog(root):
    """`{name: manifest}` for every module under `root`, ordered by name.

    Raises `CannotRun` naming every manifest at fault, so a team never picks
    from a list a broken manifest has shortened.
    """
    root = Path(root)
    if not root.is_dir():
        raise CannotRun(f"{root} is not a corpus root: it is not a directory")

    problems, manifests = [], {}
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        path = directory / MANIFEST_NAME
        where = f"{directory.name}/{MANIFEST_NAME}"
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            problems.append(f"{where} is missing")
            continue
        except (OSError, yaml.YAMLError) as exc:
            problems.append(f"{where} cannot be read: {exc}")
            continue
        if not isinstance(document, dict):
            problems.append(f"{where} is not a mapping")
            continue

        missing = [f for f in REQUIRED if not document.get(f)]
        if missing:
            problems.append(f"{where} declares no {', '.join(missing)}")
            continue
        if document["type"] not in TYPES:
            problems.append(f"{where} gives type {document['type']!r}; "
                            f"a type is {' or '.join(TYPES)}")
        if document["module"] != directory.name:
            problems.append(f"{where} names the module {document['module']!r}, "
                            f"but its directory is {directory.name!r}")
        # A manifest names its own directory, and directory names are unique, so
        # no two manifests that pass here can name the same module.
        manifests[document["module"]] = document

    if not manifests and not problems:
        raise CannotRun(f"{root} is not a corpus root: it holds no module")

    for name, document in manifests.items():
        built_on = document.get("builds_on")
        if built_on is None:
            continue
        if built_on == name:
            problems.append(f"{name}/{MANIFEST_NAME} builds on itself")
        elif built_on not in manifests:
            problems.append(f"{name}/{MANIFEST_NAME} builds on {built_on!r}, "
                            "which is not a shipped module")

    if problems:
        raise CannotRun("the shipped modules cannot be listed:\n  " + "\n  ".join(problems))
    return dict(sorted(manifests.items()))


def listing(manifests, module_type=None):
    """What `session.py modules` prints: each module's name, type and summary,
    and what it builds on where it builds on something."""
    return [
        {"module": name, "type": m["type"], "summary": m["summary"],
         **({"builds_on": m["builds_on"]} if m.get("builds_on") else {})}
        for name, m in manifests.items()
        if module_type is None or m["type"] == module_type
    ]


def choose(manifests, name, module_type=None):
    """The manifest of the module named, or `CannotRun` naming those that could
    have been walked."""
    offered = [n for n, m in manifests.items() if module_type is None or m["type"] == module_type]
    if name is None or name not in offered:
        narrowed = f" of type {module_type}" if module_type else ""
        asked = "no module was named" if name is None else f"there is no module {name!r}{narrowed}"
        raise CannotRun(f"{asked}; the modules{narrowed} this corpus ships are "
                        f"{', '.join(offered) or 'none'}")
    return manifests[name]
