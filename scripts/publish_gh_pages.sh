#!/usr/bin/env bash
# Publish a directory into the gh-pages branch as a single orphan commit.
#
# usage: publish_gh_pages.sh <src-dir> <dest-subdir-in-gh-pages | "">
#
#   publish_gh_pages.sh dist-data data   # data.yml: replaces gh-pages:/data/
#   publish_gh_pages.sh dist ""          # app-deploy.yml: root, keeps /data/
#
# Why a forced orphan commit: the data job runs 6x/day and each run pushes
# ~1.5 MB of near-incompressible binary frames.  Keeping history would add
# several GB/year to every clone of the repo.  gh-pages therefore stays at
# exactly one commit forever; the regenerable data plus the workflow's
# upload-artifact retention IS the audit trail.
#
# Both workflows share `concurrency: {group: gh-pages-publish}` so an app
# deploy and a data publish can never interleave their checkouts.
set -euo pipefail

SRC="$1"; DEST="${2:-}"
BR=gh-pages

# Identity via the ENVIRONMENT, not `git config`. The commit below is made in a
# throwaway repo created by `git init` in .ghp, which inherits nothing from this
# one -- an earlier version configured the identity here and then failed every
# publish with "Author identity unknown", because Actions runners have no global
# git identity and the config had been written to the wrong repository.
export GIT_AUTHOR_NAME="${GIT_AUTHOR_NAME:-sol-bot}"
export GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL:-sol-bot@users.noreply.github.com}"
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME"
export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"

# First publish into a fresh repo has no gh-pages yet; that is the bootstrap
# case, not an error. Swallow the expected "couldn't find remote ref" so the log
# does not read like a failure when it is the normal first run.
git fetch --depth=1 origin "$BR" 2>/dev/null || echo "no $BR yet — bootstrapping it"
rm -rf .ghp && mkdir .ghp
if git rev-parse --verify -q "origin/$BR" >/dev/null; then
  # Materialise the existing published tree so the half we do NOT own survives.
  git --work-tree=.ghp checkout "origin/$BR" -- . 2>/dev/null || true
  # `git --work-tree=X checkout ref -- path` ALSO stages every one of those paths
  # into THIS repo's index (footgun 31 notes the same trap in data.yml). Harmless
  # on a throwaway runner; on a workstation it leaves ~60 phantom "AD" entries in
  # `git status` that look like the app has been deleted. Undo it here rather
  # than in each caller, so a hand-publish is as clean as a CI one.
  git reset -q || true
fi

# rsync where it exists (every CI runner), a portable equivalent where it does
# not. This matters because publishing BY HAND FROM A WORKSTATION is a normal
# operation for this project, not an emergency: GONG is unreachable from GitHub
# runners (footgun 33), so the field-line frames have always been built locally
# and pushed from here -- and Git Bash on Windows ships no rsync, so the script
# failed at exactly the step it exists for. `--delete` semantics are the part
# that has to be preserved: the destination must END UP as a copy of the source,
# not a union with whatever was published before.
copy_tree() {   # copy_tree <src> <dst>
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete "$1"/ "$2"/
  else
    rm -rf "$2"
    mkdir -p "$2"
    cp -R "$1"/. "$2"/
  fi
}

mkdir -p ".ghp/${DEST}"
if [ -n "$DEST" ]; then
  copy_tree "$SRC" ".ghp/${DEST}"
else
  # Root publish: the app owns everything EXCEPT data/, which the data job owns.
  # Without rsync's --exclude that means copying into place and then restoring
  # the data tree we just clobbered, so keep it aside first.
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete --exclude 'data/' "$SRC"/ .ghp/
  else
    rm -rf .ghp-data-keep
    if [ -d .ghp/data ]; then mv .ghp/data .ghp-data-keep; fi
    find .ghp -mindepth 1 -maxdepth 1 ! -name '.git' -exec rm -rf {} +
    cp -R "$SRC"/. .ghp/
    rm -rf .ghp/data
    if [ -d .ghp-data-keep ]; then mv .ghp-data-keep .ghp/data; fi
  fi
fi
touch .ghp/.nojekyll

cd .ghp
git init -q
git add -A
git commit -q -m "publish ${DEST:-app} @ $(date -u +%FT%TZ) [${GITHUB_SHA:0:7}]"

# Authenticate with a per-invocation `http.extraheader` over a PLAIN remote
# URL -- never `https://x-access-token:${GITHUB_TOKEN}@github.com/...`, which
# is what this line used to be. git echoes the remote URL VERBATIM in its own
# failure messages ("fatal: Authentication failed for 'https://.../'", and
# every redirect/proxy warning), so an embedded token is one bad push away
# from the log. Actions masks `secrets.GITHUB_TOKEN`, but publishing BY HAND
# from a workstation is a normal operation here (PFSS-UPDATE.md: GONG is
# unreachable from runners, footgun 33) and it runs with
# GITHUB_TOKEN="$(gh auth token)" where nothing masks anything.
# git never echoes a `-c` value, and `-c` is scoped to this one invocation --
# it reaches neither .git/config nor the reflog. Same approach as
# actions/checkout and `scripts/gong_mirror.py:_push`.
#
# `base64` wraps at 76 columns by default on Git Bash AND on ubuntu-latest, so
# a long token yields a multi-line header: measured, a 200-char token base64s
# to 3 lines. `tr -d '\n'` is load-bearing, not tidying.
#
# $GITHUB_TOKEN is still expanded bare, so `set -u` aborts a run that has no
# token exactly as it did before (the same property `${GITHUB_SHA:0:7}` above
# relies on) rather than pushing anonymously and failing more obscurely.
# GIT_TERMINAL_PROMPT=0 so a bad or expired token fails in ~1 s instead of
# blocking on a credential prompt nobody is watching.
GHP_AUTH="AUTHORIZATION: basic $(
  printf 'x-access-token:%s' "$GITHUB_TOKEN" | base64 | tr -d '\n')"
GIT_TERMINAL_PROMPT=0 git -c http.extraheader="$GHP_AUTH" \
  push -q --force \
  "https://github.com/${GITHUB_REPOSITORY}.git" \
  HEAD:"$BR"
