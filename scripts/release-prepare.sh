#!/usr/bin/env bash
# Stage a new stellar-cli release: add the cli entry to builds.json, pick
# its rust pairings, resolve the upstream cli ref and any missing rust
# base image digests, and validate the result.
#
# Driven by .github/workflows/release.yml, but also runnable locally for
# dry-run / debugging — every step is `git`-safe (builds.json is the only
# file touched).

source scripts/lib/common.sh

usage() {
  cat <<'EOF'
Usage: scripts/release-prepare.sh --stellar-cli-version <v> [--rust-versions <v1,v2,...>] [--help]

Required:
  --stellar-cli-version <v>   stellar-cli release version, e.g. 26.0.0.
                              New = added as a fresh entry; existing in
                              builds.json = refreshed (rust pairings
                              replaced) and a new GitHub Release iteration
                              tag is chosen.

Options:
  --rust-versions <list>      Comma-separated composite rust base keys to
                              pair with, e.g. 1.94.1-trixie,1.95.0-trixie.
                              Default: the last two minor stable rust
                              versions from rust-lang/rust GitHub releases,
                              at their latest patch each, joined with the
                              variant+debian suffix carried by the most
                              recent existing builds.json entry's
                              default_rust. The last entry in the list
                              becomes default_rust.
  --help                      Show this message.

Stages builds.json (new entry or refresh), resolves cli ref + rust image
digests, validates the result, then prints the chosen GitHub Release tag
as the final stdout line:

  - v<cli>       if no release exists for this cli yet
  - v<cli>-1     if v<cli> exists; -2 if v<cli>-1 exists; etc.

All log output goes to stderr; stdout is just the tag.
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

  preflight_checks jq gh git curl sha256

  # Snapshot of builds.json before any modifications, so we can detect
  # whether the script actually changed anything (vs. a no-op refresh).
  local before_hash
  before_hash="$(sha256_of "$BUILDS_JSON_PATH")"

  # Detect mode: a fresh release of a new cli vs. a refresh of an existing
  # one. Both are legitimate paths through this script.
  local mode existing
  existing="$(builds_json --arg v "$cli" \
    '.stellar_cli_versions[] | select(.version == $v) | .version' | head -n1)"
  if [ -z "$existing" ]; then
    mode=new
  else
    mode=refresh
  fi
  log "mode: $mode"

  # Always the latest two minor rust base keys for the suffix in use
  # today, at their latest patch each. Sourced from Docker Hub's library/
  # rust tag list so we can never pick a key whose image hasn't been
  # published yet. Maintainers who need different pairings can edit
  # builds.json on the release branch before merging.
  local -a rusts=()
  if [ -n "$rust_versions_csv" ]; then
    IFS=',' read -ra rusts <<<"$rust_versions_csv"
    log "rust base keys (from --rust-versions): ${rusts[*]}"
  else
    local suffix
    suffix="$(current_rust_base_suffix)"
    log "picking the last 2 minor rust base keys with suffix '$suffix' from Docker Hub ..."
    while IFS= read -r k; do
      rusts+=("$k")
    done < <(pick_default_rust_base_keys "$suffix")
    log "rust base keys (auto): ${rusts[*]}"
  fi
  test "${#rusts[@]}" -gt 0 || die "no rust base keys selected"
  local default_rust="${rusts[-1]}"
  log "default_rust: $default_rust"

  log "applying changes to $BUILDS_JSON_PATH ..."
  if [ "$mode" = new ]; then
    add_cli_entry "$cli" "$default_rust" "${rusts[@]}"
  else
    replace_cli_entry "$cli" "$default_rust" "${rusts[@]}"
  fi

  log "resolving upstream stellar-cli ref ..."
  scripts/refresh-stellar-cli-digests.sh

  log "resolving rust image digests ..."
  scripts/refresh-rust-digests.sh

  log "validating builds.json ..."
  scripts/validate-json.sh

  # If nothing actually changed in builds.json (compared to the snapshot
  # we took at the top of main), there is nothing to release. Happens on a
  # refresh run when the current latest rust versions and cli ref already
  # match what's declared. Fail loudly so the workflow surfaces it
  # cleanly instead of trying to push an empty commit.
  local after_hash
  after_hash="$(sha256_of "$BUILDS_JSON_PATH")"
  if [ "$before_hash" = "$after_hash" ]; then
    die "no changes to builds.json — nothing to release. The auto-picked rust versions and cli ref already match what's declared for stellar-cli $cli."
  fi

  # Pick the GitHub Release tag this iteration will publish as.
  local release_tag
  release_tag="$(pick_release_tag "$cli")"
  log "release tag: $release_tag"

  log ""
  log "release-prepare: builds.json staged for stellar-cli $cli with rust ${rusts[*]}"

  # Final stdout line is the chosen release tag, for workflows that need
  # to capture it.
  printf '%s\n' "$release_tag"
}

# Returns the variant+debian suffix carried by the newest existing entry's
# default_rust. Dies if builds.json has no entries — in that bootstrap
# case the maintainer must pass --rust-versions explicitly (with composite
# keys) so the source of truth stays exclusively in builds.json.
current_rust_base_suffix() {
  local newest_default
  newest_default="$(builds_json '
    .stellar_cli_versions
    | sort_by(.version | split(".") | map(tonumber))
    | .[-1].default_rust // empty
  ')"
  test -n "$newest_default" \
    || die "builds.json has no stellar_cli_versions; pass --rust-versions with composite keys (e.g. 1.94.0-trixie) to seed the first entry"
  rust_base_suffix_from_key "$newest_default"
}

# Picks the last two unique minor rust base keys for the given suffix,
# at their latest patch each, by listing library/rust tags on Docker Hub.
# Using Docker Hub as the source list closes the timing race where
# rust-lang/rust publishes a new release before the docker-rust team
# publishes the matching image: tags we can't pull are simply not in
# the response. Output: ascending composite keys, one per line.
pick_default_rust_base_keys() {
  local suffix="$1"
  test -n "$suffix" || die "pick_default_rust_base_keys: suffix is required"

  # `name=<suffix>` is a server-side substring filter that narrows the
  # response. The local regex is what enforces the exact composite key
  # shape, so a tag like 1.96.0-slim-bookworm (different debian) or
  # 1.96.0-trixie (non-slim) is rejected even though substrings overlap.
  curl -fsSL "https://hub.docker.com/v2/repositories/library/rust/tags?page_size=100&name=${suffix}" \
    | jq -r --arg suffix "$suffix" '
        [.results[].name
         | select(test("^[0-9]+\\.[0-9]+\\.[0-9]+-" + $suffix + "$"))]
        | sort_by(capture("^(?<v>[0-9]+\\.[0-9]+\\.[0-9]+)-").v
                  | split(".") | map(tonumber))
        | reverse
        | reduce .[] as $tag (
            {result: [], seen: {}};
            ($tag | capture("^(?<v>[0-9]+\\.[0-9]+\\.[0-9]+)-").v
                  | split(".") | .[0:2] | join(".")) as $minor
            | if .seen[$minor] then .
              else .result += [$tag] | .seen[$minor] = true
              end
          )
        | .result[0:2]
        | reverse
        | .[]
      '
}

# Appends a fresh stellar_cli_versions entry (with empty ref). Used for
# new-cli releases.
add_cli_entry() {
  local cli="$1" default_rust="$2"
  shift 2
  local -a rust_versions=("$@")

  local cli_entry stubs
  cli_entry="$(make_cli_entry "$cli" "$default_rust" "" "${rust_versions[@]}")"
  stubs="$(make_digest_stubs "${rust_versions[@]}")"

  local tmp
  tmp="$(mktemp)"
  jq --sort-keys \
    --argjson entry "$cli_entry" \
    --argjson stubs "$stubs" \
    '
      .stellar_cli_versions += [$entry]
      | .rust_image_digests = ($stubs + .rust_image_digests)
    ' \
    "$BUILDS_JSON_PATH" > "$tmp"
  mv "$tmp" "$BUILDS_JSON_PATH"
}

# Replaces an existing stellar_cli_versions entry's rust_versions and
# default_rust (and clears ref so refresh-stellar-cli-digests.sh re-resolves
# it — keeps the workflow idempotent even if the upstream SHA somehow moved).
# Used for refresh runs.
replace_cli_entry() {
  local cli="$1" default_rust="$2"
  shift 2
  local -a rust_versions=("$@")

  local cli_entry stubs
  cli_entry="$(make_cli_entry "$cli" "$default_rust" "" "${rust_versions[@]}")"
  stubs="$(make_digest_stubs "${rust_versions[@]}")"

  local tmp
  tmp="$(mktemp)"
  jq --sort-keys \
    --arg cli "$cli" \
    --argjson entry "$cli_entry" \
    --argjson stubs "$stubs" \
    '
      .stellar_cli_versions |= map(if .version == $cli then $entry else . end)
      | .rust_image_digests = ($stubs + .rust_image_digests)
    ' \
    "$BUILDS_JSON_PATH" > "$tmp"
  mv "$tmp" "$BUILDS_JSON_PATH"
}

# Builds a single stellar_cli_versions entry as JSON.
make_cli_entry() {
  local cli="$1" default_rust="$2" ref="$3"
  shift 3
  local -a rust_versions=("$@")

  # Sort numerically by the bare rust version embedded at the front of
  # each composite key (e.g. 1.94.1-trixie -> [1, 94, 1]) so 1.100.0-trixie
  # lands AFTER 1.99.0-trixie; default jq `sort` on strings would put
  # "1.100.0-..." before "1.99.0-..." lexicographically. Splitting only on
  # "." would feed "1-trixie" into tonumber and fail.
  local rust_array
  rust_array="$(printf '%s\n' "${rust_versions[@]}" \
    | jq -R . \
    | jq -s 'sort_by(split("-") | .[0] | split(".") | map(tonumber))')"

  jq -n \
    --arg default_rust "$default_rust" \
    --argjson rust_versions "$rust_array" \
    --arg ref "$ref" \
    --arg version "$cli" \
    '{default_rust: $default_rust, ref: $ref, rust_versions: $rust_versions, version: $version}'
}

# Builds a JSON object stubbing each rust version to "". Merged INTO
# rust_image_digests with stubs first, so existing pinned values override
# the stub and only blank slots get filled by the subsequent refresh.
make_digest_stubs() {
  printf '%s\n' "$@" | jq -R . | jq -s 'map({(.): ""}) | add'
}

# Picks the next available GitHub Release tag for this cli version.
# Returns v<cli> if no release exists yet, otherwise v<cli>-<N> where N is
# one more than the highest existing iteration.
pick_release_tag() {
  local cli="$1"
  local cli_pat
  cli_pat="$(printf '%s' "$cli" | sed 's/\./\\./g')"

  local existing_tags
  existing_tags="$(gh release list --limit 200 --json tagName --jq '.[].tagName')"

  if ! grep -qE "^v${cli_pat}\$" <<<"$existing_tags"; then
    printf 'v%s\n' "$cli"
    return
  fi

  local max_iter
  max_iter="$(grep -E "^v${cli_pat}-[0-9]+\$" <<<"$existing_tags" \
    | sed -E "s/^v${cli_pat}-//" \
    | sort -n \
    | tail -n1)"

  printf 'v%s-%d\n' "$cli" "$(( ${max_iter:-0} + 1 ))"
}

main "$@"
