#!/usr/bin/env python3
"""PostToolUse redactor — scrub secret-SHAPED strings from tool output.

Defence-in-depth against tokens that arrive via channels the secretrun wrapper
never saw (an API error body, a config file the user asked to read, a webpage).
It matches well-known credential SHAPES; it never reads the real stored values.

Version-adaptive:
  * Claude Code 2.1.199+  -> emits `updatedToolOutput`, hard-replacing the output.
  * older                 -> the field is ignored, so we also emit
                             `additionalContext` naming the count (no value) so
                             the redaction is at least visible.
Either way, nothing is blocked (exit 0).
"""
import json
import re
import sys

REDACTED = "[REDACTED]"

# High-confidence credential shapes. Ordered longest/most-specific first.
PATTERNS = [
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----", re.S),
    re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),  # JWT
    re.compile(r"github_pat_[A-Za-z0-9_]{22,}"),
    re.compile(r"gh[posru]_[A-Za-z0-9]{30,}"),                                  # gh* tokens
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{16,}"),                             # OpenAI
    re.compile(r"(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}"),                 # Stripe
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),                                # Slack
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),                                       # Google API
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),                              # AWS access key id
    re.compile(r"Aic[0-9A-Za-z_-]{20,}"),                                      # generic Google
]
# Keyword-adjacent high-entropy value (api_key = "...", "token": "...", JSON).
# The separator tolerates a closing key-quote, ':'/'=', and an opening value-quote.
KEYWORD = re.compile(
    r"(?i)(api[_-]?key|secret|token|passwd|password|bearer|authorization)"
    r"(['\"]?\s*[:=]\s*['\"]?|\s+)"
    r"([A-Za-z0-9/_+=.-]{16,})")


def _scrub(text):
    n = 0
    for pat in PATTERNS:
        text, c = pat.subn(REDACTED, text)
        n += c

    def _kw(m):
        nonlocal n
        n += 1
        return m.group(1) + m.group(2) + REDACTED

    text = KEYWORD.sub(_kw, text)
    return text, n


def _as_text(resp):
    if isinstance(resp, str):
        return resp
    if isinstance(resp, dict):
        parts = [str(resp[k]) for k in ("stdout", "stderr", "output", "content",
                                        "text") if resp.get(k)]
        if parts:
            return "\n".join(parts)
        return json.dumps(resp)
    return "" if resp is None else str(resp)


def main():
    try:
        data = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    resp = data.get("tool_response", data.get("tool_output"))
    text = _as_text(resp)
    if not text:
        return 0
    scrubbed, n = _scrub(text)
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
