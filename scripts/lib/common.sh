# shellcheck shell=bash
# Shared helpers for scripts in this repo. Source from each script's top
# (assumes CWD is the repo root):
#   source scripts/lib/common.sh

# Bash version guard runs before `shopt -s inherit_errexit` below, which
# is bash 4.4+. macOS ships 3.2 by default.
if (( BASH_VERSINFO[0] < 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] < 4) )); then
  printf 'error: scripts need bash 4.4+ (current: %s); on macOS: brew install bash, then ensure it precedes /bin/bash on PATH\n' \
    "${BASH_VERSION:-unknown}" >&2
  exit 1
fi

set -euo pipefail
shopt -s inherit_errexit

# repo_root resolves to the absolute path of the repo, regardless of where
# the caller invoked from. All scripts assume builds.json lives at this root.
repo_root() {
  git -C "$(dirname "${BASH_SOURCE[1]}")" rev-parse --show-toplevel
}

BUILDS_JSON_PATH="$(repo_root)/builds.json"

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

# require_value <flag> <value>
# Aborts with a clear error if <value> is empty. Use at the top of each
# --flag case arm:  require_value "$1" "${2:-}"
# Prevents the unhelpful "$2: unbound variable" crash that `set -u`
# emits when a user passes a flag with no value (e.g. `--image` at EOL).
require_value() {
  local flag="$1" value="${2:-}"
  test -n "$value" || die "missing value for $flag"
}

# preflight_checks [required-cmds...] is the one call every script makes
# at the top of main(). Verifies each named command. Recognised
# pseudo-tokens:
#   sha256 — at least one of sha256sum or shasum must exist (backs sha256_of).
#   buildx — docker exists AND the buildx plugin is functional. Implies docker.
# Anything else is treated as a literal command name.
# (Bash version is enforced at source time; see top of file.)
preflight_checks() {
  local tok
  local cmds=()
  for tok in "$@"; do
    case "$tok" in
      sha256) require_sha256;;
      buildx) require_buildx;;
      *)      cmds+=("$tok");;
    esac
  done
  if [ "${#cmds[@]}" -gt 0 ]; then
    require_cmd "${cmds[@]}"
  fi
}

require_sha256() {
  command -v sha256sum >/dev/null 2>&1 \
    || command -v shasum  >/dev/null 2>&1 \
    || die "need either sha256sum or shasum on PATH for sha256 hashing"
}

require_buildx() {
  command -v docker >/dev/null 2>&1 \
    || die "docker is required (needed for buildx)"
  docker buildx version >/dev/null 2>&1 \
    || die "docker buildx plugin is required; install it or upgrade docker (docker buildx is the multi-arch build driver)"
  # Daemon reachability — `docker buildx version` only checks the plugin,
  # not whether the daemon is up. Catch a stopped or unauthorized daemon
  # before any build args get resolved.
  docker info >/dev/null 2>&1 \
    || die "docker daemon is not reachable; start it (e.g. start Docker Desktop / OrbStack) or check 'docker info' for details"
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

# Resolve the rust image digest for a given rust base key. Dies if unknown.
# A rust base key is the composite <rust>-<debian> form, e.g. 1.94.0-trixie.
rust_image_digest_for() {
  local rust_key="$1"
  local digest
  digest="$(builds_json --arg rust "$rust_key" '.rust_image_digests[$rust] // empty')"
  test -n "$digest" || die "no rust_image_digests entry for rust base key: $rust_key"
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

# Assert that a (cli-version, rust-base-key) pair is declared in builds.json.
assert_pair_declared() {
  local cli="$1" rust_key="$2"
  local found
  found="$(builds_json --arg cli "$cli" --arg rust "$rust_key" \
    '.stellar_cli_versions[] | select(.version == $cli) | .rust_versions[] | select(. == $rust)')"
  test -n "$found" \
    || die "stellar-cli $cli is not declared with rust base key $rust_key in builds.json"
}

# Resolve the default rust base key for a stellar-cli release: the
# highest-version key in that cli's rust_versions[] whose suffix matches
# the global default_distro (composed as slim-<default_distro> since the
# project standardises on slim variants — see project_slim_base_for_sbom_limit).
# Dies on missing default_distro, unknown cli, or no matching key.
derive_default_rust_for_cli() {
  local cli="$1"
  local distro
  distro="$(builds_json '.default_distro // empty')"
  test -n "$distro" || die "builds.json is missing default_distro"

  local suffix="slim-$distro"
  local picked
  picked="$(builds_json --arg cli "$cli" --arg suffix "$suffix" '
    .stellar_cli_versions[]
    | select(.version == $cli)
    | .rust_versions
    | map(select(endswith("-" + $suffix)))
    | sort_by(split("-") | .[0] | split(".") | map(tonumber))
    | last // empty
  ')"
  test -n "$picked" \
    || die "no rust_versions[] key matches default_distro '$distro' (suffix '$suffix') for stellar-cli $cli"
  printf '%s' "$picked"
}

# Extract the bare rust toolchain version from a composite base key.
# 1.94.0-trixie -> 1.94.0
rust_version_from_key() {
  local key="$1"
  [[ "$key" =~ ^([0-9]+\.[0-9]+\.[0-9]+)- ]] \
    || die "invalid rust base key: $key (expected <version>-<debian>)"
  printf '%s' "${BASH_REMATCH[1]}"
}

# Extract the Debian codename suffix from a composite base key. This is
# the trailing part used by the upstream Rust image tag, e.g. `trixie`.
# It is metadata only — labels and tag construction consume it; FROM
# lines never do.
rust_base_suffix_from_key() {
  local key="$1"
  [[ "$key" =~ ^[0-9]+\.[0-9]+\.[0-9]+-(.+)$ ]] \
    || die "invalid rust base key: $key (expected <version>-<debian>)"
  printf '%s' "${BASH_REMATCH[1]}"
}
