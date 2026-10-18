#!/usr/bin/env python3
"""PostToolUse redactor — scrub secret-SHAPED strings from tool output.

Defence-in-depth against tokens that arrive via channels the secretrun wrapper
never saw (an API error body, a config file the user asked to read, a webpage).
It matches well-known credential SHAPES; it never reads the real stored values.

Emits `updatedToolOutput` in the same shape as the tool's own response, which
replaces the output of any tool before the model sees it, plus `additionalContext` naming the count (never a value).
Nothing is blocked (exit 0).
"""
import json
import re
import sys

REDACTED = "[REDACTED]"

# High-confidence credential shapes. Ordered longest/most-specific first. A
# prefix only counts at the start of a token (_B): `sk-` inside `tosk-web-...`
# is an identifier, not a key.
_B = r"(?<![A-Za-z0-9_-])"
PATTERNS = [
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----", re.S),
    re.compile(_B + r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),  # JWT
    re.compile(_B + r"github_pat_[A-Za-z0-9_]{22,}"),
    re.compile(_B + r"gh[posru]_[A-Za-z0-9]{30,}"),                             # gh* tokens
    re.compile(_B + r"sk-(?:proj-)?[A-Za-z0-9_-]{16,}"),                        # OpenAI
    re.compile(_B + r"(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}"),            # Stripe
    re.compile(_B + r"xox[baprs]-[A-Za-z0-9-]{10,}"),                           # Slack
    re.compile(_B + r"AIza[0-9A-Za-z_-]{35}"),                                  # Google API
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),                              # AWS access key id
    re.compile(_B + r"Aic[0-9A-Za-z_-]{20,}"),                                  # generic Google
]
# A high-entropy value right after a credential keyword: `api_key = "..."`,
# `"token": "..."` (the separator tolerates a closing key-quote, ':'/'=' and an
# opening value-quote), or `Bearer <value>` on the same line. Prose like
# "a Bearer token" followed by a long word on the next line is not a credential.
_VALUE = r"([A-Za-z0-9/_+=.-]{16,})"
KEYWORDS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|passwd|password|bearer|authorization)"
               r"(['\"]?\s*[:=]\s*['\"]?)" + _VALUE),
    re.compile(r"(?i)\b(bearer)([ \t]+)" + _VALUE),
]


def _scrub(text):
    n = 0
    for pat in PATTERNS:
        text, c = pat.subn(REDACTED, text)
        n += c

    def _kw(m):
        nonlocal n
        n += 1
        return m.group(1) + m.group(2) + REDACTED

    for pat in KEYWORDS:
        text = pat.sub(_kw, text)
    return text, n


def _scrub_tree(node):
    """Scrub every string inside a tool response, keeping its shape. Claude Code
    discards a rewrite whose shape differs from the original (a Bash response is
    an object with stdout/stderr, a Read response nests the file content), so the
    output must come back as the same kind of value it went in as."""
    if isinstance(node, str):
        return _scrub(node)
    if isinstance(node, dict):
        out, n = {}, 0
        for k, v in node.items():
            out[k], c = _scrub_tree(v)
            n += c
        return out, n
    if isinstance(node, list):
        out, n = [], 0
        for v in node:
            sv, c = _scrub_tree(v)
            out.append(sv)
            n += c
        return out, n
    return node, 0


def main():
    try:
        data = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    resp = data.get("tool_response", data.get("tool_output"))
    scrubbed, n = _scrub_tree(resp)
    if n == 0:
        return 0
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "updatedToolOutput": scrubbed,
            "additionalContext":
                f"secretrun: redacted {n} secret-shaped string(s) from this "
                "tool output.",
        }
    }
    sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
