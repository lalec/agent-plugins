"""Tests for srun namespacing and setup — namespaced store ids, `setup` writing
the namespace once and the Secrets rule into CLAUDE.md, and `migrate` moving
keychain values off the bare NAME."""
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
import setup  # noqa: E402

M = manifest.Manifest


# ------------------------------------------------------------------ plan ---- #
@pytest.mark.parametrize("store,sid", [
    ("keychain", "app/K"), ("aws", "app/K"), ("gcp", "app_K"), ("1password", "app/K"),
    ("dashlane", "app/K"), ("lastpass", "app/K")])
def test_plan_namespaces_ids_per_store(store, sid):
    m = M({"K": {"store": store}}, "app")
    assert manifest.plan("K", None, m) == (store, sid)
    assert manifest.plan("X", store, M({}, "app"))[1] == sid.replace("K", "X")


def test_plan_explicit_id_wins():
    m = M({"S": {"store": "aws", "id": "shared/s"}}, "app")
    assert manifest.plan("S", None, m) == ("aws", "shared/s")


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


# ----------------------------------------------------------------- setup ---- #
def _git_repo(tmp_path, name):
    root = tmp_path / name
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def _read(root):
    return json.loads((root / ".srun.json").read_text())


def test_setup_creates_manifest_with_namespace_once(tmp_path, monkeypatch, capsys):
    root = _git_repo(tmp_path, "my.app")
    monkeypatch.chdir(root)
    assert setup.setup([]) == 0
    assert _read(root) == {"namespace": "my-app", "secrets": []}
    assert '"namespace": "my-app"' in capsys.readouterr().out
    before = (root / ".srun.json").read_bytes()
    assert setup.setup([]) == 0
    assert (root / ".srun.json").read_bytes() == before
    out = capsys.readouterr().out
    assert "is current" in out and "Commit" not in out


def test_setup_keeps_overrides_and_never_rewrites_the_namespace(tmp_path, monkeypatch):
    root = _git_repo(tmp_path, "web")
    write_manifest(root, {"A": {"backend": "aws", "id": "x"}, "B": {}})
    monkeypatch.chdir(root)
    setup.setup([])
    assert _read(root) == {"namespace": "web", "secrets": {"A": {"store": "aws", "id": "x"},
                                                           "B": {}}}
    write_manifest(root, {}, namespace="chosen")
    setup.setup([])
    assert _read(root)["namespace"] == "chosen"


@pytest.mark.parametrize("secrets,want", [
    ({"A": {"backend": "keychain"}, "B": {"backend": "keychain"}},
     {"store": "keychain", "secrets": ["A", "B"]}),
    ({"A": {}, "B": {"backend": "aws"}}, {"secrets": {"A": {}, "B": {"store": "aws"}}}),
    ({"A": {"backend": "aws"}, "C": {"cmd": "op read x"}},     # an old cmd is dropped
     {"secrets": {"A": {"store": "aws"}, "C": {}}}),
    (["A", "B"], {"secrets": ["A", "B"]}),
])
def test_setup_rewrites_old_manifests_in_the_short_form(tmp_path, monkeypatch, secrets, want):
    root = _git_repo(tmp_path, "p")
    write_manifest(root, secrets, namespace="p")
    monkeypatch.chdir(root)
    setup.setup([])
    assert _read(root) == {"namespace": "p", **want}
    before = (root / ".srun.json").read_bytes()
    setup.setup([])
    assert (root / ".srun.json").read_bytes() == before


def test_setup_store_sets_the_project_store(tmp_path, monkeypatch):
    root = _git_repo(tmp_path, "p")
    write_manifest(root, {"A": {"backend": "1password"}, "B": {}}, namespace="p")
    monkeypatch.chdir(root)
    assert setup.setup(["--store", "1password"]) == 0
    assert _read(root) == {"namespace": "p", "store": "1password", "secrets": ["A", "B"]}
    assert setup.setup(["--store", "vault"]) == 1
    assert setup.setup(["--store"]) == 1


def _rule():
    with open(setup.RULE) as f:
        return f.read().strip()


def test_setup_creates_or_appends_the_rule(tmp_path):
    md = tmp_path / "CLAUDE.md"
    assert setup.upsert_rule(str(md)) == "added"
    assert md.read_text().strip() == _rule()
    md.write_text("# Proj\n\n## Agents\n\ntext\n")
    assert setup.upsert_rule(str(md)) == "added"
    assert md.read_text() == "# Proj\n\n## Agents\n\ntext\n\n" + _rule() + "\n"
    assert setup.upsert_rule(str(md)) is None


def test_setup_replaces_an_older_rule_and_keeps_neighbours(tmp_path):
    md = tmp_path / "CLAUDE.md"
    md.write_text("# P\n\n## Secrets\n\nold rule\n\n## Roadmap\n\nkeep\n")
    assert setup.upsert_rule(str(md)) == "updated"
    text = md.read_text()
    assert "old rule" not in text and text.count("## Secrets") == 1
    assert text.startswith("# P\n\n" + _rule() + "\n\n## Roadmap\n\nkeep\n")


def test_setup_ignores_a_committed_tmp_symlink(tmp_path, monkeypatch):
    root = _git_repo(tmp_path, "p")
    victim = tmp_path / "victim"
    victim.write_text("keep\n")
    write_manifest(root, ["A"])                         # no namespace: forces a rewrite
    (root / ".srun.json").chmod(0o640)
    (root / ".srun.json.tmp").symlink_to(victim)
    monkeypatch.chdir(root)
    assert setup.setup([]) == 0
    assert victim.read_text() == "keep\n"
    assert _read(root)["namespace"] == "p"
    assert (root / ".srun.json").stat().st_mode & 0o777 == 0o640
    assert [p.name for p in root.iterdir() if p.name.startswith(".srun-")] == []


def test_setup_writes_through_a_claude_md_link_inside_the_project(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# A\n")
    (tmp_path / "CLAUDE.md").symlink_to("AGENTS.md")
    assert setup.upsert_rule(str(tmp_path / "CLAUDE.md")) == "added"
    assert (tmp_path / "CLAUDE.md").is_symlink()
    assert _rule() in (tmp_path / "AGENTS.md").read_text()


def test_setup_refuses_a_claude_md_link_out_of_the_project(tmp_path, monkeypatch, capsys):
    root = _git_repo(tmp_path, "p")
    victim = tmp_path / "victim"
    victim.write_text("keep\n")
    (root / "CLAUDE.md").symlink_to(victim)
    monkeypatch.chdir(root)
    assert setup.setup([]) == 1
    assert victim.read_text() == "keep\n"
    assert not (root / ".srun.json").exists()          # refused before any write
    assert "refusing" in capsys.readouterr().out


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
                              "CLOUD": {"store": "aws"}},
                   namespace="app")
    fake_keychain.update({"MOVE": b"val-move-1", "BOTH": b"val-old-2",
                          "app/BOTH": b"val-new-3", "shared": b"val-pin-4"})
    monkeypatch.chdir(tmp_path)
    assert manage.cmd_migrate([]) == 0
    out = capsys.readouterr().out
    lines = {ln[12:].split()[0]: ln[:10].strip() for ln in out.splitlines()}
    assert lines == {"MOVE": "moved", "GONE": "not stored", "BOTH": "kept", "PIN": "skipped",
                     "CLOUD": "skipped"}
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
