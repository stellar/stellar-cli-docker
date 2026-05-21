#!/usr/bin/env bash
# Stage a new stellar-cli release: add the cli entry to builds.json, pick
# its rust pairings, resolve the upstream cli ref and any missing rust
# base image digests, and validate the result.
#
# Driven by .github/workflows/release.yml, but also runnable locally for
# dry-run / debugging — every step is `git`-safe (builds.json is the only
# file touched).

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$script_dir/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/release-prepare.sh --stellar-cli-version <v> [--rust-versions <v1,v2,...>] [--help]

Required:
  --stellar-cli-version <v>   New stellar-cli release version, e.g. 26.1.0.
                              Must not already be declared in builds.json.

Options:
  --rust-versions <list>      Comma-separated rust versions to pair with.
                              Default: the last two minor stable rust
                              versions from rust-lang/rust GitHub releases,
                              at their latest patch each (e.g. 1.94.1,1.95.0).
                              The last entry in the list becomes default_rust.
  --help                      Show this message.

Adds the new cli entry to builds.json (with empty ref + any missing rust
digest entries), then runs refresh-stellar-cli-digests.sh and
refresh-rust-digests.sh to fill the blanks, then validate-json.sh.
EOF
}

main() {
  local cli="" rust_versions_csv=""

  while [ $# -gt 0 ]; do
    case "$1" in
      --stellar-cli-version) require_value "$1" "${2:-}"; cli="$2"; shift 2;;
      --rust-versions)       require_value "$1" "${2:-}"; rust_versions_csv="$2"; shift 2;;
      -h|--help)             usage; exit 0;;
      *)                     err "unknown argument: $1"; usage; exit 1;;
    esac
  done

  test -n "$cli" || { err "--stellar-cli-version is required"; usage; exit 1; }

  preflight_checks jq gh git

  # Reject duplicate cli versions — re-publishing an existing one needs a
  # different code path (see RELEASE.md), not a fresh prepare.
  local existing
  existing="$(builds_json --arg v "$cli" \
    '.stellar_cli_versions[] | select(.version == $v) | .version' | head -n1)"
  test -z "$existing" \
    || die "stellar-cli $cli is already declared in builds.json"

  # Resolve rust versions (auto-pick or override).
  local -a rusts=()
  if [ -n "$rust_versions_csv" ]; then
    IFS=',' read -ra rusts <<<"$rust_versions_csv"
    log "rust versions (from --rust-versions): ${rusts[*]}"
  else
    log "picking the last 2 minor stable rust versions from rust-lang/rust ..."
    while IFS= read -r v; do
      rusts+=("$v")
    done < <(pick_default_rust_versions)
    log "rust versions (auto): ${rusts[*]}"
  fi
  test "${#rusts[@]}" -gt 0 || die "no rust versions selected"

  # The last entry is newest → default_rust.
  local default_rust="${rusts[-1]}"

  log "default_rust: $default_rust"
  log "applying changes to $BUILDS_JSON_PATH ..."
  update_builds_json "$cli" "$default_rust" "${rusts[@]}"

  log "resolving upstream stellar-cli ref ..."
  "$script_dir/refresh-stellar-cli-digests.sh"

  log "resolving rust image digests ..."
  "$script_dir/refresh-rust-digests.sh"

  log "validating builds.json ..."
  "$script_dir/validate-json.sh"

  log ""
  log "release-prepare: builds.json staged for stellar-cli $cli with rust ${rusts[*]}"
}

# Picks the last two unique minor stable rust versions, at their latest
# patch each, from rust-lang/rust's GitHub releases. Output: ascending,
# one per line.
pick_default_rust_versions() {
  local versions
  versions="$(gh api repos/rust-lang/rust/releases \
    --jq '[.[] | select(.prerelease == false) | .tag_name] | .[0:20]')"
  jq -r '
    reduce .[] as $v (
      {result: [], seen: {}};
      ($v | split(".") | .[0:2] | join(".")) as $minor
      | if .seen[$minor] then .
        else .result += [$v] | .seen[$minor] = true
        end
    )
    | .result[0:2]
    | sort_by(split(".") | map(tonumber))
    | .[]
  ' <<<"$versions"
}

# Adds the new stellar_cli_versions entry (with empty ref) and stubs any
# missing rust_image_digests keys with empty strings. The subsequent
# refresh-*.sh runs fill the blanks; refresh ignores already-pinned values
# so existing entries are untouched.
update_builds_json() {
  local cli="$1" default_rust="$2"
  shift 2
  local -a rust_versions=("$@")

  local rust_array
  rust_array="$(printf '%s\n' "${rust_versions[@]}" | jq -R . | jq -s 'sort')"

  local cli_entry
  cli_entry="$(jq -n \
    --arg default_rust "$default_rust" \
    --argjson rust_versions "$rust_array" \
    --arg version "$cli" \
    '{
      default_rust: $default_rust,
      ref: "",
      rust_versions: $rust_versions,
      version: $version
    }')"

  local digest_stubs
  digest_stubs="$(printf '%s\n' "${rust_versions[@]}" \
    | jq -R . | jq -s 'map({(.): ""}) | add')"

  local tmp
  tmp="$(mktemp)"
  jq --sort-keys \
    --argjson entry "$cli_entry" \
    --argjson stubs "$digest_stubs" \
    '
      .stellar_cli_versions += [$entry]
      | .rust_image_digests = ($stubs + .rust_image_digests)
    ' \
    "$BUILDS_JSON_PATH" > "$tmp"
  mv "$tmp" "$BUILDS_JSON_PATH"
}

main "$@"
