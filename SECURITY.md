# Security Policy and Reporting a Vulnerability

stellar-cli-docker falls under the Stellar Development Foundation's bug bounty program.

To report a security problem and review the details of the program, see the [Stellar bug bounty program](https://www.stellar.org/bug-bounty-program/).

## Scope

The artifact this repository produces — the published `stellar/stellar-cli` Docker images — is in scope.

The build and release tooling (`scripts/` and `.github/workflows/`) is **not** in scope. The publishing path that ships images runs only after a reviewed merge or with repository write access, and the values these scripts act on come from `builds.json` (changed only via reviewed pull requests), version-pinned GitHub Actions, repository variables/secrets set by admins, or a maintainer's own command-line arguments.

Findings that assume control over a script's arguments or over a repo-controlled file — argument injection, path traversal via path flags, or crashes on malformed input — therefore cross no privilege boundary and are out of scope.

The `ci.yml` workflow does run on `pull_request`, so an unprivileged fork can have its own checked-out files (such as `builds.json`) processed by scripts like `validate_json.py`. Those runs execute with a read-only token and no repository secrets, and cannot publish or alter an image. A report against this tooling is only considered if it shows such genuinely untrusted input reaching a script with concrete impact on a published image or on the CI runner's secrets.
