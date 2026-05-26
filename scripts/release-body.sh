#!/usr/bin/env bash
# Compose the markdown body for a GitHub Release, given a directory of
# per-arch metadata files (meta-<cli>-rust<rust>-<arch>.json) written by
# the publish workflow's build job.
#
# Each metadata file has the shape:
#   {"arch": "...", "digest": "sha256:...", "image": "...", "rust_version": "...",
#    "stellar_cli_version": "...", "tag": "..."}
#
# Output goes to stdout.

set -euo pipefail

script_dir="$(CDPATH='' builtin cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$script_dir/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/release-body.sh --stellar-cli-version <v> --metadata-dir <path> [--registry <ref>] [--repo <slug>] [--help]

Required:
  --stellar-cli-version <v>   The release this body is for (e.g. 26.0.0).
                              Must match the cli in every metadata file.
  --metadata-dir <path>       Directory containing meta-*.json files.

Options:
  --registry <ref>            Registry path used in the rendered convenience-
                              tag lines. Default: docker.io/stellar/stellar-cli.
  --repo <slug>               GitHub repository slug (owner/repo) used in the
                              rendered `gh attestation verify --repo` example.
                              Default: stellar/stellar-cli-docker.
  --help                      Show this message.

Prints the release body markdown to stdout.
EOF
}

main() {
  local cli="" metadata_dir="" registry="docker.io/stellar/stellar-cli" \
        repo="stellar/stellar-cli-docker"

  while [ $# -gt 0 ]; do
    case "$1" in
      --stellar-cli-version) require_value "$1" "${2:-}"; cli="$2"; shift 2;;
      --metadata-dir)        require_value "$1" "${2:-}"; metadata_dir="$2"; shift 2;;
      --registry)            require_value "$1" "${2:-}"; registry="$2"; shift 2;;
      --repo)                require_value "$1" "${2:-}"; repo="$2"; shift 2;;
      -h|--help)             usage; exit 0;;
      *)                     err "unknown argument: $1"; usage; exit 1;;
    esac
  done

  test -n "$cli"          || { err "--stellar-cli-version is required"; usage; exit 1; }
  test -n "$metadata_dir" || { err "--metadata-dir is required"; usage; exit 1; }
  test -d "$metadata_dir" || die "$metadata_dir is not a directory"

  preflight_checks jq

  # Aggregate all meta-*.json files under the metadata dir, validating
  # each one individually before merging. A mismatched or missing
  # stellar_cli_version is a hard error — silently dropping would let a
  # misconfigured run produce a release body with arches omitted.
  local -a meta_files=()
  while IFS= read -r -d '' f; do
    meta_files+=("$f")
  done < <(find "$metadata_dir" -type f -name 'meta-*.json' -print0)
  test "${#meta_files[@]}" -gt 0 \
    || die "no meta-*.json files under $metadata_dir"

  local f entry_cli
  for f in "${meta_files[@]}"; do
    entry_cli="$(jq -r '.stellar_cli_version // empty' "$f")"
    test -n "$entry_cli" \
      || die "metadata file $f is missing the stellar_cli_version field"
    test "$entry_cli" = "$cli" \
      || die "metadata file $f has stellar_cli_version='$entry_cli', expected '$cli'"
  done

  local rows
  rows="$(jq -s 'sort_by(.rust_version, .arch)' "${meta_files[@]}")"

  emit_body "$cli" "$rows" "$registry" "$repo"
}

emit_body() {
  local cli="$1" rows="$2" registry="$3" repo="$4"

  printf '# stellar-cli %s\n\n' "$cli"

  printf 'Stellar CLI image (SEP-58-compatible image for Stellar smart contracts).\n\n'

  printf '## Convenience tags\n\n'
  printf -- '- `%s:%s` — multi-arch, default Rust for this release\n' "$registry" "$cli"
  local rust
  while IFS= read -r rust; do
    printf -- '- `%s:%s-rust%s` — multi-arch\n' "$registry" "$cli" "$rust"
  done < <(jq -r '. | map(.rust_version) | unique | .[]' <<<"$rows")

  printf '\n## Per-architecture digests (for SEP-58 `bldimg`)\n\n'
  printf 'Use the per-architecture digest when recording `bldimg` in your contract metadata. Never use a moving tag like `:latest` or `:%s`.\n\n' "$cli"

  local rust_rows
  while IFS= read -r rust; do
    printf '### Rust %s\n\n' "$rust"
    rust_rows="$(jq -c --arg r "$rust" 'map(select(.rust_version == $r)) | .[]' <<<"$rows")"

    while IFS= read -r row; do
      printf -- '- `%s@%s`\n' \
        "$(jq -r '.image' <<<"$row")" \
        "$(jq -r '.digest' <<<"$row")"
    done <<<"$rust_rows"

    printf '\nVerify:\n\n```sh\n'

    # gh attestation verify — verifies all attestation chains attached
    # to the image (SLSA provenance + SPDX SBOM in our case).
    while IFS= read -r row; do
      printf 'gh attestation verify oci://%s@%s --repo %s\n' \
        "$(jq -r '.image' <<<"$row")" \
        "$(jq -r '.digest' <<<"$row")" \
        "$repo"
    done <<<"$rust_rows"

    # cosign verify-attestation — registry-attached SLSA v1.0 provenance.
    # The certificate flags anchor trust to this repo's GitHub Actions
    # OIDC identity (the workflow that ran actions/attest-build-provenance);
    # without them cosign accepts any valid Sigstore signature, which is
    # not what we want. Pass `--type spdxjson` to verify the SBOM instead.
    printf '\n'
    while IFS= read -r row; do
      printf 'cosign verify-attestation \\\n'
      printf '  --type slsaprovenance1 \\\n'
      printf '  --certificate-identity-regexp "https://github.com/%s/\\.github/workflows/.*" \\\n' "$repo"
      printf '  --certificate-oidc-issuer https://token.actions.githubusercontent.com \\\n'
      printf '  %s@%s\n' \
        "$(jq -r '.image' <<<"$row")" \
        "$(jq -r '.digest' <<<"$row")"
    done <<<"$rust_rows"

    # docker buildx imagetools inspect — manifest + attached attestation
    # metadata (no signature verification, just inspection).
    printf '\n'
    while IFS= read -r row; do
      printf 'docker buildx imagetools inspect %s@%s\n' \
        "$(jq -r '.image' <<<"$row")" \
        "$(jq -r '.digest' <<<"$row")"
    done <<<"$rust_rows"

    printf '```\n\n'
  done < <(jq -r '. | map(.rust_version) | unique | .[]' <<<"$rows")

  cat <<'EOF'
## Verification

Each per-architecture image carries two independent attestation chains — SLSA build provenance and SPDX SBOM — signed by this repo's GitHub Actions OIDC identity. The per-Rust `Verify:` blocks above are copy-paste-runnable for every published image across three tools:

- `gh attestation verify` — checks every attestation chain in one call (recommended).
- `cosign verify-attestation` — registry-attached verification with explicit certificate identity + OIDC issuer flags so trust is anchored to this repo's workflows, not just "any valid Sigstore signature".
- `docker buildx imagetools inspect` — manifest + attached attestation metadata, useful for inspection (not signature verification).

## Assets

This release attaches one SBOM file (`.spdx.json`) and one provenance bundle (`.intoto.jsonl`) per per-architecture image.
EOF
}

main "$@"
