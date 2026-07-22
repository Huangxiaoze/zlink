#!/usr/bin/env bash
# Build LeafLink on Linux
# Usage:  bash scripts/build_linux.sh

set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"
if [[ ! -x .venv/bin/python ]]; then
  echo "Creating venv with $PYTHON ..."
  "$PYTHON" -m venv .venv
fi

.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements.txt -r requirements-build.txt
.venv/bin/python scripts/build.py --clean "$@"

echo ""
echo "Output: dist/LeafLink/LeafLink"
