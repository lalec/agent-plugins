#!/usr/bin/env python3
"""PreToolUse(Bash) guard — deny commands that would fish secrets into context.

Blocks the clear-cut leak vectors and teaches the correct secretrun usage in the
deny reason. Deliberately conservative: the legitimate, masked pattern
`secretrun NAME -- sh -c 'echo $NAME'` is NOT blocked (the wrapper redacts it).
This guard is a backstop, not the primary control — network exfiltration of a
resolved value cannot be detected here and is covered by the threat model in
README.md, not by this hook.

Contract: read the tool-call JSON on stdin. Exit 2 with a stderr reason to DENY
(Claude Code surfaces stderr to the model). Exit 0 to allow.
"""
import json
import re
import shlex
import sys

# Transcript / keychain-dump / env-dump leak patterns (case-insensitive).
_TRANSCRIPT = re.compile(r"\.claude/projects/", re.I)
_READERS = re.compile(
    r"\b(cat|less|more|head|tail|bat|nl|strings|rg|grep|egrep|fgrep|open|"
    r"pbcopy|xxd|od|hexdump)\b", re.I)


def _deny(reason):
    sys.stderr.write("secretrun guard: " + reason + "\n")
    raise SystemExit(2)


def _tokens(command):
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _check(command):
    low = command.lower()
    toks = _tokens(command)
    stripped = command.strip()

    # 1) Keychain bulk dump — reveals every stored credential.
    if "dump-keychain" in low:
        _deny("`dump-keychain` exposes every stored credential. Use "
              "`secretrun ls` to see secretrun names, or `secretrun NAME -- cmd` "
              "to use one.")

    # 2) Direct `security find-…-password … -w` prints a value into the "
    #    transcript. The secretrun wrapper does this internally; the model must not.
    if re.search(r"\bsecurity\b", low) and \
       re.search(r"find-(generic|internet)-password", low) and \
       re.search(r"(^|\s)-w(\s|$)", command):
        _deny("reading a keychain password with `security -w` would write the "
              "value into the transcript. Use `secretrun NAME -- cmd` instead; "
              "the value stays out of context.")

    # 3) Reading the Claude transcript (plaintext history) with a file reader.
    if _TRANSCRIPT.search(command) and _READERS.search(command):
        _deny("reading ~/.claude/projects/** can pull previously-seen secrets "
              "back into context. This path is off-limits — use "
              "`secretrun sessions` / `secretrun session <id>` for safe, redacted "
              "session metadata, or `secretrun usage` for token counts and cost.")

    # 4) `secretrun add` with a value on the command line or piped in.
    if re.search(r"\bsecretrun\s+add\b", low):
        if "|" in command and re.search(r"\|\s*secretrun\s+add", low):
            _deny("never pipe a value into `secretrun add` — it would land in "
                  "argv/context. The user must type `! secretrun add NAME` so the "
                  "value is entered at a hidden prompt.")
        # positional args after `add` beyond the NAME (ignoring -b BACKEND)
        try:
            j = toks.index("add")
        except ValueError:
            j = -1
        if j >= 0:
            pos, k = [], j + 1
            while k < len(toks):
                if toks[k] in ("-b", "--backend"):
                    k += 2
                    continue
                pos.append(toks[k])
                k += 1
            if len(pos) > 1:
                _deny("a secret value must never appear on the command line. The "
                      "user types `! secretrun add NAME` and enters the value at a "
                      "hidden prompt.")

    # 5) Whole-environment dump into context.
    if stripped in ("env", "printenv") or re.match(r"^(printenv)\s*$", stripped):
        _deny("dumping the whole environment can spill injected/inherited "
              "secrets into context. Reference specific names instead.")


def main():
    try:
        data = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if data.get("tool_name") != "Bash":
        return 0
    command = (data.get("tool_input") or {}).get("command") or ""
    if command:
        _check(command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
