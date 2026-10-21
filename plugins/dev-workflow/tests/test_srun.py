"""Tests for shared/srun — the masker, store selection (incl. the cmd store),
run/spawn, add, check, the guard's deny rules, the redactor and `init` wiring.
Maintainer-only: never copied into projects."""
import io
import json
import os
import sys
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader

import pytest
from conftest import SR_DIR, write_manifest as _manifest

import guard  # noqa: E402
import manage  # noqa: E402
import manifest  # noqa: E402
import masking  # noqa: E402
import names  # noqa: E402
import prompt  # noqa: E402
import redact  # noqa: E402
import stores  # noqa: E402
import wire  # noqa: E402

_loader = SourceFileLoader("srun_cli", os.path.join(SR_DIR, "srun"))
sr = module_from_spec(spec_from_loader("srun_cli", _loader))
_loader.exec_module(sr)



# ----------------------------------------------------------------- masker ---- #
def _mask(secrets, data):
    dst = io.BytesIO()
    masking.Masker(secrets).stream(io.BytesIO(data), dst)
    return dst.getvalue()


class ByteDripReader:
    """Yields the payload `n` bytes at a time to force chunk boundaries."""
    def __init__(self, data, n):
        self.data, self.n, self.i = data, n, 0

    def read(self, _):
        chunk = self.data[self.i:self.i + self.n]
        self.i += self.n
        return chunk


def test_mask_raw_and_encoded_forms():
    import base64
    v = b"supersecret123"
    out = _mask({"K": bytearray(v)}, b"a " + v + b" b " + base64.b64encode(v) + b"\n")
    assert v not in out and base64.b64encode(v) not in out
    assert out.count(b"[REDACTED:K]") == 2


def test_mask_split_across_chunks():
    v = b"supersecret123"
    dst = io.BytesIO()
    masking.Masker({"K": bytearray(v)}).stream(ByteDripReader(b"xx" + v + b"yy", 3), dst)
    assert dst.getvalue() == b"xx[REDACTED:K]yy"


def test_mask_skips_ultra_short_value():
    assert _mask({"X": bytearray(b"ab")}, b"cabbage\n") == b"cabbage\n"


# ------------------------------------------------------------ store plan ---- #
M = manifest.Manifest


def test_plan_manifest_wins_over_cli_backend():
    assert manifest.plan("DB", "keychain", M({"DB": {"backend": "aws", "id": "p/db"}})) \
        == ("aws", "p/db")


def test_plan_default_and_cli_backend():
    assert manifest.plan("K", None, M({})) == ("keychain", "K")
    assert manifest.plan("K", "gcp", M({})) == ("gcp", "K")


def test_plan_cmd_entry_is_the_cmd_store():
    assert manifest.plan("K", "aws", M({"K": {"cmd": "op read x"}})) == ("cmd", "op read x")


@pytest.mark.parametrize("backend", ["vault", "cmd"])
def test_plan_unknown_backend_or_cmd_without_entry_raises(backend):
    with pytest.raises(stores.SrunError):
        manifest.plan("K", backend, M({}))


def test_load_manifest_walks_up(tmp_path, monkeypatch):
    _manifest(tmp_path, {"A": {}})
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    m = manifest.load_manifest()
    assert m.secrets == {"A": {}} and m.namespace is None


# ------------------------------------------------------------- cmd store ---- #
def test_cmd_store_reads_env_file_from_manifest_dir(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("OTHER=1\nMAPS_KEY=val-from-file-99\n")
    _manifest(tmp_path, {"MAPS_KEY": {"cmd": "sed -n 's/^MAPS_KEY=//p' .env"}})
    sub = tmp_path / "web"
    sub.mkdir()
    monkeypatch.chdir(sub)                       # runs from the manifest's dir
    assert bytes(stores.RESOLVERS["cmd"]("MAPS_KEY", "sed -n 's/^MAPS_KEY=//p' .env")) \
        == b"val-from-file-99"


@pytest.mark.parametrize("cmd", ["exit 3", "true", "echo oops >&2; exit 1"])
def test_cmd_store_without_value_is_missing(cmd):
    with pytest.raises(stores.SrunError) as e:
        stores.RESOLVERS["cmd"]("K", cmd)
    assert "oops" not in str(e.value)


def test_cmd_store_is_read_only(tmp_path, monkeypatch):
    _manifest(tmp_path, {"K": {"cmd": "printf v"}})
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(manage, "read_hidden", lambda n: pytest.fail("prompted"))
    with pytest.raises(stores.SrunError) as e:
        manage.cmd_add(["K"])
    assert "secret manager" in str(e.value)
    with pytest.raises(stores.SrunError):
        manage.cmd_rm(["K"])


def test_run_with_cmd_store_masks_output(tmp_path, monkeypatch, capfdbinary):
    _manifest(tmp_path, {"PW": {"cmd": "printf Dummy-Pw-91x"}})
    monkeypatch.chdir(tmp_path)
    rc = sr.cmd_run(["PW", "--", "sh", "-c", 'echo "pw=$PW"'])
    out, _ = capfdbinary.readouterr()
    assert rc == 0 and out == b"pw=[REDACTED:PW]\n"


def test_check_reports_ok_and_miss_without_values(tmp_path, monkeypatch, capsys):
    _manifest(tmp_path, {"A": {"cmd": "printf value-aaaa"}, "B": {"cmd": "exit 1"}})
    monkeypatch.chdir(tmp_path)
    assert manage.cmd_check([]) == 1
    out = capsys.readouterr().out
    assert "OK    A  (cmd)" in out and "MISS  B  (cmd)" in out
    assert "printf" not in out
    assert "value-aaaa" not in out
    assert manage.cmd_check(["A"]) == 0


# ------------------------------------------------------------- run/spawn ---- #
def test_spawn_masks_env_value(capfdbinary):
    rc = sr._spawn(["sh", "-c", 'printf "%s" "$SECRET_X"'],
                   {"SECRET_X": bytearray(b"supersecret123")}, None)
    out, _ = capfdbinary.readouterr()
    assert rc == 0 and out == b"[REDACTED:SECRET_X]"


def test_spawn_exit_code_and_signal_passthrough(capfdbinary):
    assert sr._spawn(["sh", "-c", "exit 3"], {"K": bytearray(b"vvvv")}, None) == 3
    assert sr._spawn(["sh", "-c", "kill -9 $$"], {"K": bytearray(b"vvvv")}, None) == 137


def test_spawn_stdin_mode_keeps_value_out_of_env(capfdbinary):
    rc = sr._spawn(["sh", "-c", 'cat; echo "env=[${SECRET_X:-unset}]"'],
                   {"SECRET_X": bytearray(b"supersecret123")}, "SECRET_X")
    out, _ = capfdbinary.readouterr()
    assert rc == 0 and b"supersecret123" not in out
    assert b"env=[unset]" in out and b"[REDACTED:SECRET_X]" in out


@pytest.mark.parametrize("argv", [["TOK", "echo", "hi"], ["TOK", "--stdin", "OTHER", "--", "echo"],
                                  ["--", "echo"], ["TOK", "--"]])
def test_run_rejects_bad_argv(argv):
    with pytest.raises(stores.SrunError):
        sr.cmd_run(argv)


# ------------------------------------------------------------------ add ----- #
class _FakeProc:
    def __init__(self, returncode, stdout=b""):
        self.returncode, self.stdout = returncode, stdout


def test_add_refuses_when_no_tty_and_no_gui(monkeypatch):
    monkeypatch.setattr(prompt, "tty_available", lambda: False)
    monkeypatch.setattr(prompt.sys, "platform", "linux")
    with pytest.raises(stores.SrunError) as e:
        manage.cmd_add(["TOK"])
    assert "terminal" in str(e.value)


def test_add_uses_gui_dialog_and_keeps_value_out_of_argv(monkeypatch):
    monkeypatch.setattr(prompt, "tty_available", lambda: False)
    monkeypatch.setattr(prompt.sys, "platform", "darwin")
    calls = {}

    def fake_run(cmd, **kw):
        if cmd[0] == "osascript":
            calls["osascript"] = cmd
            return _FakeProc(0, b"hunter2value\n")
        calls["store"] = (cmd, kw.get("input"))
        return _FakeProc(0)

    monkeypatch.setattr(prompt.subprocess, "run", fake_run)
    monkeypatch.setattr(stores.subprocess, "run", fake_run)
    assert manage.cmd_add(["TOK"]) == 0
    assert calls["osascript"][-1] == "TOK"
    assert all("TOK" not in part for part in calls["osascript"][1:-1])
    cmd, stdin = calls["store"]
    assert stdin == b"hunter2value\nhunter2value\n"
    assert all("hunter2value" not in str(a) for a in cmd)


def test_add_gui_cancel_or_empty_stores_nothing(monkeypatch):
    monkeypatch.setattr(prompt, "tty_available", lambda: False)
    monkeypatch.setattr(prompt.sys, "platform", "darwin")
    for proc, word in ((_FakeProc(1), "cancelled"), (_FakeProc(0, b"\n"), "empty")):
        monkeypatch.setattr(prompt.subprocess, "run", lambda *a, p=proc, **k: p)
        with pytest.raises(stores.SrunError) as e:
            manage.cmd_add(["TOK"])
        assert word in str(e.value)


def test_add_rejects_value_on_command_line():
    with pytest.raises(stores.SrunError):
        manage._parse_name_backend(["TOK", "the-value"])


def test_excepthook_scrubs_traceback(capsys):
    sr._harden_process()
    stores.CURRENT_NAMES[:] = ["MY_TOKEN"]
    try:
        raise ValueError("this message might embed a value")
    except ValueError:
        with pytest.raises(SystemExit):
            sr.sys.excepthook(*sys.exc_info())
    err = capsys.readouterr().err
    assert "MY_TOKEN" in err and "ValueError" in err
    assert "might embed" not in err


# ------------------------------------------------- keychain name index ------ #
def test_list_keychain_bootstraps_once_then_no_dump(monkeypatch):
    calls = {"n": 0}

    def fake_dump():
        calls["n"] += 1
        return ["TOK", "DB"]

    monkeypatch.setattr(names, "keychain_dump_names", fake_dump)
    assert names.list_names("keychain") == ["DB", "TOK"]
    assert names.list_names("keychain") == ["DB", "TOK"]
    assert calls["n"] == 1


def test_index_update_only_when_bootstrapped():
    names.index_update("X", add=True)
    assert names.index_load() is None
    names.index_save([])
    names.index_update("X", add=True)
    assert names.index_load() == ["X"]
    names.index_update("X", add=False)
    assert names.index_load() == []


# --------------------------------------------------------------- guard ------ #
@pytest.mark.parametrize("cmd", [
    "security dump-keychain",
    "security find-generic-password -s foo -a bar -w",
    "echo hunter2 | srun add TOK",
    "srun add TOK hunter2",
    "printenv", "env",
    "cat .env",
    "cat web/.env.local",
    "sed -n 's/x/y/p' .env.production",
    "grep PASSWORD .env",
    "cd app && tail -5 .env",
    "srun K -- sh -c 'cat .env'",
    "srun K -- head .env",
    "bash -c 'grep X .env.local'",
])
def test_guard_denies(cmd):
    with pytest.raises(SystemExit) as e:
        guard._check(cmd)
    assert e.value.code == 2


@pytest.mark.parametrize("cmd", [
    "srun OPENAI_API_KEY -- curl https://api.example.com",
    "srun TOK -- sh -c 'echo \"$TOK\"'",
    "srun add TOK", "srun add TOK -b aws",
    "srun add TOK && srun check TOK",
    "env FOO=bar mycmd", "git status",
    "cat .env.example", "cat .env.sample",
    "grep -c '^API_KEY=' .env", "grep -q API_KEY .env.local",
    "cat ~/.claude/projects/x/y.jsonl",        # transcripts stay readable
    "ls -la .env", "source .env && npm test",
])
def test_guard_allows(cmd):
    assert guard._check(cmd) is None


# ------------------------------------------------------------- redactor ----- #
def test_redactor_full_hook_emits_updated_output(monkeypatch):
    payload = json.dumps({"tool_name": "Bash",
                          "tool_response": "leak ghp_012345678901234567890123456789abcd"})
    monkeypatch.setattr(redact.sys, "stdin", io.StringIO(payload))
    buf = io.StringIO()
    monkeypatch.setattr(redact.sys, "stdout", buf)
    redact.main()
    hso = json.loads(buf.getvalue())["hookSpecificOutput"]
    assert "ghp_" not in hso["updatedToolOutput"]
    assert "redacted 1" in hso["additionalContext"]


def test_redactor_keeps_the_response_shape(monkeypatch):
    bash = {"stdout": "leak ghp_012345678901234567890123456789abcd", "stderr": "",
            "interrupted": False}
    read = {"type": "text", "file": {"filePath": "/x", "content": "key: sk-proj-abcdef0123456789abcdef"}}
    for resp, get in ((bash, lambda o: o["stdout"]), (read, lambda o: o["file"]["content"])):
        monkeypatch.setattr(redact.sys, "stdin", io.StringIO(json.dumps(
            {"tool_name": "Bash", "tool_response": resp})))
        buf = io.StringIO()
        monkeypatch.setattr(redact.sys, "stdout", buf)
        redact.main()
        out = json.loads(buf.getvalue())["hookSpecificOutput"]["updatedToolOutput"]
        assert set(out) == set(resp)
        assert "[REDACTED]" in get(out)
    assert out["file"]["filePath"] == "/x"


@pytest.mark.parametrize("text", [
    "a normal sentence 12 34",
    "**Id:** tosk-web-must-read-techniques-fuzzing-as-an",      # sk- inside a word
    "see task-runner-configuration-loader and disk-usage-report-generator",
    "cannot mint a Bearer token\npost-body-injection-true-positive-live",
    "the token budget-allocation-for-the-quarter",              # keyword, then prose
])
def test_redactor_leaves_normal_text(text):
    assert redact._scrub(text) == (text, 0)


@pytest.mark.parametrize("text", [
    "key=sk-proj-abcdefghijklmnop1234",
    "Authorization: Bearer abcdefghij0123456789",
    '{"token": "abcdefghij0123456789"}',
    "export OPENAI=sk-abcdefghijklmnopqrstuvwx",
    "jwt eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.abcdefghijkl",
])
def test_redactor_still_catches_credentials(text):
    out, n = redact._scrub(text)
    assert n >= 1 and redact.REDACTED in out


# ------------------------------------------------------------------ init ---- #
def test_init_merges_idempotently_and_keeps_other_settings():
    settings = {"model": "x", "hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": []}]},
                "permissions": {"deny": ["Read(**/.env)"]}}
    ref = '"$CLAUDE_PROJECT_DIR"/.claude/srun'
    first = wire.merge(settings, ref)
    assert first and settings["model"] == "x"
    assert settings["permissions"]["deny"].count("Read(**/.env)") == 1
    assert "Read(**/.env.example)" not in settings["permissions"]["deny"]
    assert len(settings["hooks"]["PreToolUse"]) == 2
    assert wire.merge(settings, ref) == []


def test_init_refs_project_relative_inside_repo(tmp_path):
    assert wire._folder_ref(os.path.dirname(os.path.dirname(SR_DIR))) == \
        '"$CLAUDE_PROJECT_DIR"/shared/srun'
    assert wire._folder_ref(str(tmp_path)) == '"%s"' % SR_DIR
