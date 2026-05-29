import pytest

from lib import semver


def test_parse_basic() -> None:
    v = semver.parse("1.94.0")
    assert (v.major, v.minor, v.patch) == (1, 94, 0)


def test_parse_two_digit_minor() -> None:
    v = semver.parse("1.100.0")
    assert (v.major, v.minor, v.patch) == (1, 100, 0)


def test_parse_rejects_non_numeric() -> None:
    with pytest.raises(ValueError):
        semver.parse("1.x.0")


def test_sort_numerically_not_lexically() -> None:
    versions = ["1.100.0", "1.9.0", "1.99.0", "1.10.0"]
    assert semver.sort_versions(versions) == ["1.9.0", "1.10.0", "1.99.0", "1.100.0"]


def test_sort_stable_for_equal_keys() -> None:
    assert semver.sort_versions(["1.0.0", "1.0.0"]) == ["1.0.0", "1.0.0"]


def test_sort_empty_input() -> None:
    assert semver.sort_versions([]) == []
