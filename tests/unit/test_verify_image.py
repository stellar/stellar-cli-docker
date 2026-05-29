import subprocess

import pytest

import verify_image


def _completed(returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr="")


def test_main_passes_when_both_chains_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(verify_image.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(verify_image.gh_cli, "verify_attestation", lambda *_, **__: _completed(0))
    rc = verify_image.main(
        [
            "--image",
            "docker.io/repo@sha256:" + "a" * 64,
        ]
    )
    assert rc == 0


def test_main_fails_when_provenance_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(verify_image.common, "preflight_checks", lambda _: None)

    def fake(_image, _repo, *, predicate_type):
        if predicate_type == verify_image.PROVENANCE_PREDICATE_TYPE:
            return _completed(1)
        return _completed(0)

    monkeypatch.setattr(verify_image.gh_cli, "verify_attestation", fake)
    rc = verify_image.main(["--image", "docker.io/repo@sha256:" + "a" * 64])
    assert rc == 1
    assert "FAILED" in capsys.readouterr().err


def test_main_fails_when_sbom_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(verify_image.common, "preflight_checks", lambda _: None)

    def fake(_image, _repo, *, predicate_type):
        if predicate_type == verify_image.SBOM_PREDICATE_TYPE:
            return _completed(1)
        return _completed(0)

    monkeypatch.setattr(verify_image.gh_cli, "verify_attestation", fake)
    rc = verify_image.main(["--image", "docker.io/repo@sha256:" + "a" * 64])
    assert rc == 1


def test_main_rejects_tag_only_image(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(verify_image.common, "preflight_checks", lambda _: None)
    with pytest.raises(SystemExit):
        verify_image.main(["--image", "docker.io/repo:latest"])
    assert "pinned to a sha256 digest" in capsys.readouterr().err
