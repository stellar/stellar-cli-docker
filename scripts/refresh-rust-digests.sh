#!/usr/bin/env bash
# Maintainer helper: re-resolve rust:<version>-slim-bookworm to its current
# multi-arch index digest via `docker buildx imagetools inspect`, and update
# builds.json in place. Only fills entries whose digest is blank/unpinned;
# bumping a pinned digest must be requested per version via --rust-version.
#
# Output stays sorted because the script edits the existing
# rust_image_digests map (already alphabetical) without changing keys.

script_dir="$(CDPATH='' builtin cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$script_dir/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/refresh-rust-digests.sh [--rust-version <v>] [--dry-run] [--help]

By default, resolves digests only for existing rust_image_digests entries
whose value is blank or otherwise not a valid pinned digest (e.g. "",
"sha256:", or anything that doesn't match sha256:<64 hex>). Already-pinned
digests are intentional and are not touched — bumping a pinned digest is
an explicit choice and must be requested per version via --rust-version.

This script does not add new keys to rust_image_digests; the rust version
must already exist as a key. Add the key (with an empty digest) by hand
first if you want this script to fill it in.

Options:
  --rust-version <v>   Resolve this rust version specifically, even if it
                       already has a pinned digest. Must already be a key
                       in builds.json's rust_image_digests.
  --dry-run            Print the resolved digests but do not write back.
  --help               Show this message.

The digest captured is the multi-arch INDEX digest, which Docker resolves
to the correct per-host manifest at FROM time. This matches the comment in
builds.json and the buildx command:

  docker buildx imagetools inspect rust:<v>-slim-bookworm \
    --format '{{.Manifest.Digest}}'
EOF
}

main() {
  local only_version="" dry_run=0

  while [ $# -gt 0 ]; do
    case "$1" in
      --rust-version) require_value "$1" "${2:-}"; only_version="$2"; shift 2;;
      --dry-run)      dry_run=1; shift;;
      -h|--help)      usage; exit 0;;
      *)              err "unknown argument: $1"; usage; exit 1;;
    esac
  done

  preflight_checks jq buildx

  local versions
  if [ -n "$only_version" ]; then
    if [ "$(builds_json --arg v "$only_version" '.rust_image_digests[$v] // empty')" = "" ] \
        && [ "$(builds_json --arg v "$only_version" '.rust_image_digests | has($v)')" != "true" ]; then
      die "rust version $only_version is not a key in builds.json rust_image_digests"
    fi
    versions="$only_version"
  else
    # Default: only blank/missing entries. A pinned digest looks like
    # "sha256:<64 hex>"; anything shorter (empty string, "sha256:", a
    # partial value) is treated as needing resolution.
    versions="$(builds_json '
      .rust_image_digests
      | to_entries
      | map(select(.value | test("^sha256:[0-9a-f]{64}$") | not))
      | .[].key')"
    if [ -z "$versions" ]; then
      log "all rust_image_digests entries are already pinned; nothing to do."
      log "to re-resolve a specific one, pass --rust-version <v>."
      return 0
    fi
  fi

  local v new_digest
  declare -A updates=()
  while IFS= read -r v; do
    log "resolving rust:${v}-slim-bookworm ..."
    new_digest="$(docker buildx imagetools inspect "rust:${v}-slim-bookworm" \
      --format '{{.Manifest.Digest}}')"
    test -n "$new_digest" || die "empty digest returned for rust:${v}-slim-bookworm"
    log "  -> $new_digest"
    # shellcheck disable=SC2034  # `updates` is consumed by apply_updates via `local -n`
    updates["$v"]="$new_digest"
  done <<<"$versions"

  if [ "$dry_run" -eq 1 ]; then
    log "(dry-run; not writing builds.json)"
    return 0
  fi

  apply_updates updates
}

# Writes the updated digest map back to builds.json. Keeps every other key
# untouched and preserves the existing sorted shape via jq --sort-keys.
apply_updates() {
  # bash passes associative arrays by name, not by value, so we read from
  # the caller's array via indirection.
  local -n _u="$1"
  local tmp
  tmp="$(mktemp)"

  # Index entries so jq variable names contain no dots (which are illegal
  # in jq identifiers — `$v_1.93.0` would not parse).
  local -a keys=()
  local v
  for v in "${!_u[@]}"; do
    keys+=("$v")
  done

  local jq_args=()
  local i
  for i in "${!keys[@]}"; do
    v="${keys[$i]}"
    jq_args+=(--arg "v$i" "$v" --arg "d$i" "${_u[$v]}")
  done

  local jq_expr="."
  for i in "${!keys[@]}"; do
    jq_expr+=" | .rust_image_digests[\$v$i] = \$d$i"
  done

  jq --sort-keys "${jq_args[@]}" "$jq_expr" "$BUILDS_JSON_PATH" >"$tmp"
  mv "$tmp" "$BUILDS_JSON_PATH"
  log "wrote ${keys[*]} to $BUILDS_JSON_PATH"
}

main "$@"
