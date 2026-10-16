#!/usr/bin/env bash
# One-time setup for add-on development.
#
#   addon/scripts/setup_dev.sh
#
# Creates addon/.venv (Python 3.13) with the real Blender module (bpy) for headless
# tests, type stubs for VS Code, pytest and ruff, then runs the test suite once.
# Safe to re-run; it updates the existing environment.
set -euo pipefail
# shellcheck source=_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
cd "$ADDON_DIR"

PY_VERSION="3.13"   # must match the Python that the pinned bpy wheel is built for

echo "==> Creating addon/.venv with Python $PY_VERSION"
if command -v uv >/dev/null 2>&1; then
  uv venv --allow-existing --python "$PY_VERSION" .venv
  echo "==> Installing dev dependencies (bpy is ~900 MB, the first run takes a while)"
  VIRTUAL_ENV="$ADDON_DIR/.venv" uv pip install -r requirements-dev.txt
else
  if command -v "python$PY_VERSION" >/dev/null 2>&1; then
    [[ -d .venv ]] || "python$PY_VERSION" -m venv .venv
  elif command -v conda >/dev/null 2>&1; then
    [[ -d .venv ]] || conda create --yes --quiet --prefix .venv "python=$PY_VERSION" pip
  else
    cat >&2 <<EOF
Python $PY_VERSION is needed. Install one of these, then re-run this script:
  brew install uv           (recommended; uv downloads Python $PY_VERSION itself)
  brew install python@$PY_VERSION
EOF
    exit 1
  fi
  echo "==> Installing dev dependencies (bpy is ~900 MB, the first run takes a while)"
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements-dev.txt
fi

echo "==> Checking your Blender install"
if find_blender; then
  installed="$(blender_version)"
  pinned="$(pinned_bpy_version)"
  echo "    Blender $installed at $BLENDER"
  if [[ "$installed" != "$pinned" ]]; then
    echo "    WARNING: tests use Blender $pinned (bpy) but you have $installed installed."
    echo "    Install Blender $pinned so manual testing and automated tests match."
  fi
else
  echo "    WARNING: Blender not found; headless tests still work, manual testing needs it."
fi

echo "==> Running the add-on tests"
.venv/bin/python -m pytest -q

cat <<EOF

Done. Next:
  addon/scripts/link_addon.sh      make your Blender load the add-on from this repo
  addon/scripts/blender.sh         start Blender with output in the terminal
  addon/.venv/bin/pytest           run the tests (from the addon/ folder)
EOF
