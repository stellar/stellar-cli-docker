#!/usr/bin/env bash
# Verify that a published stellar-cli image has both attestation chains —
# SLSA build provenance and SPDX SBOM — signed by this repo's GitHub
# Actions OIDC identity.
#
# Intended for SEP-58 verifiers and any consumer about to record a `bldimg`
# digest. Reports cleanly per chain so a partial failure is easy to read.

script_dir="$(CDPATH='' builtin cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$script_dir/lib/common.sh"

DEFAULT_REPO=stellar/stellar-cli-docker
PROVENANCE_PREDICATE_TYPE=https://slsa.dev/provenance/v1
SBOM_PREDICATE_TYPE=https://spdx.dev/Document

usage() {
  cat <<EOF
Usage: scripts/verify-image.sh --image <ref> [--repo <slug>] [--help]

Required:
  --image <ref>   Full image reference, pinned to a per-arch digest.
                  e.g. docker.io/stellar/stellar-cli@sha256:abc...
                  A tag-only reference (no @sha256:...) is rejected; the
                  point of verification is to prove a specific digest.

Options:
  --repo <slug>   GitHub repository slug (owner/repo) whose Actions OIDC
                  identity signed the attestation. Default: ${DEFAULT_REPO}.
                  Override when verifying an image published from a fork.
  --help          Show this message.

Runs two \`gh attestation verify\` calls against the published image, one for
each predicate type. Both must succeed for the verification to pass.

Requires the \`gh\` CLI to be installed and authenticated.
EOF
}

main() {
  local image="" repo="$DEFAULT_REPO"

  while [ $# -gt 0 ]; do
    case "$1" in
      --image)   require_value "$1" "${2:-}"; image="$2"; shift 2;;
      --repo)    require_value "$1" "${2:-}"; repo="$2"; shift 2;;
      -h|--help) usage; exit 0;;
      *)         err "unknown argument: $1"; usage; exit 1;;
    esac
  done

  test -n "$image" || { err "--image is required"; usage; exit 1; }

  # Reject tag-only references — verifying a tag is meaningless because the
  # tag could be re-pointed. The whole verification flow rests on the digest.
  case "$image" in
    *@sha256:*) :;;
    *) die "image must be pinned to a sha256 digest (e.g. <repo>@sha256:...); got '$image'";;
  esac

  preflight_checks gh

  local oci_ref="oci://${image}"
  local rc=0

  log "verifying $image against $repo ..."

  log ""
  log "[1/2] SLSA build provenance"
  if gh attestation verify "$oci_ref" \
      --repo "$repo" \
      --predicate-type "$PROVENANCE_PREDICATE_TYPE"; then
    log "  ok"
  else
    err "  FAILED: build provenance did not verify"
    rc=1
  fi

  log ""
  log "[2/2] SPDX SBOM"
  if gh attestation verify "$oci_ref" \
      --repo "$repo" \
      --predicate-type "$SBOM_PREDICATE_TYPE"; then
    log "  ok"
  else
    err "  FAILED: SBOM did not verify"
    rc=1
  fi

  log ""
  if [ "$rc" -eq 0 ]; then
    log "verify-image: $image passed all attestation checks"
  else
    err "verify-image: $image FAILED one or more attestation checks"
  fi
  return "$rc"
}

main "$@"
