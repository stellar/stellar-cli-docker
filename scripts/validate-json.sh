#!/usr/bin/env bash
# Validate every *.json file in the repo:
#   1. Object keys are sorted alphabetically at every level.
#   2. builds.json conforms to builds.schema.json (draft-2020-12).
#   3. Cross-field constraints in builds.json that JSON Schema can't express
#      (default_rust must appear in rust_versions; rust_versions entries
#      must be keys in rust_image_digests; variants[].rust_version too).
#
# Exits 0 on success, 1 on any failure. Prints a useful diff on key-order
# failures.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$script_dir/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/validate-json.sh [--help]

Validates every *.json file in the repo (excluding common machine-generated
paths under node_modules/, target/, .git/) for sorted keys, then validates
builds.json against builds.schema.json and its cross-field constraints.

Requires:
  - jq
  - check-jsonschema (pipx install check-jsonschema)

Exit codes:
  0  all checks passed
  1  one or more checks failed
EOF
}

main() {
  case "${1:-}" in
    -h|--help) usage; exit 0;;
    "") :;;
    *) err "unknown argument: $1"; usage; exit 1;;
  esac

  require_cmd jq check-jsonschema

  local rc=0

  check_sorted_keys || rc=1
  check_schema || rc=1
  check_cross_field_constraints || rc=1

  if [ "$rc" -eq 0 ]; then
    log "validate-json: all checks passed"
  fi
  return "$rc"
}

# Lists every *.json file we care about. Done as a function so callers can
# `read -r` over it without quoting headaches.
list_json_files() {
  local root
  root="$(repo_root)"
  find "$root" \
    -type d \( -name node_modules -o -name target -o -name .git \) -prune -o \
    -type f -name '*.json' -print
}

check_sorted_keys() {
  local rc=0
  local file
  local rel
  while IFS= read -r file; do
    rel="${file#"$(repo_root)/"}"
    # Detect parse errors first so a malformed file doesn't get reported as
    # an "unsorted keys" failure.
    if ! jq -e . "$file" >/dev/null 2>&1; then
      err "$rel: invalid JSON"
      jq . "$file" 2>&1 | sed 's/^/    /' >&2 || true
      rc=1
      continue
    fi
    if ! jq -e 'def walk_sorted:
                  if type == "object"
                  then (keys == keys_unsorted)
                       and ([.[] | walk_sorted] | all)
                  elif type == "array"
                  then ([.[] | walk_sorted] | all)
                  else true
                  end;
                walk_sorted' "$file" >/dev/null; then
      err "$rel: object keys are not alphabetically sorted at every level"
      print_sort_diff "$file" >&2
      rc=1
    fi
  done < <(list_json_files)
  return "$rc"
}

# Prints a unified diff from the file as-is to the file with every object's
# keys sorted. Reads as "remove these (-) and add these (+)" so the offending
# nesting is easy to find.
print_sort_diff() {
  local file="$1"
  diff -u \
    <(jq . "$file") \
    <(jq --sort-keys . "$file") \
    | sed 's/^/    /' \
    || true
}

check_schema() {
  if check-jsonschema --schemafile "$BUILDS_SCHEMA_PATH" "$BUILDS_JSON_PATH"; then
    return 0
  else
    err "builds.json failed JSON Schema validation"
    return 1
  fi
}

check_cross_field_constraints() {
  local rc=0

  # default_rust must appear in the same entry's rust_versions.
  local bad_default
  bad_default="$(builds_json '
    .stellar_cli_versions[]
    | . as $e
    | select($e.rust_versions | index($e.default_rust) | not)
    | .version')"
  if [ -n "$bad_default" ]; then
    while IFS= read -r v; do
      err "stellar_cli_versions(version=$v).default_rust is not in its rust_versions"
    done <<<"$bad_default"
    rc=1
  fi

  # Every rust version referenced by a cli entry must be a key in
  # rust_image_digests.
  local unknown
  unknown="$(builds_json '
    . as $b
    | [.stellar_cli_versions[] | .rust_versions[]]
    | unique
    | map(select($b.rust_image_digests[.] == null))
    | .[]')"
  if [ -n "$unknown" ]; then
    while IFS= read -r r; do
      err "rust version '$r' is referenced by a cli entry but missing from rust_image_digests"
    done <<<"$unknown"
    rc=1
  fi

  # Same check for variants[].rust_version.
  local unknown_var
  unknown_var="$(builds_json '
    . as $b
    | [.variants[]? | .rust_version]
    | unique
    | map(select($b.rust_image_digests[.] == null))
    | .[]')"
  if [ -n "$unknown_var" ]; then
    while IFS= read -r r; do
      err "rust version '$r' is referenced by a variant but missing from rust_image_digests"
    done <<<"$unknown_var"
    rc=1
  fi

  return "$rc"
}

main "$@"
