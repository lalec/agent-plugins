#!/usr/bin/env python3
"""PreToolUse(Bash) guard — deny commands that would print secret values.

Blocks the clear-cut leak vectors and teaches the srun form in the deny
reason. Deliberately narrow: `srun NAME -- sh -c 'echo $NAME'` is allowed
(the wrapper masks it), and nothing here reads or restricts session transcripts.
A backstop, not the primary control — deliberate exfiltration by a child that
holds a value is outside what a command-line check can see.

Contract: tool-call JSON on stdin. Exit 2 with a stderr reason to DENY (Claude
Code shows stderr to the model). Exit 0 to allow.
"""
import json
import os
import re
import shlex
import sys

# A file reader whose output would land in the transcript.
_READERS = {"cat", "less", "more", "head", "tail", "bat", "nl", "strings", "grep",
            "egrep", "fgrep", "rg", "awk", "sed", "cut", "sort", "uniq", "xxd",
            "od", "hexdump", "pbcopy", "open", "jq", "diff"}
# grep flags that print no line content — a presence check, not a read.
_SILENT_GREP = re.compile(r"^-[a-zA-Z]*[cqlL][a-zA-Z]*$")
_ENV_FILE = re.compile(r"^\.env(\.[\w.-]+)?$")
_TEMPLATE = re.compile(r"\.(example|sample|template|dist)$")
_SHELL_OPS = {"|", "||", "&&", ";", "&"}


def _deny(reason):
    sys.stderr.write("srun guard: " + reason + "\n")
    raise SystemExit(2)


def _tokens(command):
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        return list(lex)
    except ValueError:
        return command.split()


def _segments(toks):
    seg = []
    for t in toks:
        if t in _SHELL_OPS:
            if seg:
                yield seg
            seg = []
        else:
            seg.append(t)
    if seg:
        yield seg


def _is_env_file(tok):
    base = os.path.basename(tok)
    return bool(_ENV_FILE.match(base)) and not _TEMPLATE.search(base)


def _env_file_read(toks):
    """The env file a reader prints, or None. `grep -c/-q/-l` only counts. Looks
    inside `srun ... -- cmd` and `sh -c '...'`: other values in the file
    are not masked there."""
    for seg in _segments(toks):
        prog = os.path.basename(seg[0])
        if prog == "srun" and "--" in seg:
            hit = _env_file_read(seg[seg.index("--") + 1:])
            if hit:
                return hit
            continue
        if prog in ("sh", "bash", "zsh") and "-c" in seg[:-1]:
            hit = _env_file_read(_tokens(seg[seg.index("-c") + 1]))
            if hit:
                return hit
            continue
        if prog not in _READERS:
            continue
        if prog in ("grep", "egrep", "fgrep", "rg") and \
                any(_SILENT_GREP.match(a) for a in seg[1:]):
            continue
        for a in seg[1:]:
            if _is_env_file(a):
                return a
    return None


def _check(command):
    low = command.lower()
    toks = _tokens(command)

    if "dump-keychain" in low:
        _deny("`dump-keychain` exposes every stored credential. Use "
              "`srun ls` for names, or `srun NAME -- cmd` to use one.")

    if re.search(r"\bsecurity\b", low) and \
       re.search(r"find-(generic|internet)-password", low) and \
       re.search(r"(^|\s)-w(\s|$)", command):
        _deny("`security ... -w` prints a keychain password into the transcript. "
              "Use `srun NAME -- cmd`; the value stays out of context.")

    env_file = _env_file_read(toks)
    if env_file:
        _deny(f"reading {env_file} prints secret values into the transcript. "
              "Use the value by NAME: `srun NAME -- cmd` (a `cmd` entry in "
              ".srun.json can read it from that file); `srun check "
              "NAME` says whether it is set. `grep -c '^NAME=' FILE` counts "
              "without printing.")

    if re.search(r"\bsrun\s+add\b", low):
        if re.search(r"\|\s*\S*srun\s+add", low):
            _deny("never pipe a value into `srun add`. Run `srun add "
                  "NAME` and the user types the value into a hidden prompt.")
        j = next((i for i, t in enumerate(toks) if t == "add"), -1)
        pos, k = [], j + 1
        while 0 <= j < len(toks) and k < len(toks) and toks[k] not in _SHELL_OPS:
            if toks[k] in ("-b", "--backend"):
                k += 2
                continue
            pos.append(toks[k])
            k += 1
        if len(pos) > 1:
            _deny("a secret value must never appear on the command line. Run "
                  "`srun add NAME`; the user types the value into a hidden "
                  "prompt.")

    if command.strip() in ("env", "printenv", "set", "export", "export -p"):
        _deny("dumping the whole environment can spill secrets into context. "
              "Reference specific names instead.")


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
