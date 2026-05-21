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

The release is a four-step flow, with PR review as the gate and a GitHub Release as the publish trigger. No manual tag pushes.

1. **Trigger the `release` workflow** from the Actions UI with the stellar-cli version (e.g. `26.1.0`). The workflow:

   - Resolves the upstream `stellar/stellar-cli` commit SHA for `v<version>`.
   - Picks the last two minor stable rust versions, at their latest patch each, from `rust-lang/rust` GitHub releases. The newer one becomes `default_rust`.
   - Updates `builds.json` with the new entry and any missing `rust_image_digests` keys (resolved via the same scripts you'd run locally).
   - Validates the result.
   - Pushes a `release/v<version>` branch and opens a PR with a body modeled on stellar-cli's release PRs — including a pre-filled link to create the GitHub Release on merge.

2. **Review and adjust** the PR. The auto-pick of rust versions is a sensible default but not always right; if you want different `rust_versions` for this release, push commits to the `release/v<version>` branch before merging (re-run `./scripts/validate-json.sh` locally to confirm the result is still valid). The PR-time `lint` and `build` workflows re-do validation and smoke-build on every push.

3. **Merge the PR** once approved. `builds.json` now declares the new release.

4. **Publish the release** by following the `Create release` link in the PR body. That opens `Releases → New release` with the tag pre-filled (`v<version>`); add notes (or use `Generate release notes`), then **Publish release**.

   The `publish` workflow fires on the `release: published` event and:

   - Builds and pushes per-arch images for each declared `(cli, rust)` pair.
   - Generates SLSA build provenance + SPDX SBOM attestations on each per-arch image (buildx-native + GitHub-native chains).
   - Updates the GitHub Release: appends per-architecture digests and verification commands to the body (existing notes are preserved), attaches the SBOM and provenance files as downloadable assets.

### Manual / local prepare

If you'd rather run the prepare step yourself (e.g. to debug an auto-pick that's failing), do it locally:

```sh
./scripts/release-prepare.sh --stellar-cli-version 26.1.0
# Optional: pin specific rust versions instead of the auto-pick
./scripts/release-prepare.sh --stellar-cli-version 26.1.0 --rust-versions 1.93.0,1.94.0
```

Then commit and push the resulting `builds.json` change yourself, open the PR, and continue from step 3 above.

### Validating locally before pushing

```sh
./scripts/validate-json.sh
./scripts/build-image.sh --stellar-cli-version 26.1.0 --rust-version 1.95.0
./scripts/smoke-test-image.sh --image stellar-cli:26.1.0-rust1.95.0 \
  --stellar-cli-version 26.1.0 --rust-version 1.95.0
./scripts/repro-test.sh --image stellar-cli:26.1.0-rust1.95.0
```

The smoke test confirms the binary reports the expected version and the labels are correct. The repro test confirms `stellar contract build --locked` produces byte-identical WASM across two clean builds. CI does the same against the freshly-built image on every PR push.

## What the publish workflow does

Triggered by the `release: published` event (i.e. when a maintainer clicks **Publish release** in the GitHub UI for a `v<version>` tag), or manually via `workflow_dispatch` (which takes a `stellar_cli_version` input). Each run publishes **exactly one** cli version.

| Job              | What it does                                                                                                                                                                                                                                                                                                                                                                                           |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `matrix`         | Validates `builds.json`, derives the cli version (from the release's tag name or the dispatch input), then runs `scripts/resolve-matrix.sh --stellar-cli-version <v>` to produce a matrix of `(rust, arch)` rows for that one cli.                                                                                                                                                                     |
| `build` (matrix) | Native runner per arch (`ubuntu-24.04` for amd64, `ubuntu-24.04-arm` for arm64). Refuses to overwrite an existing per-arch tag. Builds + pushes the per-arch image via `docker/build-push-action` with `provenance: mode=max` and `sbom: true`. Then attests with `actions/attest-build-provenance` and `actions/attest-sbom`. Uploads SBOM + provenance bundle + metadata JSON as workflow artifacts. |
| `manifest`       | Assembles the multi-arch manifest list `:<cli>-rust<rust>` per rust version, combining the already-pushed per-arch tags via `docker buildx imagetools create`. Refuses to overwrite an existing list.                                                                                                                                                                                                  |
| `aliases`        | Re-points `:<cli>` to the manifest list of `(cli, default_rust)`. If this cli is the newest declared, also re-points `:latest`. Aliases are intentionally moving.                                                                                                                                                                                                                                      |
| `release`        | Only on the `release: published` event (skipped on `workflow_dispatch`). Downloads the per-arch artifacts uploaded by the build job, calls `scripts/release-body.sh` to compose a structural body section, then **appends** that section to the existing release body and attaches the SBOM + provenance files. Any human-written notes already in the release body are preserved.                    |
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

After a release publish succeeds, sanity-check the attestations:

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
