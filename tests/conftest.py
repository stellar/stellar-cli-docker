from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def minimal_builds() -> dict:
    import json

    return json.loads((FIXTURES_DIR / "builds_minimal.json").read_text())


@pytest.fixture
def multi_cli_builds() -> dict:
    import json

    return json.loads((FIXTURES_DIR / "builds_multi_cli.json").read_text())
