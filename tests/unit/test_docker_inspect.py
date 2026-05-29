import subprocess
from unittest.mock import MagicMock

import pytest

from lib import docker_inspect


def _completed(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout)


def test_index_digest_extracts_from_verbose_output(monkeypatch: pytest.MonkeyPatch) -> None:
    sample = (
        "Name:      docker.io/library/rust:1.94.0-slim-trixie\n"
        "MediaType: application/vnd.oci.image.index.v1+json\n"
        "Digest:    sha256:abc123\n"
        "\n"
        "Manifests:\n"
        "  Name: ...\n"
    )
    monkeypatch.setattr(docker_inspect.runner, "capture", lambda _: sample)
    assert docker_inspect.index_digest("rust:1.94.0-slim-trixie") == "sha256:abc123"


def test_index_digest_raises_when_missing_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docker_inspect.runner, "capture", lambda _: "no digest here\n")
    with pytest.raises(RuntimeError, match="no Digest line"):
        docker_inspect.index_digest("rust:foo")


def test_exists_returns_true_on_zero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docker_inspect.runner, "run", lambda *_, **__: _completed(0))
    assert docker_inspect.exists("repo:tag") is True


def test_exists_returns_false_on_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docker_inspect.runner, "run", lambda *_, **__: _completed(1))
    assert docker_inspect.exists("repo:tag") is False


def test_create_manifest_invokes_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = MagicMock(return_value=_completed())
    monkeypatch.setattr(docker_inspect.runner, "run", captured)
    docker_inspect.create_manifest("tag", "src1", "src2")
    args = captured.call_args[0][0]
    assert args == [
        "docker",
        "buildx",
        "imagetools",
        "create",
        "--tag",
        "tag",
        "src1",
        "src2",
    ]


def test_create_manifest_requires_sources() -> None:
    with pytest.raises(ValueError, match="at least one"):
        docker_inspect.create_manifest("tag")
