import pytest

import tag_names

# Full 64-hex digest; the tag carries only its first 15 hex chars.
DIGEST = "sha256:f7bf1c266d9e48c8d724733fd97ba60464c44b743eb4f46f935577d3242d81d0"
DIGEST15 = "f7bf1c266d9e48c"
REF = "ee3115b93b9c11b7a4d090f676f35736d3d86172"
REF15 = "ee3115b93b9c11b"


def test_compose_no_platform_no_ref() -> None:
    assert (
        tag_names.compose_tag(
            stellar_cli_version="26.0.0",
            rust_version="1.94.0-slim-trixie",
            rust_image_digest=DIGEST,
        )
        == f"26.0.0-rust1.94.0-slim-trixie-{DIGEST15}"
    )


def test_compose_with_amd64() -> None:
    assert (
        tag_names.compose_tag(
            stellar_cli_version="26.0.0",
            rust_version="1.94.0-slim-trixie",
            rust_image_digest=DIGEST,
            platform="linux/amd64",
        )
        == f"26.0.0-rust1.94.0-slim-trixie-{DIGEST15}-amd64"
    )


def test_compose_with_arm64() -> None:
    assert (
        tag_names.compose_tag(
            stellar_cli_version="26.0.0",
            rust_version="1.94.0-slim-trixie",
            rust_image_digest=DIGEST,
            platform="linux/arm64",
        )
        == f"26.0.0-rust1.94.0-slim-trixie-{DIGEST15}-arm64"
    )


def test_compose_with_ref_only() -> None:
    assert (
        tag_names.compose_tag(
            stellar_cli_version="26.0.0",
            rust_version="1.94.0-slim-trixie",
            rust_image_digest=DIGEST,
            stellar_cli_ref=REF,
        )
        == f"26.0.0-{REF15}-rust1.94.0-slim-trixie-{DIGEST15}"
    )


def test_compose_with_ref_and_platform() -> None:
    assert (
        tag_names.compose_tag(
            stellar_cli_version="26.0.0",
            rust_version="1.94.0-slim-trixie",
            rust_image_digest=DIGEST,
            platform="linux/amd64",
            stellar_cli_ref=REF,
        )
        == f"26.0.0-{REF15}-rust1.94.0-slim-trixie-{DIGEST15}-amd64"
    )


def test_compose_accepts_bare_hex_digest() -> None:
    # The sha256: prefix is optional; truncation is on the hex.
    assert (
        tag_names.compose_tag(
            stellar_cli_version="26.0.0",
            rust_version="1.94.0-slim-trixie",
            rust_image_digest="f7bf1c266d9e48c8d724733fd97ba60464c44b743eb4f46f935577d3242d81d0",
        )
        == f"26.0.0-rust1.94.0-slim-trixie-{DIGEST15}"
    )


def test_compose_rejects_unsupported_platform() -> None:
    with pytest.raises(ValueError, match="unsupported platform"):
        tag_names.compose_tag(
            stellar_cli_version="26.0.0",
            rust_version="1.94.0-slim-trixie",
            rust_image_digest=DIGEST,
            platform="linux/riscv64",
        )


def test_main_prints_tag(capsys: pytest.CaptureFixture[str]) -> None:
    rc = tag_names.main(
        [
            "--stellar-cli-version",
            "26.0.0",
            "--rust-version",
            "1.94.0-slim-trixie",
            "--rust-image-digest",
            DIGEST,
        ]
    )
    assert rc == 0
    assert capsys.readouterr().out == f"26.0.0-rust1.94.0-slim-trixie-{DIGEST15}\n"


def test_main_requires_stellar_cli_version() -> None:
    with pytest.raises(SystemExit):
        tag_names.main(["--rust-version", "1.94.0-slim-trixie", "--rust-image-digest", DIGEST])


def test_main_requires_rust_version() -> None:
    with pytest.raises(SystemExit):
        tag_names.main(["--stellar-cli-version", "26.0.0", "--rust-image-digest", DIGEST])


def test_main_requires_rust_image_digest() -> None:
    with pytest.raises(SystemExit):
        tag_names.main(["--stellar-cli-version", "26.0.0", "--rust-version", "1.94.0-slim-trixie"])
