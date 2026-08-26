import pytest

from lib import dockerhub


def test_repo_path_strips_docker_hub_host() -> None:
    assert dockerhub.repo_path("docker.io/stellar/stellar-cli") == "stellar/stellar-cli"
    assert dockerhub.repo_path("index.docker.io/foo/bar") == "foo/bar"
    assert dockerhub.repo_path("registry-1.docker.io/foo/bar") == "foo/bar"


def test_repo_path_leaves_bare_path_untouched() -> None:
    assert dockerhub.repo_path("stellar/stellar-cli") == "stellar/stellar-cli"


def test_list_tags_follows_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = {
        "https://hub.docker.com/v2/repositories/ns/repo/tags?page_size=100": {
            "results": [{"name": "a"}],
            "next": "https://hub.docker.com/v2/repositories/ns/repo/tags?page=2",
        },
        "https://hub.docker.com/v2/repositories/ns/repo/tags?page=2": {
            "results": [{"name": "b"}],
            "next": None,
        },
    }
    monkeypatch.setattr(dockerhub.runner, "http_get_json", lambda url: pages[url])
    assert [tag["name"] for tag in dockerhub.list_tags("ns/repo")] == ["a", "b"]
