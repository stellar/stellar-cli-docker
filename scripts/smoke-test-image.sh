#!/usr/bin/env bash
# Smoke-test a built image. Verifies that the binary reports the expected
# version, that `contract build --help` works offline, and that the
# org.stellar.* labels carry the values they should.
#
# Exits non-zero on any failure. Prints what's being checked so CI logs are
# useful when something breaks.

source scripts/lib/common.sh

usage() {
  cat <<'EOF'
Usage: scripts/smoke-test-image.sh \
         --image <ref> \
         --stellar-cli-version <v> \
         --rust-version <v> \
         [--help]

Required:
  --image <ref>                Image to test (e.g. stellar-cli:26.0.0-rust1.94.0
                               or a registry digest). Must already be present
                               in the local docker daemon.
  --stellar-cli-version <v>    The stellar-cli version the image should report
                               and label with.
  --rust-version <v>           The rust version the image should label with.

Options:
  --help                       Show this message.

Checks:
  1. `stellar version --only-version` equals --stellar-cli-version.
  2. `stellar contract build --help` exits 0 (no network).
  3. Labels org.stellar.stellar-cli-version, org.stellar.rust-version,
     and org.stellar.wasm-target match expectations.
EOF
}

main() {
  local image="" cli="" rust=""

  while [ $# -gt 0 ]; do
    case "$1" in
      --image)               require_value "$1" "${2:-}"; image="$2"; shift 2;;
      --stellar-cli-version) require_value "$1" "${2:-}"; cli="$2"; shift 2;;
      --rust-version)        require_value "$1" "${2:-}"; rust="$2"; shift 2;;
      -h|--help)             usage; exit 0;;
      *)                     err "unknown argument: $1"; usage; exit 1;;
    esac
  done

  test -n "$image" || { err "--image is required"; usage; exit 1; }
  test -n "$cli"   || { err "--stellar-cli-version is required"; usage; exit 1; }
  test -n "$rust"  || { err "--rust-version is required"; usage; exit 1; }

  preflight_checks jq buildx

  local rc=0
  check_version_output "$image" "$cli" || rc=1
  check_contract_build_help "$image"   || rc=1
  check_labels "$image" "$cli" "$rust" || rc=1

  if [ "$rc" -eq 0 ]; then
    log "smoke-test: image $image passed all checks"
  else
    err "smoke-test: image $image FAILED one or more checks"
  fi
  return "$rc"
}

check_version_output() {
  local image="$1" expected="$2"
  log "checking 'stellar version --only-version' == $expected ..."
  local got
  got="$(docker run --rm "$image" version --only-version)"
  if [ "$got" = "$expected" ]; then
    log "  ok"
    return 0
  fi
  err "  version mismatch: got '$got', expected '$expected'"
  return 1
}

check_contract_build_help() {
  local image="$1"
  log "checking 'stellar contract build --help' runs offline ..."
  if docker run --rm --network=none "$image" contract build --help >/dev/null; then
    log "  ok"
    return 0
  fi
  err "  'contract build --help' failed under --network=none"
  return 1
}

check_labels() {
  local image="$1" cli="$2" rust="$3"
  log "checking org.stellar.* labels ..."

  local labels
  labels="$(docker inspect --format '{{json .Config.Labels}}' "$image")"

  local rc=0
  assert_label "$labels" "org.stellar.stellar-cli-version" "$cli" || rc=1
  assert_label "$labels" "org.stellar.rust-version" "$rust" || rc=1
  assert_label "$labels" "org.stellar.wasm-target" "wasm32v1-none" || rc=1
  if [ "$rc" -eq 0 ]; then
    log "  ok"
  fi
  return "$rc"
}

assert_label() {
  local labels_json="$1" key="$2" want="$3"
  local got
  got="$(jq -r --arg k "$key" '.[$k] // "<missing>"' <<<"$labels_json")"
  if [ "$got" = "$want" ]; then
    return 0
  fi
  err "  label $key: got '$got', expected '$want'"
  return 1
}

main "$@"
