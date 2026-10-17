#!/usr/bin/env bash
# Build the web app and pack the repo at HEAD plus web/dist into dist/bylaw-<sha>.tar.gz.
set -euo pipefail
cd "$(dirname "$0")/.."
sha=$(git rev-parse --short HEAD)
(cd web && npm ci --silent && npm run build --silent)
mkdir -p dist
git archive --format=tar --prefix=bylaw/ HEAD > "dist/bylaw-$sha.tar"
tar --append --file="dist/bylaw-$sha.tar" --transform 's,^web/dist,bylaw/web/dist,' web/dist
gzip -f "dist/bylaw-$sha.tar"
echo "dist/bylaw-$sha.tar.gz"
