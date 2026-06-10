# Security Policy and reporting a Vulnerability

stellar-cli-docker falls under the Stellar Foundation's bug bounty program.

To report a security problem and review the details of the program, see the [Stellar bug bounty program](https://www.stellar.org/bug-bounty-program/).

## Scope

The artifact this repository produces — the published `stellar/stellar-cli` Docker images — is in scope.

The build and release tooling (`scripts/` and `.github/workflows/`) is **not** in scope. These run only in CI or on a maintainer's machine and never receive untrusted input: every value they act on comes from `builds.json` (changed only via reviewed pull requests), version-pinned GitHub Actions, repository variables/secrets set by admins, or a maintainer's own command-line arguments. The only externally-triggerable workflow requires write access to the repository.

Findings that assume control over a script's arguments or over a repo-controlled file — argument injection, path traversal via path flags, or crashes on malformed input — therefore cross no privilege boundary and are out of scope. A report against this tooling is only considered if it shows genuinely untrusted input (for example, content from an unprivileged fork's pull request) reaching a script with concrete impact on a published image or on the runner's secrets.
