"""Hidden value entry for `secretrun add` — the user types; the agent never sees it.

Order: a terminal's hidden prompt, then (macOS, no terminal — Claude Code's shell
has none) a native hidden-input dialog, else refuse. Never reads a value from a
pipe or argv.
"""
import os
import subprocess
import sys

from stores import SecretrunError


def tty_available():
    # getpass prompts on /dev/tty, NOT stdin — a piped value is ignored, and the
    # prompt works even when stdin is redirected. Refuse only when no terminal is
    # reachable, so we never fall back to reading a value from a pipe.
    try:
        fd = os.open("/dev/tty", os.O_RDWR)
    except OSError:
        return False
    os.close(fd)
    return True


def prompt_gui(name):
    # The NAME travels as an AppleScript *argument* — never spliced into the
    # script source — so a hostile name cannot inject AppleScript. The value
    # returns on osascript's stdout pipe, straight into this process. `giving up
    # after 110` keeps a forgotten dialog inside the Bash tool's 120 s timeout.
    p = subprocess.run(
        ["osascript",
         "-e", "on run argv",
         "-e", 'set d to display dialog ("Enter value for " & item 1 of argv'
               ' & return & "(stored by secretrun; Claude never sees it)")'
               ' with title "secretrun" default answer ""'
               " with hidden answer giving up after 110",
         "-e", "return text returned of d",
         "-e", "end run",
         name],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if p.returncode != 0:
        raise SecretrunError(f"dialog cancelled; nothing stored: {name}")
    out = p.stdout[:-1] if p.stdout.endswith(b"\n") else p.stdout
    if not out:                        # empty entry, or dialog gave up (timeout)
        raise SecretrunError("empty value; nothing stored")
    return bytearray(out)


def read_hidden(name):
    if tty_available():
        import getpass
        val = getpass.getpass(f"Value for {name} (hidden, not echoed): ")
        if not val:
            raise SecretrunError("empty value; nothing stored")
        return bytearray(val.encode("utf-8"))
    if sys.platform == "darwin":
        return prompt_gui(name)
    raise SecretrunError(
        "no controlling terminal for a hidden prompt. Open a normal terminal "
        "window and run:  secretrun add " + name)
