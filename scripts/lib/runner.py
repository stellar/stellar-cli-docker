"""Subprocess and HTTP wrappers.

Centralises the two non-deterministic surfaces — child processes and
network — so tests can patch one symbol per script.
"""

import json
import subprocess
import urllib.request
from collections.abc import Sequence
from typing import Any

DEFAULT_TIMEOUT = 30.0


def run(
    cmd: Sequence[str],
    *,
    check: bool = True,
    capture_output: bool = False,
    text: bool = True,
    input: str | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(cmd),
        check=check,
        capture_output=capture_output,
        text=text,
        input=input,
        cwd=cwd,
        env=env,
    )


def capture(cmd: Sequence[str], *, check: bool = True) -> str:
    result = run(cmd, check=check, capture_output=True, text=True)
    return result.stdout


def http_get_json(url: str, *, timeout: float = DEFAULT_TIMEOUT) -> Any:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())
