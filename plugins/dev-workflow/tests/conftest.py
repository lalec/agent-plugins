"""Shared setup for the secretrun tests: the folder on sys.path, and every test
isolated from the real keychain-name index and any real .secretrun.json."""
import json
import os
import sys

import pytest

SR_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "shared", "secretrun")
sys.path.insert(0, SR_DIR)


@pytest.fixture(autouse=True)
def _isolate(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("SECRETRUN_HOME", str(tmp_path_factory.mktemp("srhome")))
    monkeypatch.chdir(tmp_path_factory.mktemp("cwd"))


def write_manifest(path, secrets, namespace=None):
    data = {"namespace": namespace} if namespace else {}
    data["secrets"] = secrets
    (path / ".secretrun.json").write_text(json.dumps(data))
