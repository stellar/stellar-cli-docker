#!/usr/bin/env bash
# Read builds.json and emit a JSON matrix suitable for `fromJson()` in a
# GitHub Actions workflow. The output drives per-image build jobs.
#
# For each stellar_cli_versions[] entry, for each rust base key in that
# entry's rust_versions, emits one row per architecture (amd64, arm64).
# Rows carry the inputs build-image.sh needs (including the bare rust
# version and the variant+debian suffix, parsed from the composite key)
# plus the precomputed arch suffix for callers that don't want to
# translate the platform string themselves.

source scripts/lib/common.sh

usage() {
  cat <<'EOF'
Usage: scripts/resolve-matrix.sh [--stellar-cli-version <v>] [--compact|--pretty] [--help]

Prints {"include": [...]} on stdout. Each include entry has:
  arch                  amd64 | arm64
  platform              linux/amd64 | linux/arm64
  rust_base_key         composite key, e.g. 1.94.0-slim-trixie
  rust_base_suffix      variant+debian portion, e.g. slim-trixie
  rust_image_digest     sha256:... (pinned base image digest)
  rust_version          bare rust toolchain version, e.g. 1.94.0
  stellar_cli_ref       40-char git SHA from stellar/stellar-cli
  stellar_cli_version   e.g. 26.0.0

Options:
  --stellar-cli-version <v>   Limit output to one cli version (must be a
                              declared entry in builds.json). Used by the
                              publish workflow which scopes each run to a
                              single release. Without this flag, every
                              declared cli is included.
  --compact                   One-line JSON (default; matches what fromJson()
                              consumes).
  --pretty                    Pretty-printed JSON, for human inspection.
  --help                      Show this message.
EOF
}

main() {
  local mode="compact" only_cli=""

  while [ $# -gt 0 ]; do
    case "$1" in
      --stellar-cli-version) require_value "$1" "${2:-}"; only_cli="$2"; shift 2;;
      --compact)             mode="compact"; shift;;
      --pretty)              mode="pretty"; shift;;
      -h|--help)             usage; exit 0;;
      *)                     err "unknown argument: $1"; usage; exit 1;;
    esac
  done

  preflight_checks jq

  if [ -n "$only_cli" ]; then
    local found
    found="$(builds_json --arg v "$only_cli" \
      '.stellar_cli_versions[] | select(.version == $v) | .version' | head -n1)"
    test -n "$found" \
      || die "stellar-cli $only_cli is not declared in builds.json"
  fi

  local jq_flags=(-c)
  if [ "$mode" = "pretty" ]; then
    jq_flags=()
  fi

  builds_json "${jq_flags[@]}" --arg only "$only_cli" '
    . as $b
    | def archs: ["amd64", "arm64"];
      def digest_for(key):
        $b.rust_image_digests[key]
        // error("no rust_image_digests entry for rust base key \(key)");
      def parse_key(key):
        (key | capture("^(?<v>[0-9]+\\.[0-9]+\\.[0-9]+)-(?<s>.+)$"))
        // error("invalid rust base key \(key)");
      def row(cli; ref; key; arch):
        parse_key(key) as $p
        | {
            arch: arch,
            platform: ("linux/" + arch),
            rust_base_key: key,
            rust_base_suffix: $p.s,
            rust_image_digest: digest_for(key),
            rust_version: $p.v,
            stellar_cli_ref: ref,
            stellar_cli_version: cli
          };

      {
        include:
          [ .stellar_cli_versions[]
            | select($only == "" or .version == $only)
            | . as $e
            | $e.rust_versions[] as $key
            | archs[] as $arch
            | row($e.version; $e.ref; $key; $arch)
          ]
      }
  '
}

main "$@"
