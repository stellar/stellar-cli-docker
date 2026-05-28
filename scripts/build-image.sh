#!/usr/bin/env bash
# Build a single stellar-cli image locally for a declared (cli, rust base)
# pair. Looks up the pinned base image digest and stellar-cli commit SHA
# from builds.json so the inputs come from one source of truth.

source scripts/lib/common.sh

usage() {
  cat <<'EOF'
Usage: scripts/build-image.sh --stellar-cli-version <v> --rust-version <key> [options]

Required:
  --stellar-cli-version <v>    e.g. 26.0.0; must be declared in builds.json
  --rust-version <key>         composite rust base key, e.g. 1.94.0-trixie;
                               must appear in that cli entry's
                               rust_versions array

Options:
  --platform <p>               linux/amd64 or linux/arm64. Defaults to the
                               host's native architecture.
  --tag <ref>                  Override the local tag. Default:
                               stellar-cli:<cli>-rust<key>
  --source-repo <slug>         GitHub repository slug (owner/repo) baked into
                               the image's OCI source/url/documentation labels.
                               Default: stellar/stellar-cli-docker.
  --help                       Show this message.

The script builds locally only. Publishing is handled by a separate script.
EOF
}

main() {
  local cli="" rust_key="" platform="" tag="" source_repo="stellar/stellar-cli-docker"

  while [ $# -gt 0 ]; do
    case "$1" in
      --stellar-cli-version) require_value "$1" "${2:-}"; cli="$2"; shift 2;;
      --rust-version)        require_value "$1" "${2:-}"; rust_key="$2"; shift 2;;
      --platform)            require_value "$1" "${2:-}"; platform="$2"; shift 2;;
      --tag)                 require_value "$1" "${2:-}"; tag="$2"; shift 2;;
      --source-repo)         require_value "$1" "${2:-}"; source_repo="$2"; shift 2;;
      -h|--help)             usage; exit 0;;
      *)                     err "unknown argument: $1"; usage; exit 1;;
    esac
  done

  test -n "$cli"      || { err "--stellar-cli-version is required"; usage; exit 1; }
  test -n "$rust_key" || { err "--rust-version is required"; usage; exit 1; }

  preflight_checks jq buildx sha256

  assert_pair_declared "$cli" "$rust_key"

  local rust_digest stellar_ref rust_version rust_base_suffix
  rust_digest="$(rust_image_digest_for "$rust_key")"
  stellar_ref="$(stellar_cli_ref_for "$cli")"
  rust_version="$(rust_version_from_key "$rust_key")"
  rust_base_suffix="$(rust_base_suffix_from_key "$rust_key")"

  if [ -z "$tag" ]; then
    tag="stellar-cli:${cli}-rust${rust_key}"
  fi

  local build_date builds_json_sha
  build_date="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  builds_json_sha="$(sha256_of "$BUILDS_JSON_PATH")"

  log "building $tag"
  log "  stellar-cli $cli         ($stellar_ref)"
  log "  rust $rust_key           ($rust_digest)"
  log "  base rust:${rust_version}-${rust_base_suffix}"
  log "  platform ${platform:-<host native>}"

  local platform_args=()
  if [ -n "$platform" ]; then
    platform_args=(--platform "$platform")
  fi

  docker buildx build \
    "${platform_args[@]}" \
    --load \
    --build-arg "RUST_VERSION=$rust_version" \
    --build-arg "RUST_BASE_SUFFIX=$rust_base_suffix" \
    --build-arg "RUST_IMAGE_DIGEST=$rust_digest" \
    --build-arg "STELLAR_CLI_REV=$stellar_ref" \
    --build-arg "STELLAR_CLI_VERSION=$cli" \
    --build-arg "BUILD_DATE=$build_date" \
    --build-arg "BUILDS_JSON_SHA=$builds_json_sha" \
    --build-arg "SOURCE_REPO=$source_repo" \
    --tag "$tag" \
    "$(repo_root)"

  log ""
  log "built: $tag"
}

main "$@"
