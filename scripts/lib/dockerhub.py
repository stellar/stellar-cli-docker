"""Read a repo's current tag state from the Docker Hub HTTP API.

The OCI registry API only ever lists *tags* — it has no way to enumerate
untagged (orphaned) manifests. So a repo's live tags are the only place the
per-arch content digests still exposed today can be discovered, which is what
the backfill needs to protect them before a later publish orphans them.

Addressed by `<namespace>/<repo>` (no registry host), e.g. `stellar/stellar-cli`.
Public repos read anonymously.
"""

from typing import Any

from lib import runner

_HUB = "https://hub.docker.com/v2"
_PAGE_SIZE = 100


def repo_path(registry: str) -> str:
    """Namespace/repo for the Hub API from a full registry ref.

    `docker.io/stellar/stellar-cli` -> `stellar/stellar-cli`. Docker Hub's HTTP
    API is keyed by `<namespace>/<repo>` without the registry host, so strip a
    leading Docker Hub host if present; anything else is assumed already bare.
    """
    for host in ("docker.io/", "registry-1.docker.io/", "index.docker.io/"):
        if registry.startswith(host):
            return registry[len(host) :]
    return registry


def list_tags(repo_path: str) -> list[dict[str, Any]]:
    """Every tag object on the repo, following pagination to the last page.

    Each item is the Hub API tag record; callers read `name` and the per-arch
    `images[]` entries (`architecture`, `os`, `digest`).
    """
    tags: list[dict[str, Any]] = []
    url: str | None = f"{_HUB}/repositories/{repo_path}/tags?page_size={_PAGE_SIZE}"
    while url:
        page = runner.http_get_json(url)
        tags.extend(page.get("results", []))
        url = page.get("next")
    return tags
