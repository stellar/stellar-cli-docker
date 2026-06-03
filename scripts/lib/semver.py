"""Numeric semver parsing and sorting.

Wraps the `semver` package so callers in this project share one
import path. String sort would invert e.g. `1.100.0` and `1.99.0`,
so always go through `parse` or `sort_versions`.
"""

from collections.abc import Iterable

from semver import Version


def parse(version: str) -> Version:
    return Version.parse(version)


def sort_versions(versions: Iterable[str]) -> list[str]:
    return sorted(versions, key=parse)
