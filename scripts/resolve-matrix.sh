#!/usr/bin/env bash
# Read builds.json and emit a JSON matrix suitable for `fromJson()` in a
# GitHub Actions workflow. The output drives per-image build jobs.
#
# For each stellar_cli_versions[] entry, for each rust in that entry's
# rust_versions, emits one row per architecture (amd64, arm64). Rows carry
# the inputs build-image.sh needs plus the precomputed arch suffix for
# callers that don't want to translate the platform string themselves.

set -euo pipefail

script_dir="$(CDPATH='' builtin cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$script_dir/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/resolve-matrix.sh [--compact|--pretty] [--help]

Prints {"include": [...]} on stdout. Each include entry has:
  arch                  amd64 | arm64
  platform              linux/amd64 | linux/arm64
  rust_version          e.g. 1.94.0
  stellar_cli_version   e.g. 26.0.0

Options:
  --compact   One-line JSON (default; matches what fromJson() consumes).
  --pretty    Pretty-printed JSON, for human inspection.
  --help      Show this message.
EOF
}

main() {
  local mode="compact"

  while [ $# -gt 0 ]; do
    case "$1" in
      --compact) mode="compact"; shift;;
      --pretty)  mode="pretty"; shift;;
      -h|--help) usage; exit 0;;
      *)         err "unknown argument: $1"; usage; exit 1;;
    esac
  done

  preflight_checks jq

  local jq_flags=(-c)
  if [ "$mode" = "pretty" ]; then
    jq_flags=()
  fi

  builds_json "${jq_flags[@]}" '
    def archs: ["amd64", "arm64"];
    def row(cli; rust; arch):
      {
        arch: arch,
        platform: ("linux/" + arch),
        rust_version: rust,
        stellar_cli_version: cli
      };

    {
      include:
        [ .stellar_cli_versions[]
          | . as $e
          | $e.rust_versions[] as $rust
          | archs[] as $arch
          | row($e.version; $rust; $arch)
        ]
    }
  '
}

main "$@"
