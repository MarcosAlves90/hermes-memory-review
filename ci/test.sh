#!/usr/bin/env bash
set -euo pipefail
uv run \
  --with 'pytest>=8,<10' \
  --with 'fastapi>=0.115,<1' \
  --with 'httpx>=0.27,<1' \
  python -m pytest -q tests --rootdir=tests
