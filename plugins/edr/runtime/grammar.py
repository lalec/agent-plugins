"""Reply grammar, numbers only — reply text never reaches a shell or the model.

`<finding> <choice>` pairs, choices `0` ok (accept as benign), `1` why
(narrative), `2` fix (run the declared remediation), `3` skip. A bare choice
applies to the only finding of a one-finding batch. A bare `0` on a larger
batch accepts every finding the analyst called benign — never one it flagged.
Anything else → hint, nothing runs.
"""
from __future__ import annotations

import re

import alerts

HINT = f"? reply <finding> <choice> · {alerts.CHOICE_LINE}"
_INT = re.compile(r"^\d+$")


def parse(text: str, valid: set[int], benign: set[int] | frozenset[int] = frozenset()
          ) -> list[tuple[str, int]] | None:
    """[(verb, finding)] for a well-formed numeric reply, else None. Verbs: ok, why, fix, skip."""
    toks = text.strip().split()
    if not toks or not all(_INT.match(t) for t in toks):
        return None
    nums = [int(t) for t in toks]
    if len(nums) == 1 and len(valid) == 1 and nums[0] in alerts.CHOICES:
        return [(alerts.CHOICES[nums[0]], next(iter(valid)))]
    if nums == [0]:
        return [("ok", n) for n in sorted(benign & valid)] or None
    if len(nums) % 2:
        return None
    out: list[tuple[str, int]] = []
    for finding, choice in zip(nums[::2], nums[1::2]):
        if finding not in valid or choice not in alerts.CHOICES:
            return None
        out.append((alerts.CHOICES[choice], finding))
    return list(dict.fromkeys(out))
