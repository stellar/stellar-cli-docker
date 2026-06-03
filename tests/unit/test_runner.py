import json
import subprocess
from unittest.mock import MagicMock

import pytest

from lib import runner


def test_run_returns_completed_process() -> None:
    result = runner.run(["true"])
    assert result.returncode == 0


def test_run_raises_on_nonzero_when_check_true() -> None:
    with pytest.raises(subprocess.CalledProcessError):
        runner.run(["false"])


def test_run_does_not_raise_when_check_false() -> None:
    result = runner.run(["false"], check=False)
    assert result.returncode != 0


def test_capture_returns_stdout_text() -> None:
    assert runner.capture(["printf", "hello"]) == "hello"


def test_capture_strips_nothing_by_default() -> None:
    assert runner.capture(["printf", "x\ny\n"]) == "x\ny\n"


def test_http_get_json_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"hello": "world"}
    fake_response = MagicMock()
    fake_response.read.return_value = json.dumps(payload).encode()
    fake_response.__enter__.return_value = fake_response
    fake_response.__exit__.return_value = False
    monkeypatch.setattr(runner.urllib.request, "urlopen", lambda *_, **__: fake_response)
    assert runner.http_get_json("https://example.com/foo") == payload


def test_http_get_json_sends_accept_header(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        response = MagicMock()
        response.read.return_value = b'"ok"'
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        return response

    monkeypatch.setattr(runner.urllib.request, "urlopen", fake_urlopen)
    runner.http_get_json("https://example.com/foo")
    request = captured["request"]
    assert request.headers.get("Accept") == "application/json"
