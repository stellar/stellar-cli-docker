#!/usr/bin/env bash
# Maintainer helper: resolve the upstream stellar/stellar-cli commit SHA for
# each stellar_cli_versions[].version (looking up the v<version> tag) and
# fill in any blank `ref` entries in builds.json.
#
# Parallel to scripts/refresh-rust-digests.sh: by default it only fills
# blanks, never silently rewriting an already-pinned SHA. Bumping a pinned
# SHA must be requested per version via --stellar-cli-version.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$script_dir/lib/common.sh"

STELLAR_CLI_REPO="https://github.com/stellar/stellar-cli.git"

usage() {
  cat <<'EOF'
Usage: scripts/refresh-stellar-cli-digests.sh [--stellar-cli-version <v>] [--dry-run] [--help]

By default, resolves git commit SHAs only for stellar_cli_versions[] entries
in builds.json whose `ref` is missing or blank. Already-pinned refs are
intentional and are not touched — bumping a pinned ref is an explicit choice
and must be requested per version via --stellar-cli-version.

Options:
  --stellar-cli-version <v>   Resolve this stellar-cli version specifically,
                              even if its ref is already pinned. Must already
                              be a key in builds.json's stellar_cli_versions.
  --dry-run                   Print the resolved refs but do not write back.
  --help                      Show this message.

For each version V, the script asks the upstream repo for the commit SHA
that the tag vV points at:

  git ls-remote https://github.com/stellar/stellar-cli.git \
    "refs/tags/vV^{}" "refs/tags/vV"

Annotated tags are peeled to their underlying commit; lightweight tags are
used as-is.
EOF
}

main() {
  local only_version="" dry_run=0

  while [ $# -gt 0 ]; do
    case "$1" in
      --stellar-cli-version) only_version="$2"; shift 2;;
      --dry-run)             dry_run=1; shift;;
      -h|--help)             usage; exit 0;;
      *)                     err "unknown argument: $1"; usage; exit 1;;
    esac
  done

  require_cmd jq git

  local versions
  if [ -n "$only_version" ]; then
    if [ "$(builds_json --arg v "$only_version" \
        '.stellar_cli_versions[] | select(.version == $v) | .version')" = "" ]; then
      die "stellar-cli version $only_version is not declared in builds.json"
    fi
    versions="$only_version"
  else
    # Default: only entries with a blank/missing ref. A pinned ref is a
    # 40-char hex SHA; anything else is treated as needing resolution.
    versions="$(builds_json '
      .stellar_cli_versions
      | map(select((.ref // "") | test("^[0-9a-f]{40}$") | not))
      | .[].version')"
    if [ -z "$versions" ]; then
      log "all stellar_cli_versions entries are already pinned; nothing to do."
      log "to re-resolve a specific one, pass --stellar-cli-version <v>."
      return 0
    fi
  fi

  declare -A resolved=()
  local v sha
  while IFS= read -r v; do
    log "resolving stellar-cli v${v} -> commit SHA ..."
    sha="$(resolve_tag_commit "v${v}")"
    test -n "$sha" || die "could not resolve tag v${v} in $STELLAR_CLI_REPO"
    log "  -> $sha"
    resolved["$v"]="$sha"
  done <<<"$versions"

  if [ "$dry_run" -eq 1 ]; then
    log "(dry-run; not writing builds.json)"
    return 0
  fi

  apply_updates resolved
}

# Resolves a tag name to the commit SHA it ultimately points to. For
# annotated tags, `<tag>^{}` peels to the underlying commit; for lightweight
# tags, the tag ref already IS the commit, so we fall back to it.
resolve_tag_commit() {
  local tag="$1"
  local out peeled plain
  out="$(git ls-remote "$STELLAR_CLI_REPO" \
    "refs/tags/${tag}^{}" "refs/tags/${tag}")"
  peeled="$(awk -v ref="refs/tags/${tag}^{}" '$2 == ref {print $1}' <<<"$out")"
  if [ -n "$peeled" ]; then
    printf '%s' "$peeled"
    return
  fi
  plain="$(awk -v ref="refs/tags/${tag}" '$2 == ref {print $1}' <<<"$out")"
  printf '%s' "$plain"
}

# Writes resolved SHAs back to builds.json. Touches only the matching entry's
# .ref field; everything else is left as-is (keys still alphabetical after
# jq --sort-keys).
apply_updates() {
  local -n _r="$1"
  local tmp
  tmp="$(mktemp)"

  local -a keys=()
  local v
  for v in "${!_r[@]}"; do
    keys+=("$v")
  done

  local jq_args=()
  local i
  for i in "${!keys[@]}"; do
    v="${keys[$i]}"
    jq_args+=(--arg "v$i" "$v" --arg "r$i" "${_r[$v]}")
  done

  # For each (version, ref) pair, find the matching entry by .version and
  # set .ref. Uses jq map(if ... then ... else . end) so unrelated entries
  # are untouched.
  local jq_expr="."
  for i in "${!keys[@]}"; do
    jq_expr+=" | .stellar_cli_versions |= map(if .version == \$v$i then .ref = \$r$i else . end)"
  done

  jq --sort-keys "${jq_args[@]}" "$jq_expr" "$BUILDS_JSON_PATH" >"$tmp"
  mv "$tmp" "$BUILDS_JSON_PATH"
  log "wrote ${keys[*]} to $BUILDS_JSON_PATH"
}

main "$@"
