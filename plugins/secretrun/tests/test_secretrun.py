"""Tests for the secretrun plugin.

Covers the security-load-bearing invariants: the output masker (encodings,
chunk-split, multiple secrets), resolver/manifest selection, the interactive-only
`add` TTY refusal, traceback scrubbing, the guard's deny rules, and the redactor's
shape matching. Loads the extension-less `bin/` scripts by path.
"""
import io
import json
import os
import types
from importlib.machinery import SourceFileLoader

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _load(relpath, name):
    return SourceFileLoader(name, os.path.join(ROOT, relpath)).load_module()


sr = _load("bin/secretrun", "secretrun_mod")
admin = _load("bin/secretrun-admin", "secretrun_admin_mod")
guard = _load("hooks/secret_guard.py", "secret_guard_mod")
redact = _load("hooks/redact_output.py", "redact_output_mod")


# ----------------------------------------------------------------- masker ---- #
def _mask(secrets, data):
    m = sr.Masker(secrets)
    src, dst = io.BytesIO(data), io.BytesIO()
    m.stream(src, dst)
    return dst.getvalue()


class ByteDripReader:
    """Yields the payload `n` bytes at a time to force chunk boundaries."""
    def __init__(self, data, n):
        self.data, self.n, self.i = data, n, 0

    def read(self, _):
        chunk = self.data[self.i:self.i + self.n]
        self.i += self.n
        return chunk


def test_mask_raw_value():
    out = _mask({"TOK": bytearray(b"supersecret123")}, b"x=supersecret123\n")
    assert b"supersecret123" not in out
    assert b"[REDACTED:TOK]" in out


def test_mask_base64_form():
    import base64
    val = b"supersecret123"
    enc = base64.b64encode(val)
    out = _mask({"TOK": bytearray(val)}, b"blob: " + enc + b"\n")
    assert enc not in out
    assert b"[REDACTED:TOK]" in out


def test_mask_split_across_chunks():
    val = b"supersecret123"
    m = sr.Masker({"TOK": bytearray(val)})
    dst = io.BytesIO()
    m.stream(ByteDripReader(b"pre-" + val + b"-post", 3), dst)
    out = dst.getvalue()
    assert val not in out
    assert b"[REDACTED:TOK]" in out
    assert out.startswith(b"pre-") and out.endswith(b"-post")


def test_mask_multiple_secrets():
    out = _mask({"A": bytearray(b"aaaa1111"), "B": bytearray(b"bbbb2222")},
                b"aaaa1111 and bbbb2222\n")
    assert b"aaaa1111" not in out and b"bbbb2222" not in out
    assert b"[REDACTED:A]" in out and b"[REDACTED:B]" in out


def test_mask_skips_ultra_short_value():
    # 3-byte value < MIN_MASK_LEN must NOT be masked (would nuke normal output)
    out = _mask({"X": bytearray(b"ab")}, b"cabbage\n")
    assert out == b"cabbage\n"


# ------------------------------------------------------- resolver / plan ---- #
def test_plan_manifest_wins_over_cli_backend():
    manifest = {"DB": {"backend": "aws", "id": "prod/db"}}
    assert sr._plan("DB", "keychain", manifest) == ("aws", "prod/db")


def test_plan_default_and_cli_backend():
    assert sr._plan("K", None, {}) == ("keychain", "K")
    assert sr._plan("K", "gcp", {}) == ("gcp", "K")


def test_plan_unknown_backend_raises():
    with pytest.raises(sr.SecretrunError):
        sr._plan("K", "vault", {})


def test_load_manifest(tmp_path, monkeypatch):
    (tmp_path / ".secretrun.json").write_text(
        json.dumps({"secrets": {"TOK": {"backend": "keychain"}}}))
    monkeypatch.chdir(tmp_path)
    assert sr._load_manifest() == {"TOK": {"backend": "keychain"}}


def test_load_manifest_walks_up(tmp_path, monkeypatch):
    (tmp_path / ".secretrun.json").write_text(json.dumps({"secrets": {"A": {}}}))
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    assert sr._load_manifest() == {"A": {}}


# ------------------------------------------------------------- run/spawn ---- #
def test_spawn_masks_env_value(capfdbinary):
    rc = sr._spawn(["sh", "-c", 'printf "%s" "$SECRET_X"'],
                   {"SECRET_X": bytearray(b"supersecret123")}, None)
    out, _ = capfdbinary.readouterr()
    assert rc == 0
    assert b"supersecret123" not in out
    assert b"[REDACTED:SECRET_X]" in out


def test_spawn_exit_code_passthrough(capfdbinary):
    assert sr._spawn(["sh", "-c", "exit 3"], {"K": bytearray(b"vvvv")}, None) == 3


def test_spawn_signal_passthrough(capfdbinary):
    # 128 + SIGKILL(9)
    rc = sr._spawn(["sh", "-c", "kill -9 $$"], {"K": bytearray(b"vvvv")}, None)
    assert rc == 137


def test_spawn_stdin_mode_keeps_value_out_of_env(capfdbinary):
    # value goes to stdin; env var must be UNSET, and the echoed value masked
    rc = sr._spawn(["sh", "-c", 'cat; echo "env=[${SECRET_X:-unset}]"'],
                   {"SECRET_X": bytearray(b"supersecret123")}, "SECRET_X")
    out, _ = capfdbinary.readouterr()
    assert rc == 0
    assert b"supersecret123" not in out
    assert b"env=[unset]" in out
    assert b"[REDACTED:SECRET_X]" in out


def test_run_requires_separator():
    with pytest.raises(sr.SecretrunError):
        sr.cmd_run(["TOK", "echo", "hi"])   # no --


def test_run_stdin_name_must_be_a_name():
    with pytest.raises(sr.SecretrunError):
        sr.cmd_run(["TOK", "--stdin", "OTHER", "--", "echo"])


# ------------------------------------------------------------------ add ----- #
def test_add_refuses_non_tty(monkeypatch):
    monkeypatch.setattr(sr.sys, "stdin", types.SimpleNamespace(isatty=lambda: False))
    with pytest.raises(sr.SecretrunError) as e:
        sr.cmd_add(["TOK"])
    assert "interactive" in str(e.value)


def test_add_rejects_value_on_command_line():
    with pytest.raises(sr.SecretrunError):
        sr._parse_name_backend(["TOK", "the-value"])


# --------------------------------------------------------- excepthook ------- #
def test_excepthook_scrubs_traceback(capsys):
    sr._harden_process()
    sr._CURRENT_NAMES[:] = ["MY_TOKEN"]
    try:
        raise ValueError("this message might embed a value")
    except ValueError:
        import sys as _s
        with pytest.raises(SystemExit):
            sr.sys.excepthook(*_s.exc_info())
    err = capsys.readouterr().err
    assert "MY_TOKEN" in err
    assert "ValueError" in err
    assert "this message might embed a value" not in err  # no value/traceback text


# --------------------------------------------------------------- guard ------ #
def _guard(cmd):
    return guard._check(cmd)


@pytest.mark.parametrize("cmd", [
    "security dump-keychain",
    "security find-generic-password -s foo -a bar -w",
    "cat ~/.claude/projects/x/y.jsonl",
    "grep secret ~/.claude/projects/*.jsonl",
    "echo hunter2 | secretrun add TOK",
    "secretrun add TOK hunter2",
    "printenv",
    "env",
])
def test_guard_denies(cmd):
    with pytest.raises(SystemExit) as e:
        _guard(cmd)
    assert e.value.code == 2


@pytest.mark.parametrize("cmd", [
    "secretrun OPENAI_API_KEY -- curl https://api.example.com",
    "secretrun TOK -- sh -c 'echo \"$TOK\"'",   # masked by wrapper — allowed
    "secretrun add TOK",
    "secretrun add TOK -b aws",
    "ls -la",
    "env FOO=bar mycmd",                         # env used to SET a var, not dump
    "git status",
])
def test_guard_allows(cmd):
    assert _guard(cmd) is None


# ------------------------------------------------------------- redactor ----- #
@pytest.mark.parametrize("text,shape", [
    ("token=ghp_012345678901234567890123456789abcd", "ghp_"),
    ("key: sk-proj-abcdef0123456789abcdef", "sk-"),
    ("Authorization: Bearer eyJhbGciOi.eyJzdWIiOi.SflKxwRJSM", "eyJ"),
    ('{"api_key": "AbCdEf0123456789ghIjKl"}', "api_key"),
    ("aws AKIAIOSFODNN7EXAMPLE here", "AKIA"),
])
def test_redactor_scrubs_shapes(text, shape):
    out, n = redact._scrub(text)
    assert n >= 1
    assert "[REDACTED]" in out


def test_redactor_leaves_normal_text():
    out, n = redact._scrub("just a normal sentence with numbers 12 and 34")
    assert n == 0
    assert out == "just a normal sentence with numbers 12 and 34"


def test_redactor_full_hook_emits_updated_output(monkeypatch):
    payload = json.dumps({"tool_name": "Bash",
                          "tool_response": "leak ghp_012345678901234567890123456789abcd"})
    monkeypatch.setattr(redact.sys, "stdin", io.StringIO(payload))
    buf = io.StringIO()
    monkeypatch.setattr(redact.sys, "stdout", buf)
    redact.main()
    out = json.loads(buf.getvalue())
    hso = out["hookSpecificOutput"]
    assert "[REDACTED]" in hso["updatedToolOutput"]
    assert "ghp_" not in hso["updatedToolOutput"]
    assert "redacted 1" in hso["additionalContext"]


# --------------------------------------------------------- admin merge ------ #
def test_merge_hardening_unions_and_sets():
    target = {"permissions": {"deny": ["Read(**/.env*)"]},
              "cleanupPeriodDays": 30}
    snippet = json.load(open(os.path.join(ROOT, "settings/hardening-snippet.json")))
    changed = admin._merge_hardening(target, snippet)
    deny = target["permissions"]["deny"]
    assert deny.count("Read(**/.env*)") == 1          # not duplicated
    assert "Read(~/.ssh/**)" in deny                   # added
    assert target["env"]["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"] == "1"
    assert target["cleanupPeriodDays"] == 7            # lowered from 30
    assert changed                                     # reported changes


def test_merge_hardening_keeps_stricter_cleanup():
    target = {"cleanupPeriodDays": 3}
    snippet = {"cleanupPeriodDays": 7}
    admin._merge_hardening(target, snippet)
    assert target["cleanupPeriodDays"] == 3            # never relaxed


def test_merge_hardening_idempotent():
    snippet = json.load(open(os.path.join(ROOT, "settings/hardening-snippet.json")))
    target = {}
    admin._merge_hardening(target, snippet)
    second = admin._merge_hardening(target, snippet)
    assert second == []                                # nothing changes twice
