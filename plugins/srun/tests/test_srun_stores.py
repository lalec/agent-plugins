"""Tests for store choice (a NAME's own entry, -s, the project, the personal
default, the keychain), the short manifest form, and the password-manager
stores against faked CLIs — no value ever on an argv."""
import json

import pytest
from conftest import write_manifest

import guard  # noqa: E402
import manage  # noqa: E402
import managers  # noqa: E402
import manifest  # noqa: E402
import stores  # noqa: E402

M = manifest.Manifest


# ------------------------------------------------------------ store choice -- #
def test_store_precedence(monkeypatch):
    assert manifest.plan("K", None, M({}))[0] == "keychain"
    manifest.set_default_store("lastpass")
    assert manifest.plan("K", None, M({}))[0] == "lastpass"
    assert manifest.plan("K", None, M({}, store="dashlane"))[0] == "dashlane"
    assert manifest.plan("K", "aws", M({}, store="dashlane"))[0] == "aws"
    assert manifest.plan("K", "aws", M({"K": {"store": "gcp"}}, store="dashlane"))[0] == "gcp"


def test_default_command_shows_and_sets(capsys):
    manage.cmd_default([])
    assert "keychain (built in)" in capsys.readouterr().out
    manage.cmd_default(["1password"])
    manage.cmd_default([])
    assert capsys.readouterr().out.splitlines()[-1] == "default store: 1password"
    for bad in (["cmd"], ["vault"], ["a", "b"]):
        with pytest.raises(stores.SrunError):
            manage.cmd_default(bad)


def test_load_reads_the_list_form_and_the_legacy_dict(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".srun.json").write_text(json.dumps(
        {"namespace": "p", "store": "lastpass", "secrets": ["A", "B"]}))
    m = manifest.load_manifest()
    assert m.secrets == {"A": {}, "B": {}} and m.store == "lastpass"
    assert manifest.plan("A", None, m) == ("lastpass", "p/A")
    write_manifest(tmp_path, {"A": {"backend": "aws"}}, namespace="p")
    assert manifest.load_manifest().secrets == {"A": {"store": "aws"}}


def test_unknown_project_store_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".srun.json").write_text(json.dumps({"store": "vault", "secrets": []}))
    with pytest.raises(stores.SrunError):
        manifest.load_manifest()


# ------------------------------------------------------- faked manager CLIs -- #
class _P:
    def __init__(self, rc=0, out=b""):
        self.returncode, self.stdout = rc, out


@pytest.fixture
def cli(monkeypatch):
    """Route subprocess.run to a table keyed by the first two argv words;
    records every call so tests can assert no value reached an argv."""
    calls, table = [], {}

    def run(argv, **kw):
        calls.append((argv, kw))
        out = table.get(tuple(argv[:2]))
        if out is None:
            raise FileNotFoundError(argv[0])
        return out(argv, kw) if callable(out) else out

    monkeypatch.setattr(managers.subprocess, "run", run)
    monkeypatch.setattr(stores.subprocess, "run", run)
    return table, calls


def _no_value_in_argv(calls, value):
    assert all(value not in " ".join(a) for a, _ in calls)


def test_1password_reads_the_exact_title_by_id(cli):
    table, calls = cli
    table[("op", "item")] = _P(out=json.dumps([
        {"id": "i1", "title": "p/API_KEY_2", "vault": {"id": "v1"}},
        {"id": "i2", "title": "p/API_KEY", "vault": {"id": "v2"}}]).encode())
    table[("op", "read")] = lambda a, kw: _P(out=b"op-val-11\n") \
        if a[2] == "op://v2/i2/password" else _P(1)
    assert stores.RESOLVERS["1password"]("API_KEY", "p/API_KEY") == bytearray(b"op-val-11")
    assert all(kw["stdin"] is managers.subprocess.DEVNULL for _, kw in calls)
    _no_value_in_argv(calls, "op-val-11")


@pytest.mark.parametrize("items,msg", [([], "not found"),
                                       ([{"id": "a", "title": "p/K"}] * 2, "keep one")])
def test_1password_missing_or_duplicate_title(cli, items, msg):
    cli[0][("op", "item")] = _P(out=json.dumps(items).encode())
    with pytest.raises(stores.SrunError) as e:
        stores.RESOLVERS["1password"]("K", "p/K")
    assert msg in str(e.value)


def test_dashlane_picks_the_exact_title_from_substring_matches(cli):
    table, calls = cli
    table[("dcli", "password")] = _P(out=json.dumps([
        {"title": "p/K_OLD", "password": "dl-old-1"},
        {"title": "p/K", "password": "dl-val-22"}]).encode())
    assert stores.RESOLVERS["dashlane"]("K", "p/K") == bytearray(b"dl-val-22")
    assert calls[0][0] == ["dcli", "password", "-o", "json", "title=p/K"]


def test_lastpass_locked_fails_before_any_read(cli):
    table, calls = cli
    table[("lpass", "status")] = _P(1)
    with pytest.raises(stores.SrunError) as e:
        stores.RESOLVERS["lastpass"]("K", "p/K")
    assert "lpass login" in str(e.value) and len(calls) == 1


def test_lastpass_read_requires_one_exact_fullname(cli):
    table, _ = cli
    table[("lpass", "status")] = _P(0)
    table[("lpass", "show")] = _P(out=json.dumps([
        {"fullname": "p/K", "password": "lp-val-33"},
        {"fullname": "p/K2", "password": "x"}]).encode())
    assert stores.RESOLVERS["lastpass"]("K", "p/K") == bytearray(b"lp-val-33")


def test_lastpass_add_sends_the_value_on_stdin_only(cli, tmp_path, monkeypatch, capsys):
    table, calls = cli
    table[("lpass", "status")] = _P(0)
    table[("lpass", "edit")] = _P(0)
    write_manifest(tmp_path, ["K"], namespace="p")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(manage, "read_hidden", lambda n: bytearray(b"lp-new-44"))
    assert manage.cmd_add(["K", "-s", "lastpass"]) == 0
    argv, kw = calls[-1]
    assert argv == ["lpass", "edit", "--non-interactive", "--password", "p/K"]
    assert kw["input"] == b"lp-new-44"
    _no_value_in_argv(calls, "lp-new-44")
    assert "lp-new-44" not in capsys.readouterr().out


@pytest.mark.parametrize("store,app", [("1password", "1Password app"),
                                       ("dashlane", "Dashlane app")])
def test_app_only_stores_say_where_to_create_the_item(tmp_path, monkeypatch, store, app):
    (tmp_path / ".srun.json").write_text(json.dumps(
        {"namespace": "p", "store": store, "secrets": ["K"]}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(manage, "read_hidden", lambda n: pytest.fail("prompted"))
    with pytest.raises(stores.SrunError) as e:
        manage.cmd_add(["K"])
    assert app in str(e.value) and "p/K" in str(e.value)


def test_missing_cli_is_a_named_error(cli):
    with pytest.raises(stores.SrunError) as e:
        stores.RESOLVERS["dashlane"]("K", "p/K")
    assert "not installed" in str(e.value)


def test_guard_still_denies_a_value_after_the_store_flag():
    with pytest.raises(SystemExit) as e:
        guard._check("srun add TOK -s lastpass hunter2")
    assert e.value.code == 2
    guard._check("srun add TOK -s lastpass")
