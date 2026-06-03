import subprocess
from unittest.mock import MagicMock

import pytest

from lib import docker_inspect


def _completed(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout)


_INDEX = "sha256:" + "a" * 64


def test_index_digest_uses_manifest_digest_format(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[list[str]] = []

    def fake_capture(cmd: list[str]) -> str:
        captured.append(cmd)
        return f"{_INDEX}\n"

    monkeypatch.setattr(docker_inspect.runner, "capture", fake_capture)
    assert docker_inspect.index_digest("rust:1.94.0-slim-trixie") == _INDEX
    assert captured[0][-2:] == ["--format", "{{.Manifest.Digest}}"]


def test_index_digest_extracts_from_struct_dump(monkeypatch: pytest.MonkeyPatch) -> None:
    # Some buildx releases print the whole descriptor rather than the bare
    # digest; the descriptor still carries only the single index digest.
    dump = f"{{application/vnd.oci.image.index.v1+json {_INDEX} 1234 [] map[] [] <nil> <nil>}}\n"
    monkeypatch.setattr(docker_inspect.runner, "capture", lambda _: dump)
    assert docker_inspect.index_digest("rust:1.94.0-slim-trixie") == _INDEX


def test_index_digest_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docker_inspect.runner, "capture", lambda _: "no digest here\n")
    with pytest.raises(RuntimeError, match="no digest"):
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
