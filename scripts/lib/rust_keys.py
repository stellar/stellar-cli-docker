"""Parse composite rust base keys.

A rust base key is `<version>-<debian-suffix>`, e.g. `1.94.0-trixie`
or `1.94.0-slim-trixie`. Version is always three dotted ints; suffix
is everything after the first dash.
"""

import re
from typing import NamedTuple

_PATTERN = re.compile(r"^(?P<version>[0-9]+\.[0-9]+\.[0-9]+)-(?P<suffix>.+)$")


class RustKey(NamedTuple):
    version: str
    suffix: str


def parse(key: str) -> RustKey:
    match = _PATTERN.match(key)
    if match is None:
        raise ValueError(f"invalid rust base key: {key} (expected <version>-<debian>)")
    return RustKey(version=match["version"], suffix=match["suffix"])


def version_of(key: str) -> str:
    return parse(key).version


def suffix_of(key: str) -> str:
    return parse(key).suffix
