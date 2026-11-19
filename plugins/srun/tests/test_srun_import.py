"""Tests for `srun import` — reading secrets from a dotenv file the way
python-dotenv does, storing them without overwriting, and removing only their
lines once every one is stored. Values never reach the output."""
import json
import os

import pytest
from conftest import write_manifest

import envfile  # noqa: E402
import stores  # noqa: E402

ENV = """# app settings
PUBLIC_URL=https://example.test
export API_KEY=val-key-11 # inline comment
DQ="val-dq-\\"12\\"\\n"
SQ='val sq 13 # not a comment'
LAST=val-last-14
"""


@pytest.fixture
def kc(monkeypatch):
    store = {}

    def get(name, sid):
        if sid not in store:
            raise stores.SrunError(f"not found in keychain: {name}")
        return bytearray(store[sid])

    def put(backend, name, sid, vb):
        store[sid] = bytes(vb)

    monkeypatch.setitem(stores.RESOLVERS, "keychain", get)
    monkeypatch.setattr(envfile, "store", put)
    return store


@pytest.fixture
def project(tmp_path, monkeypatch):
    write_manifest(tmp_path, ["OLD"], namespace="app")
    (tmp_path / ".env").write_text(ENV)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_reads_values_like_python_dotenv(project):
    found, _ = envfile.read_values(".env", ["API_KEY", "DQ", "SQ", "LAST"])
    got = {n: bytes(v) for n, (v, _) in found.items()}
    assert got == {"API_KEY": b"val-key-11", "DQ": b'val-dq-"12"\n',
                   "SQ": b"val sq 13 # not a comment", "LAST": b"val-last-14"}


def test_matches_python_dotenv_when_installed(project):
    dotenv = pytest.importorskip("dotenv")
    want = dotenv.dotenv_values(".env")
    found, _ = envfile.read_values(".env", ["API_KEY", "DQ", "SQ", "LAST"])
    assert {n: bytes(v).decode() for n, (v, _) in found.items()} == \
        {n: want[n] for n in ("API_KEY", "DQ", "SQ", "LAST")}


@pytest.mark.parametrize("text,err", [
    ("K=${OTHER}x\n", "expansion"),
    ('K="line one\nline two"\n', "spans lines"),
    ("K=a\nK=b\n", "more than once"),
    ("K=\n", "empty"),
    ("OTHER=x\n", "not in"),
])
def test_refuses_what_it_cannot_read_for_certain(project, text, err):
    (project / ".env").write_text(text)
    with pytest.raises(stores.SrunError, match=err):
        envfile.read_values(".env", ["K"])


def test_import_stores_lists_and_removes_only_those_lines(project, kc, capsys):
    assert envfile.cmd_import([".env", "API_KEY", "DQ", "--remove"]) == 0
    assert kc == {"app/API_KEY": b"val-key-11", "app/DQ": b'val-dq-"12"\n'}
    left = (project / ".env").read_text()
    assert "API_KEY" not in left and "DQ=" not in left
    assert "PUBLIC_URL=https://example.test" in left and "# app settings" in left
    assert "LAST=val-last-14" in left
    secrets = json.loads((project / ".srun.json").read_text())["secrets"]
    assert secrets == ["OLD", "API_KEY", "DQ"]
    out = capsys.readouterr().out
    assert "stored  API_KEY  (keychain app/API_KEY)" in out
    assert "val-" not in out


def test_import_keeps_file_mode(project, kc):
    os.chmod(project / ".env", 0o600)
    envfile.cmd_import([".env", "LAST", "--remove"])
    assert os.stat(project / ".env").st_mode & 0o777 == 0o600


def test_equal_value_is_kept_and_rerun_is_safe(project, kc, capsys):
    kc["app/API_KEY"] = b"val-key-11"
    assert envfile.cmd_import([".env", "API_KEY"]) == 0
    assert "kept    API_KEY" in capsys.readouterr().out
    assert "API_KEY" in (project / ".env").read_text()          # no --remove


def test_different_value_is_refused_and_nothing_changes(project, kc):
    kc["app/LAST"] = b"other-value"
    before = (project / ".env").read_text()
    with pytest.raises(stores.SrunError, match="different value"):
        envfile.cmd_import([".env", "API_KEY", "LAST", "--remove"])
    assert kc["app/LAST"] == b"other-value"
    assert (project / ".env").read_text() == before


def test_without_manifest_refuses(tmp_path, monkeypatch, kc):
    (tmp_path / ".env").write_text(ENV)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(stores.SrunError, match="srun setup"):
        envfile.cmd_import([".env", "API_KEY"])
    assert kc == {}


def test_remove_refuses_a_link(project, kc):
    (project / "real.env").write_text(ENV)
    os.remove(project / ".env")
    os.symlink(project / "real.env", project / ".env")
    with pytest.raises(stores.SrunError, match="link"):
        envfile.cmd_import([".env", "API_KEY", "--remove"])
