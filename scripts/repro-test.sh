#!/usr/bin/env bash
# Verify WASM reproducibility: clone an upstream contracts repo at a pinned
# revision, then for each named contract subdir build twice inside the
# image and confirm the .wasm artifacts are byte-identical.
#
# Defaults to stellar/soroban-examples@v23.0.0 and three representative
# contracts. Cloning at CI time (rather than vendoring) mirrors how a real
# consumer uses the image — git clone their contracts, docker run the
# build. Same-arch only; cross-arch byte equality is not promised.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$script_dir/lib/common.sh"

DEFAULT_REPO=https://github.com/stellar/soroban-examples.git
DEFAULT_REV=v23.0.0
DEFAULT_CONTRACTS=(token liquidity_pool atomic_swap)

# Script-level state read by the EXIT trap, since `local` vars in main()
# are gone by the time the trap fires.
image=""
workdir=""
keep=0

usage() {
  cat <<EOF
Usage: scripts/repro-test.sh --image <ref> [options] [--help]

Required:
  --image <ref>          Image to test (e.g. stellar-cli:26.0.0-rust1.94.0
                         or docker.io/stellar/stellar-cli@sha256:...).

Options:
  --repo <url>           Git repo to clone. Default: ${DEFAULT_REPO}
  --rev <ref>            Git ref to check out. Default: ${DEFAULT_REV}
  --contract <name>      Contract subdirectory under the cloned repo to
                         test. Pass multiple times to add more.
                         Default: ${DEFAULT_CONTRACTS[*]}
  --keep-workdir         Don't remove the temp checkout on exit (debug).
  --help                 Show this message.

For each contract, builds twice in fresh containers (target/ wiped
between builds) and compares the sha256 of the resulting .wasm.
EOF
}

main() {
  local repo="$DEFAULT_REPO" rev="$DEFAULT_REV"
  local -a contracts=()

  while [ $# -gt 0 ]; do
    case "$1" in
      --image)        image="$2"; shift 2;;
      --repo)         repo="$2"; shift 2;;
      --rev)          rev="$2"; shift 2;;
      --contract)     contracts+=("$2"); shift 2;;
      --keep-workdir) keep=1; shift;;
      -h|--help)      usage; exit 0;;
      *)              err "unknown argument: $1"; usage; exit 1;;
    esac
  done

  test -n "$image" || { err "--image is required"; usage; exit 1; }
  if [ "${#contracts[@]}" -eq 0 ]; then
    contracts=("${DEFAULT_CONTRACTS[@]}")
  fi

  preflight_checks git buildx

  workdir="$(mktemp -d -t repro-test.XXXXXXXX)"
  trap cleanup EXIT

  log "cloning $repo @ $rev into $workdir ..."
  git -C "$workdir" init -q
  git -C "$workdir" remote add origin "$repo"
  git -C "$workdir" fetch --depth=1 origin "$rev" -q
  git -C "$workdir" checkout -q FETCH_HEAD

  local rc=0
  local c
  for c in "${contracts[@]}"; do
    test_one_contract "$image" "$workdir" "$c" || rc=1
  done

  if [ "$rc" -eq 0 ]; then
    log ""
    log "repro-test: all ${#contracts[@]} contracts produce stable WASM"
  else
    err ""
    err "repro-test: one or more contracts FAILED reproducibility"
  fi
  return "$rc"
}

test_one_contract() {
  local image="$1" workdir="$2" name="$3"
  local contract_dir="$workdir/$name"

  log ""
  log "=== $name ==="

  test -d "$contract_dir" \
    || { err "no contract directory at $contract_dir"; return 1; }
  test -f "$contract_dir/Cargo.toml" \
    || { err "$name/Cargo.toml missing"; return 1; }
  test -f "$contract_dir/Cargo.lock" \
    || { err "$name/Cargo.lock missing (required for --locked builds)"; return 1; }

  local hash_a hash_b
  hash_a="$(build_and_hash "$image" "$contract_dir")" || return 1
  log "  build A: $hash_a"
  hash_b="$(build_and_hash "$image" "$contract_dir")" || return 1
  log "  build B: $hash_b"

  if [ "$hash_a" = "$hash_b" ]; then
    log "  ok — reproducible"
    return 0
  fi
  err "  WASM hash mismatch — build is NOT reproducible"
  return 1
}

# Remove the cloned workdir on EXIT. Files inside may be root-owned by the
# container builds; use docker to wipe them so this works on Linux CI too,
# falling back to a host rm if docker isn't reachable.
cleanup() {
  if [ "$keep" -eq 1 ]; then
    log "keeping workdir on exit: $workdir"
    return
  fi
  if [ -n "$workdir" ] && [ -d "$workdir" ]; then
    if [ -n "$image" ]; then
      docker run --rm --entrypoint sh -v "$workdir:/work" "$image" \
        -c 'find /work -mindepth 1 -delete' >/dev/null 2>&1 \
        || rm -rf "$workdir" 2>/dev/null \
        || true
    else
      rm -rf "$workdir" 2>/dev/null || true
    fi
    rmdir "$workdir" 2>/dev/null || true
  fi
}

# Build the contract and print the sha256 of the produced .wasm.
# Cleans /source/target before building so each call starts cold.
build_and_hash() {
  local image="$1" contract_dir="$2"
  docker run --rm \
    --entrypoint sh \
    -v "$contract_dir:/source" \
    "$image" \
    -c '
      set -e
      rm -rf /source/target
      /usr/local/bin/stellar contract build --locked >&2
      sha256sum /source/target/wasm32v1-none/release/*.wasm | awk "{print \$1}"
    '
}

main "$@"
