#!/usr/bin/env python3
"""PreToolUse guard — deny Bash commands and Read/Grep calls that would print
secret values: secret files, keychain reads, and password-manager reads
(`op read`, `dcli password`, `lpass show`, ...).

Blocks the clear-cut leak vectors and teaches the srun form in the deny
reason. Deliberately narrow: `srun NAME -- sh -c 'echo $NAME'` is allowed
(the wrapper masks it), and nothing here reads or restricts session transcripts.
A backstop, not the primary control — deliberate exfiltration by a child that
holds a value is outside what a command-line check can see.

Secret files: `.env` files (never `.env.example` and other templates), and
anything under ~/.aws, ~/.ssh or ~/.config/gcloud — for Bash readers, the Read
tool, and Grep in content mode. Glob and Grep's default file-list and count
modes print no content and stay allowed.

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
# Password-manager verbs that print a stored value (`op item list`, `lpass
# status` and the like print none and stay allowed).
_MANAGER_READS = {
    "op": [("read",), ("inject",), ("item", "get"), ("document", "get")],
    "dcli": [("password",), ("p",), ("read",), ("note",), ("n",), ("secret",)],
    "lpass": [("show",), ("export",)],
}
_SECRET_DIRS = [os.path.expanduser(d) for d in ("~/.aws", "~/.ssh", "~/.config/gcloud")]


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


def _is_secret_path(tok):
    if _is_env_file(tok):
        return True
    path = os.path.abspath(os.path.expanduser(tok.replace("$HOME", "~", 1)))
    return any(path == d or path.startswith(d + os.sep) for d in _SECRET_DIRS)


def _commands(toks):
    """Every command segment, including those inside `srun ... -- cmd` and
    `sh -c '...'`: other values printed there are not masked."""
    for seg in _segments(toks):
        prog = os.path.basename(seg[0])
        if prog == "srun" and "--" in seg:
            yield from _commands(seg[seg.index("--") + 1:])
        elif prog in ("sh", "bash", "zsh") and "-c" in seg[:-1]:
            yield from _commands(_tokens(seg[seg.index("-c") + 1]))
        else:
            yield prog, seg


def _secret_read(toks):
    """The secret file a reader prints, or None. `grep -c/-q/-l` only counts."""
    for prog, seg in _commands(toks):
        if prog not in _READERS:
            continue
        if prog in ("grep", "egrep", "fgrep", "rg") and \
                any(_SILENT_GREP.match(a) for a in seg[1:]):
            continue
        for a in seg[1:]:
            if _is_secret_path(a):
                return a
    return None


def _manager_read(toks):
    """A password-manager command that prints a value, or None. srun runs
    these itself; the agent never needs them."""
    for prog, seg in _commands(toks):
        verbs = tuple(a for a in seg[1:] if not a.startswith("-"))
        for v in _MANAGER_READS.get(prog, ()):
            if verbs[:len(v)] == v:
                return " ".join((prog,) + v)
    return None


def _deny_read(path):
    _deny(f"reading {path} prints secret values into the transcript. "
          "Use the value by NAME: `srun NAME -- cmd` (a `cmd` entry in "
          ".srun.json can read it from that file); `srun check "
          "NAME` says whether it is set. `grep -c '^NAME=' FILE` counts "
          "without printing.")


def _check_file_tool(tool, inp):
    """Read prints a file; Grep prints matching lines only in content mode."""
    if tool == "Read":
        path = inp.get("file_path") or ""
    elif tool == "Grep" and inp.get("output_mode") == "content":
        path = inp.get("path") or ""
        glob = inp.get("glob") or ""
        base = glob.rsplit("/", 1)[-1]
        if base.startswith(".env") and not _TEMPLATE.search(base):
            _deny_read(glob)
    else:
        return
    if path and _is_secret_path(path):
        _deny_read(path)


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

    secret_file = _secret_read(toks)
    if secret_file:
        _deny_read(secret_file)

    manager = _manager_read(toks)
    if manager:
        _deny(f"`{manager}` prints a stored value into the transcript. Use the "
              "value by NAME: `srun NAME -- cmd` reads it from the project's "
              "store; `srun check NAME` says whether it is set.")

    if re.search(r"\bsrun\s+add\b", low):
        if re.search(r"\|\s*\S*srun\s+add", low):
            _deny("never pipe a value into `srun add`. Run `srun add "
                  "NAME` and the user types the value into a hidden prompt.")
        j = next((i for i, t in enumerate(toks) if t == "add"), -1)
        pos, k = [], j + 1
        while 0 <= j < len(toks) and k < len(toks) and toks[k] not in _SHELL_OPS:
            if toks[k] in ("-s", "--store"):
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
    tool, inp = data.get("tool_name"), data.get("tool_input") or {}
    if tool == "Bash":
        if inp.get("command"):
            _check(inp["command"])
    else:
        _check_file_tool(tool, inp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
