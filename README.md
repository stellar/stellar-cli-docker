# stellar-cli-docker

Docker images for the [Stellar CLI](https://github.com/stellar/stellar-cli).

Also compatible as a [SEP-58](https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0058.md) image image for reproducible Stellar contract builds.

Each image:

- Pins its base via the official `rust:<version>-<suffix>` multi-arch
  index digest. See
  [`RELEASE.md` → Base image policy](./RELEASE.md#base-image-policy) for
  how the version + suffix are chosen per release.
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

The image exposes four well-known paths:

| Path       | What                                                                              |
| ---------- | --------------------------------------------------------------------------------- |
| `/source`  | `WORKDIR`. Bind-mount your contract here.                                         |
| `/config`  | `STELLAR_CONFIG_HOME`. Mount to persist network and identity configuration.       |
| `/data`    | `STELLAR_DATA_HOME`. Mount to persist CLI data.                                   |
| `/stellar` | Home for user `stellar` (UID 1000). Mount to persist the cargo cache (see below). |

The image runs as user `stellar` (UID 1000) with `/stellar` as the home
directory. `CARGO_HOME` resolves to `/stellar/.cargo` inside the
container, which is wiped on exit by default.

To reuse cargo's registry index, git checkouts, and crate sources across
runs — and to make the image work under `--user "$(id -u):$(id -g)"` on
Linux hosts whose UID is not 1000 — mount a writable host directory at
`/stellar`:

```sh
mkdir -p /tmp/myproject
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v /tmp/myproject:/stellar \
  -v "$PWD:/source" \
  docker.io/stellar/stellar-cli:latest contract build --locked
```

## Verifiable builds ([SEP-58](https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0058.md))

For verifiable references, **always pin to a per-arch single-architecture
digest**, never to a moving tag like `:latest` or `:<cli>`, and never to a
multi-arch manifest list digest:

```sh
# Find the per-arch digest for the architecture you used to build.
# Pick any of the immutable manifest-list tags from the release notes,
# e.g. :26.0.0-<ref>-rust1.94.0-slim-trixie, or the :26.0.0 alias:
docker buildx imagetools inspect docker.io/stellar/stellar-cli:26.0.0
```

Record the per-arch digest in your contract's `bldimg` metadata. A verifier
will pull the same per-arch image, run the same `docker run` invocation, and
compare the resulting WASM sha256.

## Repo layout

| Path                                     | What                                                                                                                                                                                              |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Dockerfile`                             | Two-stage builder + runtime, args-driven.                                                                                                                                                         |
| `builds.json`                            | Source of truth for which (stellar-cli, rust base key) pairs we publish.                                                                                                                          |
| `builds.schema.json`                     | JSON Schema for `builds.json`.                                                                                                                                                                    |
| `scripts/build_image.py`                 | Local single-image build.                                                                                                                                                                         |
| `scripts/validate_json.py`               | Validates every `*.json` for sorted keys and `builds.json` for schema + cross-field constraints.                                                                                                  |
| `scripts/refresh_rust_digests.py`        | Fills blank `rust_image_digests` entries by inspecting `rust:<key>` upstream (where `<key>` is the composite `<rust>-<suffix>` form). Does not touch already-pinned digests unless asked per-key. |
| `scripts/refresh_stellar_cli_digests.py` | Fills blank `stellar_cli_versions[].ref` entries by resolving the matching `v<version>` git tag in `stellar/stellar-cli`. Same per-target opt-in shape as the rust refresher.                     |
| `scripts/verify_image.py`                | Consumer-facing verifier. Wraps `gh attestation verify` for both the SLSA build provenance and the SPDX SBOM attestations against a per-arch image digest.                                        |
| `scripts/lib/`                           | Shared Python helpers imported by the other scripts (builds.json IO, semver/key parsing, subprocess + adapter wrappers).                                                                          |

## Local development

```sh
# Validate builds.json.
./scripts/validate_json.py

# Build a local image for a declared (cli, rust base) pair.
./scripts/build_image.py --stellar-cli-version 26.0.0 --rust-version 1.94.0-slim-trixie

# Smoke-test the built image.
docker run --rm stellar-cli:26.0.0-rust1.94.0-slim-trixie --version
docker run --rm stellar-cli:26.0.0-rust1.94.0-slim-trixie contract build --help

# Resolve blank rust base image digests (maintainer task).
./scripts/refresh_rust_digests.py --dry-run

# Resolve blank stellar-cli refs from upstream git tags (maintainer task).
./scripts/refresh_stellar_cli_digests.py --dry-run
```

Requirements: `docker` (with `buildx`) and [`uv`](https://docs.astral.sh/uv/).

## Releasing

Maintainers: see [`RELEASE.md`](./RELEASE.md) for the end-to-end release
process — how `builds.json` works, the PR-driven release flow that fires
the publish workflow when a GitHub Release is published, the tag-
immutability guard, and how to verify a freshly published image.

## License

[Apache-2.0](./LICENSE).
