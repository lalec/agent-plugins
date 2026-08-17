"""Tests for the secretrun plugin.

Covers the security-load-bearing invariants: the output masker (encodings,
chunk-split, multiple secrets), resolver/manifest selection, the interactive-only
`add` TTY refusal, traceback scrubbing, the guard's deny rules, and the redactor's
shape matching. Loads the extension-less `bin/` scripts by path.
"""
import io
import json
import os
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


@pytest.fixture(autouse=True)
def _isolate_secretrun_home(tmp_path_factory, monkeypatch):
    # Keep every test's keychain-name index off the real ~/.secretrun.
    monkeypatch.setenv("SECRETRUN_HOME", str(tmp_path_factory.mktemp("srhome")))


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


def test_stream_flushes_complete_lines_before_eof():
    # MCP-launcher mode: a stdio client can't send its next request until it
    # received the server's full JSON-RPC line — the masker must emit through
    # the newline immediately, not hold a tail back until EOF (= deadlock).
    m = sr.Masker({"TOK": bytearray(b"supersecret123")})
    dst = io.BytesIO()

    class LineReader:
        calls = 0

        def read(self, _):
            self.calls += 1
            if self.calls == 1:
                return b'{"result":"supersecret123"}\n'
            # a real server would block here awaiting the client's next
            # request, which only comes if the previous line was delivered
            assert dst.getvalue().endswith(b"\n"), "line held back: deadlock"
            return b""

    m.stream(LineReader(), dst)
    assert dst.getvalue() == b'{"result":"[REDACTED:TOK]"}\n'


def test_stream_prefers_read1():
    # BufferedReader.read(n) blocks until n bytes or EOF; read1 returns as
    # soon as data arrives — required for long-running interactive children.
    class R1:
        used = []

        def read1(self, n):
            self.used.append("read1")
            return b""

        def read(self, n):
            self.used.append("read")
            return b""

    r = R1()
    sr.Masker({}).stream(r, io.BytesIO())
    assert r.used == ["read1"]


def test_stream_newline_inside_secret_still_masked():
    # a multi-line value disables the newline flush; the straddle-hold path
    # must still mask it across chunk boundaries
    val = b"line1\nline2"
    dst = io.BytesIO()
    sr.Masker({"PEM": bytearray(val)}).stream(
        ByteDripReader(b"a" + val + b"b\n", 4), dst)
    out = dst.getvalue()
    assert val not in out
    assert out == b"a[REDACTED:PEM]b\n"


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
def test_add_refuses_when_no_tty_and_no_gui(monkeypatch):
    monkeypatch.setattr(sr, "_tty_available", lambda: False)
    monkeypatch.setattr(sr.sys, "platform", "linux")
    with pytest.raises(sr.SecretrunError) as e:
        sr.cmd_add(["TOK"])
    assert "terminal" in str(e.value)


class _FakeProc:
    def __init__(self, returncode, stdout=b""):
        self.returncode, self.stdout = returncode, stdout


def test_add_uses_gui_dialog_when_no_tty(monkeypatch):
    monkeypatch.setattr(sr, "_tty_available", lambda: False)
    monkeypatch.setattr(sr.sys, "platform", "darwin")
    calls = {}

    def fake_run(cmd, **kw):
        if cmd[0] == "osascript":
            calls["osascript"] = cmd
            return _FakeProc(0, b"hunter2value\n")
        calls["store"] = (cmd, kw.get("input"))
        return _FakeProc(0)

    monkeypatch.setattr(sr.subprocess, "run", fake_run)
    assert sr.cmd_add(["TOK"]) == 0
    # NAME is an AppleScript argv argument, never spliced into the script source
    assert calls["osascript"][-1] == "TOK"
    assert all("TOK" not in part for part in calls["osascript"][1:-1])
    # value reached the keychain store via stdin, newline stripped, not in argv
    cmd, stdin = calls["store"]
    assert stdin == b"hunter2value\nhunter2value\n"
    assert all(b"hunter2value" not in str(a).encode() for a in cmd)


def test_add_gui_cancel_stores_nothing(monkeypatch):
    monkeypatch.setattr(sr, "_tty_available", lambda: False)
    monkeypatch.setattr(sr.sys, "platform", "darwin")
    monkeypatch.setattr(sr.subprocess, "run", lambda *a, **k: _FakeProc(1))
    with pytest.raises(sr.SecretrunError) as e:
        sr.cmd_add(["TOK"])
    assert "cancelled" in str(e.value)


def test_add_gui_empty_value_rejected(monkeypatch):
    monkeypatch.setattr(sr, "_tty_available", lambda: False)
    monkeypatch.setattr(sr.sys, "platform", "darwin")
    monkeypatch.setattr(sr.subprocess, "run", lambda *a, **k: _FakeProc(0, b"\n"))
    with pytest.raises(sr.SecretrunError) as e:
        sr.cmd_add(["TOK"])
    assert "empty" in str(e.value)


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


# ------------------------------------------------- keychain name index ------ #
def test_index_roundtrip():
    assert sr._index_load() is None                    # nothing stored yet
    sr._index_save(["B", "A", "A"])
    assert sr._index_load() == ["A", "B"]              # sorted, deduped


def test_index_update_only_when_bootstrapped():
    sr._index_update("X", add=True)                    # no index yet -> no-op
    assert sr._index_load() is None
    sr._index_save([])                                 # bootstrap (empty)
    sr._index_update("X", add=True)
    assert sr._index_load() == ["X"]
    sr._index_update("X", add=False)
    assert sr._index_load() == []


def test_list_keychain_bootstraps_once_then_no_dump(monkeypatch):
    calls = {"n": 0}

    def fake_dump():
        calls["n"] += 1
        return ["TOK", "DB"]

    monkeypatch.setattr(sr, "_keychain_dump_names", fake_dump)
    assert sr._list("keychain") == ["DB", "TOK"]       # first run bootstraps
    assert calls["n"] == 1
    assert sr._list("keychain") == ["DB", "TOK"]       # served from the index
    assert calls["n"] == 1                              # keychain NOT dumped again


def test_ls_keychain_first_run_note_then_silent(monkeypatch, capsys):
    monkeypatch.setattr(sr, "_keychain_dump_names", lambda: ["A"])
    sr.cmd_ls([])
    cap = capsys.readouterr()
    assert "A" in cap.out and "first run" in cap.err
    sr.cmd_ls([])                                       # index now exists
    assert "first run" not in capsys.readouterr().err


def test_sync_rebuilds_index_authoritatively(monkeypatch, capsys):
    sr._index_save(["STALE"])                           # simulate drift
    monkeypatch.setattr(sr, "_keychain_dump_names", lambda: ["REAL1", "REAL2"])
    assert sr.cmd_sync([]) == 0
    assert sr._index_load() == ["REAL1", "REAL2"]       # replaced, not merged
    assert "synced 2" in capsys.readouterr().out


def test_sync_rejects_non_keychain_backend():
    with pytest.raises(sr.SecretrunError):
        sr.cmd_sync(["-b", "aws"])


# ------------------------------------------------------------- sessions ----- #
def test_encode_cwd_matches_claude_dir_naming():
    # every non-alphanumeric char of the absolute path becomes '-'
    assert sr._encode_cwd("/Users/a/py-projects/x") == "-Users-a-py-projects-x"


def _write_session(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


def test_parse_session_extracts_only_safe_metadata(tmp_path):
    f = tmp_path / "abcd1234-5678.jsonl"
    _write_session(f, [
        {"type": "summary", "summary": "add stripe webhook handler"},
        {"type": "user", "timestamp": "2026-07-22T14:00:00Z", "cwd": "/repo",
         "gitBranch": "main",
         "message": {"role": "user", "content": "please add a webhook"}},
        {"type": "assistant", "timestamp": "2026-07-22T14:01:00Z", "cwd": "/repo",
         "message": {"role": "assistant", "content": [
             {"type": "tool_use", "name": "Write",
              "input": {"file_path": "/repo/src/api.ts"}},
             {"type": "tool_use", "name": "Bash",
              "input": {"command": "git add -A && git commit -m x"}}]}},
        {"type": "user", "timestamp": "2026-07-22T14:02:00Z", "cwd": "/repo",
         "message": {"role": "user",
                     "content": [{"type": "tool_result", "content": "ok"}]}},
    ])
    info = sr._parse_session(str(f))
    assert info["id"] == "abcd1234-5678"
    assert info["cwd"] == "/repo"
    assert info["branch"] == "main"
    assert info["first"] == "2026-07-22T14:00:00Z"
    assert info["last"] == "2026-07-22T14:02:00Z"
    assert info["messages"] == 3
    assert info["files"] == {"/repo/src/api.ts": 1}
    assert info["git"] == ["add", "commit"]
    assert info["label"] == "add stripe webhook handler"
    assert info["redacted"] == 0


def test_parse_session_redacts_secret_shaped_label(tmp_path):
    f = tmp_path / "sess.jsonl"
    _write_session(f, [
        {"type": "summary",
         "summary": "debug token ghp_012345678901234567890123456789abcd"}])
    info = sr._parse_session(str(f))
    assert "ghp_" not in info["label"]        # the value never surfaces
    assert "[REDACTED]" in info["label"]
    assert info["redacted"] >= 1


def test_parse_session_skips_malformed_lines(tmp_path):
    f = tmp_path / "sess.jsonl"
    f.write_text('not json\n{"type":"user","timestamp":"2026-01-01T00:00:00Z",'
                 '"message":{"role":"user","content":"hi"}}\n')
    info = sr._parse_session(str(f))          # bad line skipped, good line parsed
    assert info["messages"] == 1
    assert info["label"] == "hi"


def test_sessions_lists_current_project(tmp_path, monkeypatch, capsys):
    work = tmp_path / "work"
    work.mkdir()
    proj = tmp_path / "cfg" / "projects" / sr._encode_cwd(str(work))
    proj.mkdir(parents=True)
    _write_session(proj / "feedcafe-0001.jsonl", [
        {"type": "summary", "summary": "fix typo"},
        {"type": "user", "timestamp": "2026-07-21T09:00:00Z",
         "message": {"role": "user", "content": "fix the readme typo"}}])
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.chdir(work)
    assert sr.cmd_sessions([]) == 0
    out = capsys.readouterr().out
    assert "feedcafe" in out and "fix typo" in out


def test_sessions_empty_project_is_graceful(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.chdir(tmp_path)
    assert sr.cmd_sessions([]) == 0
    assert "no recorded sessions" in capsys.readouterr().out


def test_guard_transcript_deny_points_to_sanctioned_reader(capsys):
    with pytest.raises(SystemExit):
        guard._check("cat ~/.claude/projects/x/y.jsonl")
    err = capsys.readouterr().err
    assert "secretrun session" in err and "secretrun usage" in err


# ---------------------------------------------------------------- usage ----- #
def _assistant(model, usage, mid="msg_1", ts="2026-08-01T10:00:00Z"):
    return {"type": "assistant", "timestamp": ts,
            "message": {"role": "assistant", "id": mid, "model": model,
                        "content": [{"type": "text", "text": "hi"}],
                        "usage": usage}}


_USAGE_1M = {"input_tokens": 1000000, "output_tokens": 1000000,
             "cache_read_input_tokens": 1000000,
             "cache_creation": {"ephemeral_5m_input_tokens": 1000000,
                                "ephemeral_1h_input_tokens": 1000000}}


@pytest.fixture
def priced(tmp_path, monkeypatch):
    """A tiny, fully known price table so cost assertions are exact."""
    table = tmp_path / "prices.json"
    table.write_text(json.dumps({
        "updated": "2026-01-01",
        "cache": {"write_5m": 1.25, "write_1h": 2.0, "read": 0.1},
        "models": {"claude-test-1": {"in": 10, "out": 100,
                                     "fast": {"in": 20, "out": 200}}}}))
    monkeypatch.setenv("SECRETRUN_PRICES", str(table))
    monkeypatch.setattr(sr, "_PRICES", None)
    yield
    monkeypatch.setattr(sr, "_PRICES", None)


def test_usage_dedupes_repeated_records_for_one_message(tmp_path):
    # Claude Code writes one record per content block, each repeating the usage.
    f = tmp_path / "s.jsonl"
    _write_session(f, [_assistant("claude-test-1", _USAGE_1M, mid="msg_a")] * 3)
    counts = sr._parse_session(str(f))["usage"][("claude-test-1", "standard")]
    assert counts == {"in": 1000000, "out": 1000000, "cache_read": 1000000,
                      "cache_w5": 1000000, "cache_w1h": 1000000, "msgs": 1}


def test_usage_splits_cache_writes_by_ttl_and_prices_them(tmp_path, priced):
    f = tmp_path / "s.jsonl"
    _write_session(f, [_assistant("claude-test-1", _USAGE_1M)])
    counts = sr._parse_session(str(f))["usage"][("claude-test-1", "standard")]
    # in 10 + out 100 + read 1 + write5m 12.5 + write1h 20 (1M tokens each)
    assert sr._cost(counts, "claude-test-1", "standard") == pytest.approx(143.5)


def test_usage_fast_mode_uses_its_own_rate(tmp_path, priced):
    f = tmp_path / "s.jsonl"
    usage = dict(_USAGE_1M, speed="fast")
    _write_session(f, [_assistant("claude-test-1", usage)])
    info = sr._parse_session(str(f))
    counts = info["usage"][("claude-test-1", "fast")]
    assert sr._cost(counts, "claude-test-1", "fast") == pytest.approx(287.0)


def test_usage_flat_cache_count_falls_back_to_5m_rate(tmp_path, priced):
    f = tmp_path / "s.jsonl"
    _write_session(f, [_assistant("claude-test-1", {
        "input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 1000000})])
    counts = sr._parse_session(str(f))["usage"][("claude-test-1", "standard")]
    assert counts["cache_w5"] == 1000000 and counts["cache_w1h"] == 0
    assert sr._cost(counts, "claude-test-1", "standard") == pytest.approx(12.5)


def test_usage_dated_snapshot_id_resolves_to_family_rate(priced):
    assert sr._rate("claude-test-1-20260101", "standard") == (10.0, 100.0)


def test_usage_unknown_model_is_unpriced_never_guessed(tmp_path, priced):
    f = tmp_path / "s.jsonl"
    _write_session(f, [_assistant("claude-unknown-9", _USAGE_1M)])
    totals, cost, unpriced = sr._roll_up(sr._parse_session(str(f))["usage"])
    assert totals["out"] == 1000000        # tokens still reported
    assert cost is None and unpriced == {"claude-unknown-9"}
    assert sr._usd(cost) == "—"


def test_usage_zero_token_turns_are_not_a_model(tmp_path):
    # synthetic/interrupted turns bill nothing and must not appear as a model
    f = tmp_path / "s.jsonl"
    _write_session(f, [_assistant("<synthetic>", {
        "input_tokens": 0, "output_tokens": 0,
        "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0})])
    assert sr._parse_session(str(f))["usage"] == {}


def _usage_project(tmp_path, monkeypatch, records, name="beefcafe-0001.jsonl"):
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    proj = tmp_path / "cfg" / "projects" / sr._encode_cwd(str(work))
    proj.mkdir(parents=True, exist_ok=True)
    _write_session(proj / name, records)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.chdir(work)


def test_usage_reports_tokens_cost_and_price_provenance(
        tmp_path, monkeypatch, capsys, priced):
    _usage_project(tmp_path, monkeypatch,
                   [_assistant("claude-test-1", _USAGE_1M)])
    assert sr.cmd_usage([]) == 0
    out = capsys.readouterr().out
    assert "beefcafe" in out and "test-1" in out
    assert "143.50" in out                       # per-session and total
    assert "prices as of 2026-01-01" in out      # figures are dated, not implied


def test_usage_emits_no_content_only_numbers(tmp_path, monkeypatch, capsys, priced):
    _usage_project(tmp_path, monkeypatch, [
        {"type": "summary", "summary": "wire up the acme billing webhook"},
        _assistant("claude-test-1", _USAGE_1M)])
    sr.cmd_usage([])
    out = capsys.readouterr().out
    # `sessions` may surface a redacted label; `usage` surfaces no prose at all
    assert "acme" not in out and "webhook" not in out


def test_usage_since_filters_by_last_active(tmp_path, monkeypatch, capsys, priced):
    _usage_project(tmp_path, monkeypatch, [
        _assistant("claude-test-1", _USAGE_1M, ts="2020-01-01T00:00:00Z")])
    assert sr.cmd_usage(["--since", "7"]) == 0
    assert "no recorded token usage" in capsys.readouterr().out


def test_usage_rejects_bad_since():
    with pytest.raises(sr.SecretrunError):
        sr.cmd_usage(["--since", "soon"])
    with pytest.raises(sr.SecretrunError):
        sr.cmd_usage(["--since", "0"])
    with pytest.raises(sr.SecretrunError):
        sr.cmd_usage(["--nope"])


def test_usage_survives_missing_price_table(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SECRETRUN_PRICES", str(tmp_path / "gone.json"))
    monkeypatch.setattr(sr, "_PRICES", None)
    _usage_project(tmp_path, monkeypatch,
                   [_assistant("claude-test-1", _USAGE_1M)])
    assert sr.cmd_usage([]) == 0                 # degrades, never crashes
    out = capsys.readouterr().out
    assert "1.0M" in out and "no usable price table" in out
    monkeypatch.setattr(sr, "_PRICES", None)


def test_shipped_price_table_is_loadable_and_dated():
    root = os.path.dirname(os.path.dirname(os.path.abspath(sr.__file__)))
    with open(os.path.join(root, "share", "prices.json")) as f:
        table = json.load(f)
    assert table["updated"] and table["cache"]["read"] and table["models"]
    for name, entry in table["models"].items():
        assert name.startswith("claude-") and entry["in"] > 0 and entry["out"] > 0
