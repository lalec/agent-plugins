"""Tests for srun namespacing — namespaced store ids, `init` writing the
namespace once, and `migrate` moving keychain values off the bare NAME.
Maintainer-only: never copied into projects."""
import json
import os
import shutil
import subprocess
import sys

import pytest
from conftest import write_manifest

import manage  # noqa: E402
import manifest  # noqa: E402
import stores  # noqa: E402
import wire  # noqa: E402

M = manifest.Manifest


# ------------------------------------------------------------------ plan ---- #
@pytest.mark.parametrize("backend,sid", [
    ("keychain", "app/K"), ("aws", "app/K"), ("gcp", "app_K")])
def test_plan_namespaces_ids_per_backend(backend, sid):
    m = M({"K": {"backend": backend}}, "app")
    assert manifest.plan("K", None, m) == (backend, sid)
    assert manifest.plan("X", backend, M({}, "app"))[1] == sid.replace("K", "X")


def test_plan_explicit_id_wins_and_cmd_is_unchanged():
    m = M({"S": {"backend": "aws", "id": "shared/s"}, "C": {"cmd": "op read x"}}, "app")
    assert manifest.plan("S", None, m) == ("aws", "shared/s")
    assert manifest.plan("C", None, m) == ("cmd", "op read x")


def test_plan_without_namespace_is_the_bare_name():
    assert manifest.plan("K", None, M({"K": {}})) == ("keychain", "K")


@pytest.mark.parametrize("ns", ["bad/ns", "a b", "", 5, "x.y"])
def test_invalid_namespace_raises_naming_the_key(tmp_path, monkeypatch, ns):
    (tmp_path / ".srun.json").write_text(json.dumps({"namespace": ns, "secrets": {}}))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(stores.SrunError) as e:
        manifest.load_manifest()
    assert '"namespace"' in str(e.value)
    assert ns == "" or str(ns) not in str(e.value)


# ------------------------------------------------------------------ init ---- #
def _git_repo(tmp_path, name):
    root = tmp_path / name
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def test_init_creates_manifest_with_namespace_once(tmp_path, monkeypatch, capsys):
    root = _git_repo(tmp_path, "my.app")
    monkeypatch.chdir(root)
    assert wire.init([]) == 0
    path = root / ".srun.json"
    assert json.loads(path.read_text()) == {"namespace": "my-app", "secrets": {}}
    assert '"namespace": "my-app"' in capsys.readouterr().out
    before = path.read_bytes()
    assert wire.init([]) == 0
    assert path.read_bytes() == before
    out = capsys.readouterr().out
    assert "already wired" in out and "namespace" not in out


def test_init_adds_namespace_keeping_entries_and_never_rewrites(tmp_path, monkeypatch):
    root = _git_repo(tmp_path, "web")
    write_manifest(root, {"A": {"backend": "aws", "id": "x"}})
    monkeypatch.chdir(root)
    wire.init([])
    data = json.loads((root / ".srun.json").read_text())
    assert data == {"namespace": "web", "secrets": {"A": {"backend": "aws", "id": "x"}}}
    write_manifest(root, {}, namespace="chosen")
    wire.init([])
    assert json.loads((root / ".srun.json").read_text())["namespace"] == "chosen"


def test_init_global_touches_no_manifest(tmp_path, monkeypatch):
    root = _git_repo(tmp_path, "proj")
    monkeypatch.chdir(root)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert wire.init(["--global"]) == 0
    assert not (root / ".srun.json").exists()
    assert (tmp_path / "home" / ".claude" / "settings.json").is_file()


# --------------------------------------------------------------- migrate ---- #
@pytest.fixture
def fake_keychain(monkeypatch):
    kc = {}

    def get(name, sid):
        if sid not in kc:
            raise stores.SrunError(f"not found in keychain: {name}")
        return bytearray(kc[sid])

    def put(backend, name, sid, vb):
        kc[sid] = bytes(vb)

    def rm(backend, name, sid):
        kc.pop(sid)

    monkeypatch.setitem(stores.RESOLVERS, "keychain", get)
    monkeypatch.setattr(manage, "store", put)
    monkeypatch.setattr(manage, "delete", rm)
    return kc


def test_migrate_reports_each_name_and_never_prints_a_value(
        tmp_path, monkeypatch, capsys, fake_keychain):
    write_manifest(tmp_path, {"MOVE": {}, "GONE": {}, "BOTH": {}, "PIN": {"id": "shared"},
                              "OP": {"cmd": "op read x"}, "CLOUD": {"backend": "aws"}},
                   namespace="app")
    fake_keychain.update({"MOVE": b"val-move-1", "BOTH": b"val-old-2",
                          "app/BOTH": b"val-new-3", "shared": b"val-pin-4"})
    monkeypatch.chdir(tmp_path)
    assert manage.cmd_migrate([]) == 0
    out = capsys.readouterr().out
    lines = {ln[12:].split()[0]: ln[:10].strip() for ln in out.splitlines()}
    assert lines == {"MOVE": "moved", "GONE": "not stored", "BOTH": "kept", "PIN": "skipped",
                     "OP": "skipped", "CLOUD": "skipped"}
    assert fake_keychain == {"app/MOVE": b"val-move-1", "BOTH": b"val-old-2",
                             "app/BOTH": b"val-new-3", "shared": b"val-pin-4"}
    assert "val-" not in out


def test_migrate_without_namespace_refuses(tmp_path, monkeypatch, fake_keychain):
    write_manifest(tmp_path, {"A": {}})
    monkeypatch.chdir(tmp_path)
    with pytest.raises(stores.SrunError):
        manage.cmd_migrate([])


# ------------------------------------------------------- real keychain ------ #
@pytest.mark.skipif(sys.platform != "darwin" or not shutil.which("security"),
                    reason="needs the macOS keychain")
def test_keychain_round_trip_add_check_migrate(tmp_path, monkeypatch, capsys):
    tag = f"srtest{os.getpid()}"
    ns, added, moved = tag, f"{tag.upper()}_ADDED", f"{tag.upper()}_MOVED"
    ids = [(added, f"{ns}/{added}"), (moved, moved), (moved, f"{ns}/{moved}")]
    write_manifest(tmp_path, {added: {}, moved: {}}, namespace=ns)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(manage, "read_hidden", lambda n: bytearray(b"dummy-added-71"))
    get = stores.RESOLVERS["keychain"]
    try:
        assert manage.cmd_add([added]) == 0
        stores.store("keychain", moved, moved, bytearray(b"dummy-moved-72"))
        assert manage.cmd_migrate([moved]) == 0
        assert manage.cmd_check([]) == 0
        out = capsys.readouterr().out
        assert f"OK    {added}  (keychain {ns}/{added})" in out
        assert f"OK    {moved}  (keychain {ns}/{moved})" in out
        assert "dummy-" not in out
        with pytest.raises(stores.SrunError):
            get(moved, moved)
        assert get(moved, f"{ns}/{moved}") == bytearray(b"dummy-moved-72")
    finally:
        for name, sid in ids:
            try:
                stores.delete("keychain", name, sid)
            except stores.SrunError:
                pass
