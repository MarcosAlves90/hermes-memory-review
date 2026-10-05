#!/usr/bin/env bash
set -euo pipefail
uv run --with 'pytest>=8,<10' python -m pytest -q tests --rootdir=tests
