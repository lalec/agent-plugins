"""Tests for the srun scripts — the masker, store selection (incl. the cmd
store), run/spawn, add, check, the guard's deny rules and the redactor."""
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


@pytest.mark.parametrize("encode", ["b64encode", "urlsafe_b64encode"])
@pytest.mark.parametrize("before,after", [(b"", b":"), (b"abc:", b""), (b"user:", b""),
                                          (b"user:", b":x"), (b"ab", b"pad")])
def test_mask_value_inside_a_longer_base64_string(encode, before, after):
    import base64
    v = b"sk_live_51Hq?Zx>9~"                           # 18 bytes, + and / when encoded
    enc = getattr(base64, encode)(before + v + after)
    out = _mask({"K": bytearray(v)}, b"Authorization: Basic " + enc + b"\n")
    # every character of the value's encoding is masked but one at each edge
    kept = out.split(b"Basic ")[1].rstrip(b"=\n").replace(b"[REDACTED:K]", b"")
    assert len(kept) <= len(enc.rstrip(b"=")) - (4 * len(v) // 3 - 2)


def test_mask_split_across_chunks():
    v = b"supersecret123"
    dst = io.BytesIO()
    masking.Masker({"K": bytearray(v)}).stream(ByteDripReader(b"xx" + v + b"yy", 3), dst)
    assert dst.getvalue() == b"xx[REDACTED:K]yy"


def test_mask_skips_ultra_short_value():
    assert _mask({"X": bytearray(b"ab")}, b"cabbage\n") == b"cabbage\n"


# ------------------------------------------------------------ store plan ---- #
M = manifest.Manifest


def test_plan_manifest_wins_over_cli_store():
    assert manifest.plan("DB", "keychain", M({"DB": {"store": "aws", "id": "p/db"}})) \
        == ("aws", "p/db")


def test_plan_default_and_cli_store():
    assert manifest.plan("K", None, M({})) == ("keychain", "K")
    assert manifest.plan("K", "gcp", M({})) == ("gcp", "K")


def test_plan_ignores_an_old_cmd_key():
    assert manifest.plan("K", "aws", M({"K": {"cmd": "op read x"}})) == ("aws", "K")


@pytest.mark.parametrize("store", ["vault", "cmd"])
def test_plan_unknown_store_raises(store):
    with pytest.raises(stores.SrunError):
        manifest.plan("K", store, M({}))


def test_load_manifest_walks_up(tmp_path, monkeypatch):
    _manifest(tmp_path, {"A": {}})
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    m = manifest.load_manifest()
    assert m.secrets == {"A": {}} and m.namespace is None


@pytest.mark.parametrize("marker", ["dir", "file"])     # a worktree's .git is a file
def test_load_manifest_stops_at_the_repo_root(tmp_path, monkeypatch, marker):
    _manifest(tmp_path, {"OUTSIDE": {}})
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / ".git").mkdir() if marker == "dir" else (repo / ".git").write_text("gitdir: x")
    monkeypatch.chdir(repo / "src")
    assert manifest.load_manifest().secrets == {}


def test_load_manifest_stops_at_home(tmp_path, monkeypatch):
    _manifest(tmp_path, {"OUTSIDE": {}})
    (tmp_path / "home" / "proj").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path / "home" / "proj")
    assert manifest.load_manifest().secrets == {}


@pytest.mark.parametrize("target", ["file", "folder"])
def test_load_manifest_refuses_one_others_can_write(tmp_path, monkeypatch, target):
    _manifest(tmp_path, {"A": {}})
    os.chmod(tmp_path / ".srun.json" if target == "file" else tmp_path, 0o777)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(stores.SrunError) as e:
        manifest.load_manifest()
    assert "refusing" in str(e.value)


def test_load_manifest_refuses_one_another_user_owns(tmp_path, monkeypatch):
    _manifest(tmp_path, {"A": {}})
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(os, "getuid", lambda: 4242)
    with pytest.raises(stores.SrunError):
        manifest.load_manifest()


# ------------------------------------------------------- resolve via store -- #
@pytest.fixture
def keychain_values(monkeypatch):
    """The keychain replaced by a dict of id -> value."""
    kc = {}

    def get(name, sid):
        if sid not in kc:
            raise stores.SrunError(f"not found in keychain: {name}")
        return bytearray(kc[sid])

    monkeypatch.setitem(stores.RESOLVERS, "keychain", get)
    return kc


def test_an_old_cmd_entry_is_never_run(tmp_path, monkeypatch, keychain_values, capsys):
    ran = tmp_path / "ran"
    _manifest(tmp_path, {"K": {"cmd": f"touch {ran}; printf v"}})
    monkeypatch.chdir(tmp_path)
    assert manifest.plan("K", None, manifest.load_manifest()) == ("keychain", "K")
    assert manage.cmd_check([]) == 1
    with pytest.raises(stores.SrunError):
        sr.cmd_run(["K", "--", "true"])
    assert not ran.exists()
    assert "MISS  K  (keychain K)" in capsys.readouterr().out


def test_run_masks_output(tmp_path, monkeypatch, keychain_values, capfdbinary):
    keychain_values["PW"] = b"Dummy-Pw-91x"
    _manifest(tmp_path, ["PW"])
    monkeypatch.chdir(tmp_path)
    rc = sr.cmd_run(["PW", "--", "sh", "-c", 'echo "pw=$PW"'])
    out, _ = capfdbinary.readouterr()
    assert rc == 0 and out == b"pw=[REDACTED:PW]\n"


def test_check_reports_ok_and_miss_without_values(tmp_path, monkeypatch, keychain_values,
                                                  capsys):
    keychain_values["p/A"] = b"value-aaaa"
    _manifest(tmp_path, ["A", "B"], namespace="p")
    monkeypatch.chdir(tmp_path)
    assert manage.cmd_check([]) == 1
    out = capsys.readouterr().out
    assert "OK    A  (keychain p/A)" in out and "MISS  B  (keychain p/B)" in out
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
        manage._parse_name_store(["TOK", "the-value"])


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
    "cat ~/.aws/credentials",
    "cat $HOME/.ssh/id_ed25519",
    "grep token ~/.config/gcloud/credentials.db",
    "sudo cat .env", "env -i cat .env", "time head .env", "FOO=1 cat .env",
    "echo $(cat .env)", "echo `cat .env`", "true\ncat .env", "bash -lc 'cat .env'",
    # the file name itself comes from a substitution
    "cat $(find . -name .env)", "head $(echo .env)", "cat `realpath .env`",
    "srun add TOK $(cat ~/x)",
])
def test_guard_denies(cmd):
    with pytest.raises(SystemExit) as e:
        guard._check(cmd)
    assert e.value.code == 2


@pytest.mark.parametrize("cmd", [
    "srun OPENAI_API_KEY -- curl https://api.example.com",
    "srun TOK -- sh -c 'echo \"$TOK\"'",
    "srun add TOK", "srun add TOK -s aws",
    "srun add TOK && srun check TOK",
    "env FOO=bar mycmd", "git status",
    "cat .env.example", "cat .env.sample",
    "grep -c '^API_KEY=' .env", "grep -q API_KEY .env.local",
    "cat ~/.claude/projects/x/y.jsonl",        # transcripts stay readable
    "ls -la .env", "source .env && npm test",
])
def test_guard_allows(cmd):
    assert guard._check(cmd) is None


@pytest.mark.parametrize("tool,inp", [
    ("Read", {"file_path": "/repo/.env"}),
    ("Read", {"file_path": "/repo/web/.env.production.local"}),
    ("Read", {"file_path": os.path.expanduser("~/.aws/credentials")}),
    ("Read", {"file_path": os.path.expanduser("~/.ssh/id_rsa")}),
    ("Grep", {"pattern": "KEY", "path": "/repo/.env", "output_mode": "content"}),
    ("Grep", {"pattern": "KEY", "glob": ".env*", "output_mode": "content"}),
])
def test_guard_denies_file_tools(tool, inp):
    with pytest.raises(SystemExit) as e:
        guard._check_file_tool(tool, inp)
    assert e.value.code == 2


@pytest.mark.parametrize("tool,inp", [
    ("Read", {"file_path": "/repo/.env.example"}),
    ("Read", {"file_path": "/repo/src/env.ts"}),
    ("Read", {"file_path": os.path.expanduser("~/.claude/projects/x/y.jsonl")}),
    ("Grep", {"pattern": "KEY", "path": "/repo/.env"}),                 # file list
    ("Grep", {"pattern": "KEY", "path": "/repo/.env", "output_mode": "count"}),
    ("Grep", {"pattern": "KEY", "glob": ".env.example", "output_mode": "content"}),
    ("Glob", {"pattern": "**/.env"}),
])
def test_guard_allows_file_tools(tool, inp):
    assert guard._check_file_tool(tool, inp) is None


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
    "Basic internationalization support",                       # Basic, then prose
])
def test_redactor_leaves_normal_text(text):
    assert redact._scrub(text) == (text, 0)


@pytest.mark.parametrize("text", [
    "key=sk-proj-abcdefghijklmnop1234",
    "Authorization: Bearer abcdefghij0123456789",
    "> Authorization: Basic c2tfbGl2ZV81MUhxP1p4Pjl+Og==",
    '{"token": "abcdefghij0123456789"}',
    "export OPENAI=sk-abcdefghijklmnopqrstuvwx",
    "jwt eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.abcdefghijkl",
])
def test_redactor_still_catches_credentials(text):
    out, n = redact._scrub(text)
    assert n >= 1 and redact.REDACTED in out
