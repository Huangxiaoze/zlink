#!/usr/bin/env bash
# Build ZLink.app on macOS
# Usage:  bash scripts/build_macos.sh
# Note: Accessibility permission is still required for input injection at runtime.

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
if [[ -d dist/ZLink.app ]]; then
  echo "Output: dist/ZLink.app"
else
  echo "Output: dist/ZLink/ZLink"
fi
