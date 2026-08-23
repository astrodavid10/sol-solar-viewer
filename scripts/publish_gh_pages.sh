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

git config user.name  "${GIT_AUTHOR_NAME:-sol-bot}"
git config user.email "${GIT_AUTHOR_EMAIL:-sol-bot@users.noreply.github.com}"

git fetch --depth=1 origin "$BR" || true
rm -rf .ghp && mkdir .ghp
if git rev-parse --verify -q "origin/$BR" >/dev/null; then
  # Materialise the existing published tree so the half we do NOT own survives.
  git --work-tree=.ghp checkout "origin/$BR" -- . 2>/dev/null || true
fi

mkdir -p ".ghp/${DEST}"
if [ -n "$DEST" ]; then
  rsync -a --delete "$SRC"/ ".ghp/${DEST}/"
else
  rsync -a --delete --exclude 'data/' "$SRC"/ .ghp/
fi
touch .ghp/.nojekyll

cd .ghp
git init -q
git add -A
git commit -q -m "publish ${DEST:-app} @ $(date -u +%FT%TZ) [${GITHUB_SHA:0:7}]"
git push -q --force \
  "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" \
  HEAD:"$BR"
