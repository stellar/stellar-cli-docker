# stellar-cli-docker

Docker images for the [Stellar CLI](https://github.com/stellar/stellar-cli).

Also compatible as a [SEP-58](https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0058.md) image image for reproducible Stellar contract builds.

Each image:

- Pins its Debian base via the official `rust:<version>-slim-bookworm`
  multi-arch index digest.
- Pins the Rust toolchain via `RUSTUP_TOOLCHAIN`, baked in so an in-source
  `rust-toolchain.toml` cannot silently swap it.
- Pins `stellar-cli` to a specific upstream commit, installed with
  `cargo install --locked`.
- Ships with the `wasm32v1-none` target preinstalled.
- Sets `WORKDIR /source` and `ENTRYPOINT ["stellar"]`.

## Quick start

Pull a published image (per-host arch):

```sh
docker run --rm docker.io/stellar/stellar-cli:latest --version
```

Build a contract by mounting the contract directory at `/source`:

```sh
docker run --rm -v "$PWD:/source" docker.io/stellar/stellar-cli:latest contract build --locked
```

## Verifiable builds ([SEP-58](https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0058.md))

For verifiable references, **always pin to a per-arch single-architecture
digest**, never to a moving tag like `:latest` or to a multi-arch manifest
list digest:

```sh
# Find the per-arch digest for the architecture you used to build:
docker buildx imagetools inspect docker.io/stellar/stellar-cli:26.0.0-rust1.94.0
```

Record the per-arch digest in your contract's `bldimg` metadata. A verifier
will pull the same per-arch image, run the same `docker run` invocation, and
compare the resulting WASM sha256.

## Repo layout

| Path                                     | What                                                                                                                                                                          |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Dockerfile`                             | Two-stage builder + runtime, args-driven.                                                                                                                                     |
| `builds.json`                            | Source of truth for which (stellar-cli, rust) pairs we publish.                                                                                                               |
| `builds.schema.json`                     | JSON Schema for `builds.json`.                                                                                                                                                |
| `scripts/build-image.sh`                 | Local single-image build.                                                                                                                                                     |
| `scripts/validate-json.sh`               | Validates every `*.json` for sorted keys and `builds.json` for schema + cross-field constraints.                                                                              |
| `scripts/refresh-rust-digests.sh`        | Fills blank `rust_image_digests` entries by inspecting `rust:<v>-slim-bookworm` upstream. Does not touch already-pinned digests unless asked per-version.                     |
| `scripts/refresh-stellar-cli-digests.sh` | Fills blank `stellar_cli_versions[].ref` entries by resolving the matching `v<version>` git tag in `stellar/stellar-cli`. Same per-target opt-in shape as the rust refresher. |
| `scripts/verify-image.sh`                | Consumer-facing verifier. Wraps `gh attestation verify` for both the SLSA build provenance and the SPDX SBOM attestations against a per-arch image digest.                    |
| `scripts/lib/common.sh`                  | Shared helpers sourced by the other scripts.                                                                                                                                  |

## Local development

```sh
# Validate builds.json.
./scripts/validate-json.sh

# Build a local image for a declared (cli, rust) pair.
./scripts/build-image.sh --stellar-cli-version 26.0.0 --rust-version 1.94.0

# Smoke-test the built image.
docker run --rm stellar-cli:26.0.0-rust1.94.0 --version
docker run --rm stellar-cli:26.0.0-rust1.94.0 contract build --help

# Resolve blank rust base image digests (maintainer task).
./scripts/refresh-rust-digests.sh --dry-run

# Resolve blank stellar-cli refs from upstream git tags (maintainer task).
./scripts/refresh-stellar-cli-digests.sh --dry-run
```

Requirements: `docker` (with `buildx`), `jq`, `check-jsonschema` (pip /
pipx install).

## License

[Apache-2.0](./LICENSE).
