# shellcheck shell=bash
# Shared helpers for scripts in this repo. Source from other scripts via:
#   source "$(dirname "$0")/lib/common.sh"

set -euo pipefail

# repo_root resolves to the absolute path of the repo, regardless of where
# the caller invoked from. All scripts assume builds.json lives at this root.
repo_root() {
  git -C "$(dirname "${BASH_SOURCE[1]}")" rev-parse --show-toplevel
}

BUILDS_JSON_PATH="$(repo_root)/builds.json"
BUILDS_SCHEMA_PATH="$(repo_root)/builds.schema.json"

log() {
  printf '%s\n' "$*" >&2
}

err() {
  printf 'error: %s\n' "$*" >&2
}

die() {
  err "$*"
  exit 1
}

require_cmd() {
  local cmd
  for cmd in "$@"; do
    command -v "$cmd" >/dev/null 2>&1 \
      || die "required command not found: $cmd"
  done
}

# sha256_of <file> prints the file's SHA-256 hex digest. Prefers coreutils
# sha256sum (universal on Linux), falls back to BSD shasum -a 256 (default
# on macOS). One of the two is available on every platform we run on.
sha256_of() {
  local file="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$file" | awk '{print $1}'
  else
    die "need either sha256sum or shasum on PATH"
  fi
}

# builds_json [jq-args...] <jq-expr> evaluates <jq-expr> against builds.json
# and prints the raw result. Any extra jq args (e.g. --arg name value) are
# passed through; the expression itself is positional, just like jq.
builds_json() {
  jq -r "$@" "$BUILDS_JSON_PATH"
}

# Resolve the rust image digest for a given rust version. Dies if unknown.
rust_image_digest_for() {
  local rust="$1"
  local digest
  digest="$(builds_json --arg rust "$rust" '.rust_image_digests[$rust] // empty')"
  test -n "$digest" || die "no rust_image_digests entry for rust version: $rust"
  printf '%s' "$digest"
}

# Resolve the stellar-cli git ref for a given version. Dies if unknown.
stellar_cli_ref_for() {
  local version="$1"
  local ref
  ref="$(builds_json --arg v "$version" '.stellar_cli_versions[] | select(.version == $v) | .ref' | head -n1)"
  test -n "$ref" || die "no stellar_cli_versions entry for version: $version"
  printf '%s' "$ref"
}

# Assert that a (cli-version, rust-version) pair is declared in builds.json.
assert_pair_declared() {
  local cli="$1" rust="$2"
  local found
  found="$(builds_json --arg cli "$cli" --arg rust "$rust" \
    '.stellar_cli_versions[] | select(.version == $cli) | .rust_versions[] | select(. == $rust)')"
  test -n "$found" \
    || die "stellar-cli $cli is not declared with rust $rust in builds.json"
}
