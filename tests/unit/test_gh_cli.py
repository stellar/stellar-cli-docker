import json
import subprocess
from unittest.mock import MagicMock

import pytest

from lib import gh_cli


def _completed(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout)


def test_list_release_tags_returns_tag_names(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps([{"tagName": "v26.0.0"}, {"tagName": "v26.0.0-1"}])
    monkeypatch.setattr(gh_cli.runner, "capture", lambda _: payload)
    assert gh_cli.list_release_tags("stellar/stellar-cli-docker") == [
        "v26.0.0",
        "v26.0.0-1",
    ]


def test_list_release_tags_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gh_cli.runner, "capture", lambda _: "[]")
    assert gh_cli.list_release_tags("foo/bar") == []


def test_open_pr_for_branch_returns_first_number(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps([{"number": 42}, {"number": 43}])
    monkeypatch.setattr(gh_cli.runner, "capture", lambda _: payload)
    assert gh_cli.open_pr_for_branch("foo/bar", "release/v1") == 42


def test_open_pr_for_branch_none_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gh_cli.runner, "capture", lambda _: "[]")
    assert gh_cli.open_pr_for_branch("foo/bar", "release/v1") is None


def test_verify_attestation_includes_oci_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = MagicMock(return_value=_completed())
    monkeypatch.setattr(gh_cli.runner, "run", captured)
    gh_cli.verify_attestation("docker.io/repo@sha256:abc", "owner/repo")
    args = captured.call_args[0][0]
    assert "oci://docker.io/repo@sha256:abc" in args
    assert "--repo" in args
    assert "owner/repo" in args


def test_verify_attestation_appends_predicate_type(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = MagicMock(return_value=_completed())
    monkeypatch.setattr(gh_cli.runner, "run", captured)
    gh_cli.verify_attestation(
        "docker.io/repo@sha256:abc",
        "owner/repo",
        predicate_type="https://slsa.dev/provenance/v1",
    )
    args = captured.call_args[0][0]
    assert "--predicate-type" in args
    assert "https://slsa.dev/provenance/v1" in args
