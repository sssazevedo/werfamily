#!/usr/bin/env bash
set -euo pipefail
docker compose -f deploy/docker-compose.yml up --build
