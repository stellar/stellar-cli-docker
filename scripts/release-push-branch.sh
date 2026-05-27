#!/usr/bin/env bash
# Commit the staged builds.json and push the release branch. Refuses to
# clobber an in-progress review PR; force-pushes orphan branches left
# over from a prior failed run; pushes fresh otherwise.

source scripts/lib/common.sh

usage() {
  cat <<'EOF'
Usage: scripts/release-push-branch.sh --release-tag <tag>

Required:
  --release-tag <tag>   Release tag for the branch and commit message.
EOF
}

main() {
  preflight_checks gh git

  local release_tag=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --release-tag) require_value "$1" "${2:-}"; release_tag="$2"; shift 2;;
      -h|--help)     usage; exit 0;;
      *)             die "unknown argument: $1";;
    esac
  done
  test -n "$release_tag" || die "--release-tag is required"

  local branch="release/${release_tag}"

  git add builds.json
  git commit -m "Release ${release_tag}."

  # Three re-dispatch cases for the same release_tag:
  #   - fresh: branch doesn't exist on remote → normal push
  #   - orphan: branch exists, no open PR (prior run failed after push
  #     but before PR creation) → force-push to overwrite
  #   - open PR: branch exists with a live PR → bail, don't clobber
  local push_args=()
  if git ls-remote --exit-code --heads origin "$branch" >/dev/null 2>&1; then
    # Explicit check: a transient gh failure here must not silently flow
    # into the orphan-recovery branch and force-push over live work.
    local open_pr
    if ! open_pr="$(gh pr list --head "$branch" --state open --json number --jq '.[0].number')"; then
      printf '::error::failed to check for open PRs on %s — refusing to push\n' "$branch"
      exit 1
    fi
    if [ -n "$open_pr" ]; then
      printf '::error::%s already has an open PR (#%s). Close it or pick a different version.\n' \
        "$branch" "$open_pr"
      exit 1
    fi
    printf '::warning::%s exists on remote with no open PR (orphan from a prior failed run); force-pushing.\n' \
      "$branch"
    push_args=(--force)
  fi

  git push "${push_args[@]}" origin "$branch"
}

main "$@"
