#!/usr/bin/env bash
# Build a single stellar-cli image locally for a declared (cli, rust) pair.
# Looks up the pinned base image digest and stellar-cli commit SHA from
# builds.json so the inputs come from one source of truth.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$script_dir/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/build-image.sh --stellar-cli-version <v> --rust-version <v> [options]

Required:
  --stellar-cli-version <v>    e.g. 26.0.0; must be declared in builds.json
  --rust-version <v>           e.g. 1.94.0; must appear in that cli entry's
                               rust_versions array

Options:
  --platform <p>               linux/amd64 or linux/arm64. Defaults to the
                               host's native architecture.
  --tag <ref>                  Override the local tag. Default:
                               stellar-cli:<cli>-rust<rust>
  --variant <name>             Used for the org.stellar.variant label and
                               for variants[] entries. Default: standard
  --load                       After building, load the image into the local
                               docker daemon. Default behaviour with buildx
                               for single-platform builds.
  --help                       Show this message.

The script builds locally only. Publishing is handled by a separate script.
EOF
}

main() {
  local cli="" rust="" platform="" tag="" variant="standard"

  while [ $# -gt 0 ]; do
    case "$1" in
      --stellar-cli-version) cli="$2"; shift 2;;
      --rust-version)        rust="$2"; shift 2;;
      --platform)            platform="$2"; shift 2;;
      --tag)                 tag="$2"; shift 2;;
      --variant)             variant="$2"; shift 2;;
      --load)                shift;;  # noop, buildx single-platform loads by default
      -h|--help)             usage; exit 0;;
      *)                     err "unknown argument: $1"; usage; exit 1;;
    esac
  done

  test -n "$cli"  || { err "--stellar-cli-version is required"; usage; exit 1; }
  test -n "$rust" || { err "--rust-version is required"; usage; exit 1; }

  require_cmd jq docker

  assert_pair_declared "$cli" "$rust"

  local rust_digest stellar_ref
  rust_digest="$(rust_image_digest_for "$rust")"
  stellar_ref="$(stellar_cli_ref_for "$cli")"

  if [ -z "$tag" ]; then
    tag="stellar-cli:${cli}-rust${rust}"
  fi

  local build_date builds_json_sha
  build_date="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  builds_json_sha="$(shasum -a 256 "$BUILDS_JSON_PATH" | awk '{print $1}')"

  log "building $tag"
  log "  stellar-cli $cli  ($stellar_ref)"
  log "  rust $rust          ($rust_digest)"
  log "  platform ${platform:-<host native>}"

  local platform_args=()
  if [ -n "$platform" ]; then
    platform_args=(--platform "$platform")
  fi

  docker buildx build \
    "${platform_args[@]}" \
    --load \
    --build-arg "RUST_VERSION=$rust" \
    --build-arg "RUST_IMAGE_DIGEST=$rust_digest" \
    --build-arg "STELLAR_CLI_REF=$stellar_ref" \
    --build-arg "STELLAR_CLI_VERSION=$cli" \
    --build-arg "VARIANT=$variant" \
    --build-arg "BUILD_DATE=$build_date" \
    --build-arg "BUILDS_JSON_SHA=$builds_json_sha" \
    --tag "$tag" \
    "$(repo_root)"

  log ""
  log "built: $tag"
}

main "$@"
