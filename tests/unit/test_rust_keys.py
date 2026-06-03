import pytest

from lib import rust_keys


def test_parse_plain_suffix() -> None:
    assert rust_keys.parse("1.94.0-trixie") == ("1.94.0", "trixie")


def test_parse_compound_suffix() -> None:
    assert rust_keys.parse("1.94.0-slim-trixie") == ("1.94.0", "slim-trixie")


def test_parse_two_digit_minor() -> None:
    assert rust_keys.parse("1.100.0-slim-bookworm") == ("1.100.0", "slim-bookworm")


def test_version_of_helper() -> None:
    assert rust_keys.version_of("1.94.0-slim-trixie") == "1.94.0"


def test_suffix_of_helper() -> None:
    assert rust_keys.suffix_of("1.94.0-slim-trixie") == "slim-trixie"


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "1.94-trixie",  # missing patch
        "1.94.0",  # no suffix
        "1.94.0-",  # empty suffix
        "rust-trixie",  # non-numeric version
        "-trixie",  # missing version
    ],
)
def test_parse_rejects_malformed(bad: str) -> None:
    with pytest.raises(ValueError):
        rust_keys.parse(bad)
