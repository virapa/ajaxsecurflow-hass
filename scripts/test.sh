#!/usr/bin/env bash
# Runs the test suite inside the Docker test image. Usage: scripts/test.sh [pytest args]
set -euo pipefail
cd "$(dirname "$0")/.."
IMAGE=ajaxsecurflow-hass-test
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  docker build -f Dockerfile.test -t "$IMAGE" .
fi
# MSYS_NO_PATHCONV keeps Git Bash from mangling the /app mount path on Windows.
MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W 2>/dev/null || pwd):/app" -w /app "$IMAGE" python -m pytest "$@"
