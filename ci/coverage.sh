#!/usr/bin/env bash
set -euo pipefail
rm -f .coverage coverage.xml
uv run --with 'pytest>=8,<10' --with 'coverage>=7,<8' python -m coverage run --branch -m pytest -q tests --rootdir=tests
uv run --with 'coverage>=7,<8' python -m coverage xml -o coverage.xml
