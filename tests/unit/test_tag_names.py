import pytest

import tag_names


def test_compose_no_platform_no_ref() -> None:
    assert (
        tag_names.compose_tag(stellar_cli_version="26.0.0", rust_version="1.94.0-slim-trixie")
        == "26.0.0-rust1.94.0-slim-trixie"
    )


def test_compose_with_amd64() -> None:
    assert (
        tag_names.compose_tag(
            stellar_cli_version="26.0.0", rust_version="1.94.0-slim-trixie", platform="linux/amd64"
        )
        == "26.0.0-rust1.94.0-slim-trixie-amd64"
    )


def test_compose_with_arm64() -> None:
    assert (
        tag_names.compose_tag(
            stellar_cli_version="26.0.0", rust_version="1.94.0-slim-trixie", platform="linux/arm64"
        )
        == "26.0.0-rust1.94.0-slim-trixie-arm64"
    )


def test_compose_with_ref_only() -> None:
    assert (
        tag_names.compose_tag(
            stellar_cli_version="26.0.0",
            rust_version="1.94.0-slim-trixie",
            stellar_cli_ref="ee3115b93b9c11b7a4d090f676f35736d3d86172",
        )
        == "26.0.0-ee3115b93b9c11b7a4d090f676f35736d3d86172-rust1.94.0-slim-trixie"
    )


def test_compose_with_ref_and_platform() -> None:
    assert (
        tag_names.compose_tag(
            stellar_cli_version="26.0.0",
            rust_version="1.94.0-slim-trixie",
            platform="linux/amd64",
            stellar_cli_ref="ee3115b93b9c11b7a4d090f676f35736d3d86172",
        )
        == "26.0.0-ee3115b93b9c11b7a4d090f676f35736d3d86172-rust1.94.0-slim-trixie-amd64"
    )


def test_compose_plain_suffix() -> None:
    assert (
        tag_names.compose_tag(stellar_cli_version="26.1.0", rust_version="1.94.0-trixie")
        == "26.1.0-rust1.94.0-trixie"
    )


def test_compose_rejects_unsupported_platform() -> None:
    with pytest.raises(ValueError, match="unsupported platform"):
        tag_names.compose_tag(
            stellar_cli_version="26.0.0",
            rust_version="1.94.0-slim-trixie",
            platform="linux/riscv64",
        )


def test_main_prints_tag(capsys: pytest.CaptureFixture[str]) -> None:
    rc = tag_names.main(["--stellar-cli-version", "26.0.0", "--rust-version", "1.94.0-slim-trixie"])
    assert rc == 0
    assert capsys.readouterr().out == "26.0.0-rust1.94.0-slim-trixie\n"


def test_main_requires_stellar_cli_version() -> None:
    with pytest.raises(SystemExit):
        tag_names.main(["--rust-version", "1.94.0-slim-trixie"])


def test_main_requires_rust_version() -> None:
    with pytest.raises(SystemExit):
        tag_names.main(["--stellar-cli-version", "26.0.0"])
