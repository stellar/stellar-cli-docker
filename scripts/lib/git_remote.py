"""Adapter around `git ls-remote` for tag-to-commit resolution.

Wraps the one git invocation the refresh scripts depend on so tests
can patch one symbol per script.
"""

from lib import runner


def ls_remote(repo_url: str, *refspecs: str) -> str:
    return runner.capture(["git", "ls-remote", repo_url, *refspecs])


def resolve_tag_commit(repo_url: str, tag: str) -> str | None:
    """Resolve a tag name to the commit SHA it points to.

    For annotated tags, `<tag>^{}` peels to the underlying commit; for
    lightweight tags, the tag ref already IS the commit, so we fall back
    to that. Returns None if neither form matches.
    """
    peeled_ref = f"refs/tags/{tag}^{{}}"
    plain_ref = f"refs/tags/{tag}"
    output = ls_remote(repo_url, peeled_ref, plain_ref)
    peeled: str | None = None
    plain: str | None = None
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        sha, ref = parts[0], parts[1]
        if ref == peeled_ref:
            peeled = sha
        elif ref == plain_ref:
            plain = sha
    return peeled or plain
