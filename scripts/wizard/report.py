"""The two renderings of a validation result.

Neither omits a finding the other reports: both are derived from the same list
of `Failure`s, in the same order.
"""

import json


def render_human(mode, failures):
    if not failures:
        return f"{mode} is valid"

    lines = []
    for failure in failures:
        named = " → ".join(failure.entries) if failure.entries else "(no id)"
        location = failure.file or mode
        lines.append(f"{location} — {named}")
        lines.append(f"    {failure.rule}")
        lines.append("")

    # Criterion 3 ends the report with a count, so a maintainer reading a long
    # list knows they reached the end of it.
    noun = "failure" if len(failures) == 1 else "failures"
    lines.append(f"{len(failures)} {noun}")
    return "\n".join(lines)


_ABSENT = object()


def render_json(mode, failures, currency=_ABSENT):
    """`currency` is the newer-corpus notice for a valid ADR set, `None` when
    the skill ships no such module, and absent from the output otherwise."""
    return json.dumps(
        {
            "mode": mode,
            "valid": not failures,
            "count": len(failures),
            "failures": [f.as_dict() for f in failures],
            **({} if currency is _ABSENT else {"currency": currency}),
        },
        indent=2,
        ensure_ascii=False,
    )
