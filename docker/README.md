# Stellar CLI

Docker images for the [Stellar CLI](https://github.com/stellar/stellar-cli).

Also compatible as a
[SEP-58](https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0058.md)
image for reproducible Stellar contract builds.

Each image:

- Pins its base via the official `rust:<version>-<suffix>` multi-arch index
  digest.
- Pins the Rust toolchain via `RUSTUP_TOOLCHAIN`, baked in so an in-source
  `rust-toolchain.toml` cannot silently swap it.
- Pins `stellar-cli` to a specific upstream commit, installed with
  `cargo install --locked`.
- Ships with the `wasm32v1-none` target preinstalled.
- Sets `WORKDIR /source` and `ENTRYPOINT ["stellar"]`.

## Quick start

Pull a published image:

```sh
docker run --rm docker.io/stellar/stellar-cli:latest --version
```

Confirm the rustc version used:

```sh
docker run --rm --entrypoint rustc docker.io/stellar/stellar-cli:latest --version
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
directory. `CARGO_HOME` resolves to `/stellar/.cargo` inside the container,
which is wiped on exit by default.

To reuse cargo's registry index, git checkouts, and crate sources across runs —
and to make the image work under `--user "$(id -u):$(id -g)"` on Linux hosts
whose UID is not 1000 — mount a writable host directory at `/stellar`:

```sh
mkdir -p /tmp/myproject
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v /tmp/myproject:/stellar \
  -v "$PWD:/source" \
  docker.io/stellar/stellar-cli:latest contract build --locked
```

## Verifiable builds ([SEP-58](https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0058.md))

For verifiable references, **always pin to a per-arch single-architecture digest
(`@sha256:…`)** — it is the only stable reference. Never use a tag or a
multi-arch manifest list digest in `bldimg`:

```sh
# List the per-arch digest for each platform behind a tag. Pick any of the
# manifest-list tags from the release notes, e.g. :26.0.0-rust1.94.0-slim-trixie,
# or the :26.0.0 alias:
docker buildx imagetools inspect docker.io/stellar/stellar-cli:26.0.0 \
  --format '{{range .Manifest.Manifests}}{{if and .Platform (ne .Platform.OS "unknown")}}{{.Platform.OS}}/{{.Platform.Architecture}} {{.Digest}}{{println}}{{end}}{{end}}'
```

This prints one line per architecture, e.g.:

```
linux/amd64 sha256:…
linux/arm64 sha256:…
```

Record the `sha256:…` digest for the architecture you built on in your
contract's `bldimg` metadata — not the tag and not the manifest-list digest. A
verifier will pull that same per-arch image, run the same `docker run`
invocation, and compare the resulting WASM sha256.

## Image Tags

- `latest` — most recent release. **Moving** — re-points on every publish.
- `X.Y.Z` — specific release version (e.g. `26.1.0`). **Moving** — re-points on
  every publish (e.g. after a refreshed rust base).
- `<X.Y.Z>-rust<rust image>` — multi-arch manifest list (e.g.
  `26.1.0-rust1.95.0-slim-trixie`). **Mutable** — overwritten if that pair is
  rebuilt in a later refresh.
- `<X.Y.Z>-rust<rust image>-<arch>` — per-arch release (e.g.
  `26.1.0-rust1.95.0-slim-trixie-arm64`). **Mutable** — overwritten on refresh.
- `<X.Y.Z>-rust<rust image>-<arch>-N` — **immutable** per-arch snapshot at
  refresh iteration `N` (`26.1.0-rust1.95.0-slim-trixie-arm64-0` is the first
  publish, `…-1` the next, …). Unlike the mutable per-arch tag, it never
  re-points, so every per-arch digest a past release exposed stays referenced
  and is never garbage-collected — this is the tag that keeps SEP-58 `bldimg`
  pins alive.

## Source

Built from
[stellar/stellar-cli-docker](https://github.com/stellar/stellar-cli-docker).

## License

[Apache-2.0](https://github.com/stellar/stellar-cli-docker/blob/main/LICENSE).
