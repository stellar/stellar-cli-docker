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

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$script_dir/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/release-body.sh --stellar-cli-version <v> --metadata-dir <path> [--help]

Required:
  --stellar-cli-version <v>   The release this body is for (e.g. 26.0.0).
                              Must match the cli in every metadata file.
  --metadata-dir <path>       Directory containing meta-*.json files.

Options:
  --help                      Show this message.

Prints the release body markdown to stdout.
EOF
}

main() {
  local cli="" metadata_dir=""

  while [ $# -gt 0 ]; do
    case "$1" in
      --stellar-cli-version) require_value "$1" "${2:-}"; cli="$2"; shift 2;;
      --metadata-dir)        require_value "$1" "${2:-}"; metadata_dir="$2"; shift 2;;
      -h|--help)             usage; exit 0;;
      *)                     err "unknown argument: $1"; usage; exit 1;;
    esac
  done

  test -n "$cli"          || { err "--stellar-cli-version is required"; usage; exit 1; }
  test -n "$metadata_dir" || { err "--metadata-dir is required"; usage; exit 1; }
  test -d "$metadata_dir" || die "$metadata_dir is not a directory"

  preflight_checks jq

  # Aggregate all meta-*.json files under the metadata dir into one JSON array.
  local rows
  rows="$(find "$metadata_dir" -type f -name 'meta-*.json' -print0 \
    | xargs -0 jq -s --arg cli "$cli" \
        'map(select(.stellar_cli_version == $cli))
         | sort_by(.rust_version, .arch)')"
  test "$(jq 'length' <<<"$rows")" -gt 0 \
    || die "no metadata files for stellar-cli $cli under $metadata_dir"

  emit_body "$cli" "$rows"
}

emit_body() {
  local cli="$1" rows="$2"

  printf '# stellar-cli %s\n\n' "$cli"

  printf 'Trusted, SEP-58-compatible build images for the Stellar CLI.\n\n'

  printf '## Convenience tags\n\n'
  printf -- '- `docker.io/stellar/stellar-cli:%s` — multi-arch, default Rust for this release\n' "$cli"
  local rust
  while IFS= read -r rust; do
    printf -- '- `docker.io/stellar/stellar-cli:%s-rust%s` — multi-arch\n' "$cli" "$rust"
  done < <(jq -r '. | map(.rust_version) | unique | .[]' <<<"$rows")

  printf '\n## Per-architecture digests (for SEP-58 `bldimg`)\n\n'
  printf 'Use the per-architecture digest when recording `bldimg` in your contract metadata. Never use a moving tag like `:latest` or `:%s`.\n\n' "$cli"

  while IFS= read -r rust; do
    printf '### Rust %s\n\n' "$rust"
    while IFS= read -r row; do
      printf -- '- `%s@%s`\n' \
        "$(jq -r '.image' <<<"$row")" \
        "$(jq -r '.digest' <<<"$row")"
    done < <(jq -c --arg r "$rust" 'map(select(.rust_version == $r)) | .[]' <<<"$rows")
    printf '\n'
  done < <(jq -r '. | map(.rust_version) | unique | .[]' <<<"$rows")

  cat <<'EOF'
## Verification

Each per-architecture image carries two independent attestation chains.

### GitHub-native (recommended)

```sh
gh attestation verify oci://<image>@<digest> \
  --repo stellar/stellar-cli-docker
```

The repo includes `scripts/verify-image.sh` that wraps this for both provenance and SBOM:

```sh
./scripts/verify-image.sh --image <image>@<digest>
```

### Registry-attached (cosign / docker buildx)

```sh
cosign verify-attestation --type slsaprovenance <image>@<digest>
docker buildx imagetools inspect <image>@<digest>
```

## Assets

This release attaches one SBOM file (`.spdx.json`) and one provenance bundle (`.intoto.jsonl`) per per-architecture image.
EOF
}

main "$@"
