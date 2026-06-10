from pathlib import Path

import pytest

import repro_test


def test_clone_rejects_option_like_rev(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # The classic argument-injection vector: --rev '--upload-pack=<cmd>'.
    monkeypatch.setattr(repro_test.runner, "run", lambda *_, **__: pytest.fail("ran git"))
    with pytest.raises(ValueError, match="must not begin with '-'"):
        repro_test.clone("https://example.com/repo.git", "--upload-pack=touch /tmp/x", tmp_path)


def test_clone_rejects_option_like_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(repro_test.runner, "run", lambda *_, **__: pytest.fail("ran git"))
    with pytest.raises(ValueError, match="must not begin with '-'"):
        repro_test.clone("--config=core.foo=bar", "main", tmp_path)


def test_clone_fetch_pins_end_of_options(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cmds: list[list[str]] = []
    monkeypatch.setattr(repro_test.runner, "run", lambda cmd, **__: cmds.append(cmd))
    repro_test.clone("https://example.com/repo.git", "main", tmp_path)
    fetch = next(c for c in cmds if "fetch" in c)
    assert "--end-of-options" in fetch
    # rev sits after --end-of-options, so it can never be parsed as a flag.
    assert fetch.index("--end-of-options") < fetch.index("main")


def test_assert_sha256_accepts_valid() -> None:
    assert repro_test.assert_sha256("a" * 64, "build A") is True


def test_assert_sha256_rejects_short() -> None:
    assert repro_test.assert_sha256("abc", "build A") is False


def test_assert_sha256_rejects_uppercase() -> None:
    assert repro_test.assert_sha256("A" * 64, "build A") is False


def test_assert_sha256_rejects_non_hex() -> None:
    assert repro_test.assert_sha256("g" * 64, "build A") is False


def test_test_one_contract_passes_when_hashes_match(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    contract = tmp_path / "token"
    contract.mkdir()
    (contract / "Cargo.toml").write_text("[package]\n")
    (contract / "Cargo.lock").write_text("")
    monkeypatch.setattr(repro_test, "build_and_hash", lambda *_: "a" * 64)
    assert repro_test.test_one_contract("img", tmp_path, "token") is True


def test_test_one_contract_fails_when_hashes_differ(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    contract = tmp_path / "token"
    contract.mkdir()
    (contract / "Cargo.toml").write_text("[package]\n")
    (contract / "Cargo.lock").write_text("")
    counter = iter(["a" * 64, "b" * 64])
    monkeypatch.setattr(repro_test, "build_and_hash", lambda *_: next(counter))
    assert repro_test.test_one_contract("img", tmp_path, "token") is False
    assert "NOT reproducible" in capsys.readouterr().err


def test_test_one_contract_missing_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert repro_test.test_one_contract("img", tmp_path, "nope") is False
    assert "no contract directory" in capsys.readouterr().err


def test_test_one_contract_missing_cargo_lock(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    contract = tmp_path / "token"
    contract.mkdir()
    (contract / "Cargo.toml").write_text("[package]\n")
    assert repro_test.test_one_contract("img", tmp_path, "token") is False
    assert "Cargo.lock missing" in capsys.readouterr().err
