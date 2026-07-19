#!/usr/bin/env sh
set -eu

command -v docker >/dev/null 2>&1 || {
  echo "Docker is not installed or is not available in PATH." >&2
  exit 1
}

docker compose up --build
