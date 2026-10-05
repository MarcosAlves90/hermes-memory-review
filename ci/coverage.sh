#!/usr/bin/env bash
set -euo pipefail
rm -f .coverage coverage.xml
uv run \
  --with 'pytest>=8,<10' \
  --with 'coverage>=7,<8' \
  --with 'fastapi>=0.115,<1' \
  --with 'httpx>=0.27,<1' \
  python -m coverage run --branch -m pytest -q tests --rootdir=tests
uv run --with 'coverage>=7,<8' python -m coverage xml -o coverage.xml
