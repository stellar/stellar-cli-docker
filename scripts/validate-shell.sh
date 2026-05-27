#!/usr/bin/env bash
# Validate that every top-level shell script in scripts/ inherits the
# project's safe shell options by sourcing scripts/lib/common.sh, and
# that common.sh itself declares those options. Without this check, a
# new script could silently regress to bash defaults and let `$(...)`
# failures be swallowed under set -e.

source scripts/lib/common.sh

main() {
  local failed=0
  local common=scripts/lib/common.sh

  grep -qE '^set -euo pipefail$' "$common" \
    || { err "$common is missing: set -euo pipefail"; failed=1; }
  grep -qE '^shopt -s inherit_errexit$' "$common" \
    || { err "$common is missing: shopt -s inherit_errexit"; failed=1; }

  local script
  for script in scripts/*.sh; do
    grep -qE '^source scripts/lib/common\.sh$' "$script" \
      || { err "$script does not source scripts/lib/common.sh"; failed=1; }
  done

  test "$failed" -eq 0 || die "shell validation failed"
  log "validate-shell: all checks passed"
}

main "$@"
