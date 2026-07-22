#!/usr/bin/env bash
# Build LeafLink on Ubuntu/Debian and produce an installable .deb
#
# Usage (from repo root `remote/`):
#   bash scripts/build_deb.sh
#   bash scripts/build_deb.sh --console          # keep terminal for debug
#   DEB_ONLY=1 bash scripts/build_deb.sh        # reuse existing dist/LeafLink
#
# Output:
#   dist/LeafLink/LeafLink
#   dist/leaflink_<version>_<arch>.deb
#
# Install:
#   sudo apt install ./dist/leaflink_*.deb
#   # or
#   sudo dpkg -i ./dist/leaflink_*.deb && sudo apt-get install -f -y

set -euo pipefail
cd "$(dirname "$0")/.."

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "ERROR: build_deb.sh must run on Linux (Ubuntu/Debian)." >&2
  exit 1
fi

if ! command -v dpkg-deb >/dev/null 2>&1; then
  echo "dpkg-deb not found. Install with:"
  echo "  sudo apt update && sudo apt install -y dpkg-dev"
  exit 1
fi

PYTHON="${PYTHON:-python3}"
if [[ ! -x .venv/bin/python ]]; then
  echo "Creating venv with $PYTHON ..."
  "$PYTHON" -m venv .venv
fi

.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements.txt -r requirements-build.txt

# Prefer Ubuntu 18.04 deps file when present and PySide2 is desired.
if [[ -f requirements-ubuntu1804.txt ]]; then
  .venv/bin/python -m pip install -r requirements-ubuntu1804.txt || true
fi

if [[ "${DEB_ONLY:-0}" == "1" ]]; then
  .venv/bin/python scripts/build.py --deb-only "$@"
else
  .venv/bin/python scripts/build.py --clean --deb "$@"
fi

echo ""
echo "App    : dist/LeafLink/LeafLink"
echo "Package: dist/leaflink_*.deb"
ls -lh dist/leaflink_*.deb 2>/dev/null || true
