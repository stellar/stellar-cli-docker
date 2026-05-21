# Releasing Stellar CLI images

This document covers the maintainer side of `stellar/stellar-cli-docker` — how to publish a new Stellar CLI image and what the publish workflow does on your behalf.

## What gets published

Each release publishes to `docker.io/stellar/stellar-cli`:

- **Per-architecture images** — `:<cli>-rust<rust>-amd64` and `:<cli>-rust<rust>-arm64`. Each one is a single-architecture manifest with its own SHA-256 digest; this is the form a consumer cites in a SEP-58 `bldimg` field.
- **Multi-arch manifest list** per `(cli, rust)` pair — `:<cli>-rust<rust>` resolves to the right per-arch image at pull time.
- **Convenience aliases** — `:<cli>` points at the manifest list for that cli paired with its `default_rust`. `:latest` points at the newest declared cli's default-rust manifest list. **Aliases must never be used in `bldimg`** — they move.
- **Two attestation chains** — buildx-native (SLSA build provenance + SPDX SBOM attached in the registry alongside the image) and GitHub-native (the same predicates signed and stored in the repo's attestation store, verifiable via `gh attestation verify`).
- **A GitHub Release** on `v*` tag push, with per-architecture digests in the body and the SBOM + provenance files attached as downloadable assets.

The single source of truth for which `(cli, rust)` pairs we publish is [`builds.json`](./builds.json). Releases happen one stellar-cli version per workflow run.

## Releasing a new stellar-cli version

1. **Add the entry to `builds.json`.**

   ```json
   {
     "default_rust": "1.94.0",
     "ref": "",
     "rust_versions": ["1.94.0"],
     "version": "26.1.0"
   }
   ```

   Leave `ref` empty; the next step fills it in. List in `rust_versions` every rust version you want to publish images for. `default_rust` must appear in `rust_versions` (validated by `scripts/validate-json.sh`).

   If you're introducing a rust version that doesn't already have an entry in `rust_image_digests`, add it with an empty value:

   ```json
   "rust_image_digests": {
     "1.94.0": ""
   }
   ```

2. **Resolve the upstream commit SHA and base image digest.**

   ```sh
   ./scripts/refresh-stellar-cli-digests.sh
   ./scripts/refresh-rust-digests.sh
   ```

   Both scripts fill blank entries only. Already-pinned values are left alone (re-resolving a pinned value requires `--stellar-cli-version <v>` / `--rust-version <v>` respectively, and is a deliberate, infrequent maintenance task — see _Bumping a pinned base or ref_ below).

3. **Validate locally.**

   ```sh
   ./scripts/validate-json.sh
   ./scripts/build-image.sh --stellar-cli-version 26.1.0 --rust-version 1.94.0
   docker run --rm stellar-cli:26.1.0-rust1.94.0 version --only-version
   ./scripts/smoke-test-image.sh --image stellar-cli:26.1.0-rust1.94.0 \
     --stellar-cli-version 26.1.0 --rust-version 1.94.0
   ./scripts/repro-test.sh --image stellar-cli:26.1.0-rust1.94.0
   ```

   The smoke test confirms the binary reports the expected version and the labels are correct. The repro test confirms `stellar contract build --locked` produces byte-identical WASM across two clean builds.

4. **Open a PR with the `builds.json` change.** The `lint` and `build` workflows run on the PR and re-do steps 3 against the freshly-built image.

5. **Tag the merge commit.** Once the PR lands on `main`:

   ```sh
   git checkout main && git pull
   git tag -a v26.1.0 -m "Release 26.1.0"
   git push origin v26.1.0
   ```

   The `publish` workflow triggers automatically on the tag push.

## What the publish workflow does

Triggered by `v*` tag push, or manually via `workflow_dispatch` (which takes a `stellar_cli_version` input). Each run publishes **exactly one** cli version.

| Job              | What it does                                                                                                                                                                                                                                                                                                                                                                                           |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `matrix`         | Validates `builds.json`, derives the cli version (from the tag name or the dispatch input), then runs `scripts/resolve-matrix.sh --stellar-cli-version <v>` to produce a matrix of `(rust, arch)` rows for that one cli.                                                                                                                                                                               |
| `build` (matrix) | Native runner per arch (`ubuntu-24.04` for amd64, `ubuntu-24.04-arm` for arm64). Refuses to overwrite an existing per-arch tag. Builds + pushes the per-arch image via `docker/build-push-action` with `provenance: mode=max` and `sbom: true`. Then attests with `actions/attest-build-provenance` and `actions/attest-sbom`. Uploads SBOM + provenance bundle + metadata JSON as workflow artifacts. |
| `manifest`       | Assembles the multi-arch manifest list `:<cli>-rust<rust>` per rust version, combining the already-pushed per-arch tags via `docker buildx imagetools create`. Refuses to overwrite an existing list.                                                                                                                                                                                                  |
| `aliases`        | Re-points `:<cli>` to the manifest list of `(cli, default_rust)`. If this cli is the newest declared, also re-points `:latest`. Aliases are intentionally moving.                                                                                                                                                                                                                                      |
| `release`        | Only on `v*` tag push. Downloads the per-arch artifacts uploaded by the build job, calls `scripts/release-body.sh` to compose the release body, creates / updates the GitHub Release with the SBOM and provenance files attached.                                                                                                                                                                      |
| `complete`       | Branch-protection aggregator. Fails if any upstream job failed or was cancelled.                                                                                                                                                                                                                                                                                                                       |

## Tag immutability and restarts

Per-architecture tags (`:<cli>-rust<rust>-<arch>`) and per-pair manifest lists (`:<cli>-rust<rust>`) are **immutable**. The publish workflow checks `docker buildx imagetools inspect` before each push and aborts the job loudly if the target tag already exists. There is **no force flag** and no workflow input to override this — the trust property the whole repo rests on is that a tag means the same content forever.

Moving aliases (`:<cli>`, `:latest`) are exempt; they're documented as moving and re-pointed each release.

To recover from a failed run, use **Re-run failed jobs** from the GitHub Actions UI. Already-successful jobs aren't re-run, so the existence check never fires on tags that published cleanly the first time.

To genuinely re-publish a content-immutable tag (e.g. recovering from a corrupt push), delete the offending tag in Docker Hub by hand first, then re-run the workflow.

## Bumping a pinned base or ref

Pinned values in `builds.json` are intentional. Bumping them changes the bytes of published images and invalidates anything that already referenced the prior digest, so it's a deliberate action.

```sh
./scripts/refresh-rust-digests.sh --rust-version 1.94.0
./scripts/refresh-stellar-cli-digests.sh --stellar-cli-version 26.1.0
```

Both target-specific commands skip the blank-only check and re-resolve from upstream. Commit the resulting `builds.json` change and run the release flow as if it were a new release — the immutability guard will refuse to overwrite already-published tags, so you also need to delete those tags from Docker Hub first (or bump the cli version, the cleaner option).

## Verifying a freshly published release

After a `v*` tag publish succeeds, sanity-check the attestations:

```sh
# Extract a per-arch digest:
docker buildx imagetools inspect docker.io/stellar/stellar-cli:26.1.0-rust1.94.0-amd64

# Verify both attestation chains in one command:
./scripts/verify-image.sh --image docker.io/stellar/stellar-cli@sha256:<digest>
```

Or directly:

```sh
gh attestation verify oci://docker.io/stellar/stellar-cli@sha256:<digest> \
  --repo stellar/stellar-cli-docker
cosign verify-attestation --type slsaprovenance \
  docker.io/stellar/stellar-cli@sha256:<digest>
```

Both attestation chains have the same trust root (the runner's GitHub Actions OIDC identity); they differ only in verification UX.

## Adding a rust version to an already-released stellar-cli

If you need to pair an existing cli release with an additional rust toolchain (e.g. to pick up a Rust security release without bumping the cli):

1. Add the new rust to that cli entry's `rust_versions` array in `builds.json`.
2. Resolve the rust digest if needed (`./scripts/refresh-rust-digests.sh`).
3. PR, merge.
4. Trigger the publish workflow manually via `workflow_dispatch`, passing the existing cli version as `stellar_cli_version`.

The matrix will include both the already-published pairs and the new ones. The immutability guard refuses to overwrite the already-published per-arch tags, so the `build` job fails on those rows — by design. To make progress, on Docker Hub delete by hand the per-arch tags and manifest list for each already-published `(cli, existing-rust)` pair, then re-run the failed jobs. The new `(cli, new-rust)` rows publish cleanly because their tags didn't exist yet.

This is friction-heavy. In practice it's almost always cleaner to roll the cli minor version forward than to retro-pair an existing cli with a newer toolchain.
