#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "[1/4] Python syntax"
python3 -m py_compile __init__.py core.py
if [[ -f dashboard/plugin_api.py ]]; then
  python3 -m py_compile dashboard/plugin_api.py
fi

echo "[2/4] Tests"
bash ci/test.sh

echo "[3/4] Coverage"
bash ci/coverage.sh
uv run --with 'coverage>=7,<8' python - <<'PY2'
from pathlib import Path
import xml.etree.ElementTree as ET
root = ET.parse(Path('coverage.xml')).getroot()
line_rate = float(root.attrib['line-rate']) * 100
print(f'line coverage: {line_rate:.2f}%')
if not line_rate > 95:
    raise SystemExit('coverage must be >95%')
PY2
rm -f .coverage coverage.xml

echo "[4/4] Hermes plugin validation"
hermes plugins validate "$ROOT" --install-deps
