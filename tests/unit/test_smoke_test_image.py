import json
import subprocess

import pytest

import smoke_test_image


def _completed(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout)


def test_check_version_output_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smoke_test_image.runner, "capture", lambda _: "26.0.0\n")
    assert smoke_test_image.check_version_output("img", "26.0.0") is True


def test_check_version_output_mismatch(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(smoke_test_image.runner, "capture", lambda _: "26.0.1\n")
    assert smoke_test_image.check_version_output("img", "26.0.0") is False
    assert "version mismatch" in capsys.readouterr().err


def test_check_contract_build_help_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smoke_test_image.runner, "run", lambda *_, **__: _completed(0))
    assert smoke_test_image.check_contract_build_help("img") is True


def test_check_contract_build_help_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smoke_test_image.runner, "run", lambda *_, **__: _completed(1))
    assert smoke_test_image.check_contract_build_help("img") is False


def test_check_labels_all_match(monkeypatch: pytest.MonkeyPatch) -> None:
    labels = {
        "org.opencontainers.image.version": "26.0.0",
        "org.opencontainers.image.revision": "abc123",
        "org.opencontainers.image.base.name": "docker.io/library/rust:1.94.0-slim-trixie",
        "org.opencontainers.image.base.digest": "sha256:def",
    }
    monkeypatch.setattr(smoke_test_image.runner, "capture", lambda _: json.dumps(labels))
    assert (
        smoke_test_image.check_labels(
            "img",
            cli="26.0.0",
            stellar_ref="abc123",
            rust_version="1.94.0",
            rust_base_suffix="slim-trixie",
            rust_image_digest="sha256:def",
        )
        is True
    )


def test_check_labels_detects_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    labels = {
        "org.opencontainers.image.version": "26.0.0",
        # missing revision
        "org.opencontainers.image.base.name": "docker.io/library/rust:1.94.0-slim-trixie",
        "org.opencontainers.image.base.digest": "sha256:def",
    }
    monkeypatch.setattr(smoke_test_image.runner, "capture", lambda _: json.dumps(labels))
    assert (
        smoke_test_image.check_labels(
            "img",
            cli="26.0.0",
            stellar_ref="abc123",
            rust_version="1.94.0",
            rust_base_suffix="slim-trixie",
            rust_image_digest="sha256:def",
        )
        is False
    )
    assert "revision" in capsys.readouterr().err


def test_main_threads_pinned_digest(monkeypatch: pytest.MonkeyPatch, minimal_builds: dict) -> None:
    monkeypatch.setattr(smoke_test_image.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(smoke_test_image.builds, "load", lambda: minimal_builds)
    monkeypatch.setattr(smoke_test_image, "check_version_output", lambda *a, **k: True)
    monkeypatch.setattr(smoke_test_image, "check_contract_build_help", lambda *a, **k: True)
    seen = {}
    monkeypatch.setattr(
        smoke_test_image,
        "check_labels",
        lambda image, **kwargs: seen.update(kwargs) or True,
    )

    rc = smoke_test_image.main(
        [
            "--image",
            "img",
            "--stellar-cli-version",
            "26.0.0",
            "--rust-version",
            "1.94.0-slim-trixie",
            "--rust-image-digest",
            "sha256:" + "a" * 64,
        ]
    )
    assert rc == 0
    assert seen["rust_image_digest"] == "sha256:" + "a" * 64
    assert seen["rust_version"] == "1.94.0"
    assert seen["rust_base_suffix"] == "slim-trixie"


def test_main_rejects_option_like_image(
    monkeypatch: pytest.MonkeyPatch, minimal_builds: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(smoke_test_image.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(smoke_test_image.builds, "load", lambda: minimal_builds)
    # No docker check should run; an image of '--privileged' would be parsed as
    # a docker flag, so main() must die before reaching any runner call.
    monkeypatch.setattr(
        smoke_test_image.runner, "capture", lambda *_, **__: pytest.fail("ran docker")
    )
    monkeypatch.setattr(smoke_test_image.runner, "run", lambda *_, **__: pytest.fail("ran docker"))
    with pytest.raises(SystemExit):
        smoke_test_image.main(
            [
                "--image=--privileged",  # single token: argparse accepts the '--privileged' value
                "--stellar-cli-version",
                "26.0.0",
                "--rust-version",
                "1.94.0-slim-trixie",
                "--rust-image-digest",
                "sha256:" + "a" * 64,
            ]
        )
    assert "must not begin with '-'" in capsys.readouterr().err


def test_check_labels_detects_drifted_digest(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    labels = {
        "org.opencontainers.image.version": "26.0.0",
        "org.opencontainers.image.revision": "abc123",
        "org.opencontainers.image.base.name": "docker.io/library/rust:1.94.0-slim-trixie",
        "org.opencontainers.image.base.digest": "sha256:WRONG",
    }
    monkeypatch.setattr(smoke_test_image.runner, "capture", lambda _: json.dumps(labels))
    assert (
        smoke_test_image.check_labels(
            "img",
            cli="26.0.0",
            stellar_ref="abc123",
            rust_version="1.94.0",
            rust_base_suffix="slim-trixie",
            rust_image_digest="sha256:def",
        )
        is False
    )
    assert "base.digest" in capsys.readouterr().err
