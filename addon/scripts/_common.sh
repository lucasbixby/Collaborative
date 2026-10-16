# shellcheck shell=bash
# Shared helpers for the add-on dev scripts. Sourced, not run directly.

ADDON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ADDON_NAME="collaborative_blender"
# shellcheck disable=SC2034  # used by the scripts that source this file
ADDON_SOURCE="$ADDON_DIR/$ADDON_NAME"

# The Blender to use. Override with:  BLENDER=/path/to/blender scripts/<script>.sh
find_blender() {
  if [[ -n "${BLENDER:-}" ]]; then
    :
  elif [[ -x "/Applications/Blender.app/Contents/MacOS/Blender" ]]; then
    BLENDER="/Applications/Blender.app/Contents/MacOS/Blender"
  elif command -v blender >/dev/null 2>&1; then
    BLENDER="$(command -v blender)"
  else
    echo "Blender not found. Install it from https://www.blender.org/download/ or set BLENDER=/path/to/blender" >&2
    return 1
  fi
  if [[ ! -x "$BLENDER" ]]; then
    echo "BLENDER=$BLENDER is not an executable file" >&2
    return 1
  fi
}

# Prints the installed Blender's major.minor version, e.g. 5.2
blender_version() {
  "$BLENDER" --factory-startup --version 2>/dev/null | sed -n 's/^Blender \([0-9]*\.[0-9]*\).*/\1/p' | head -1
}

# The bpy version pinned for tests, major.minor, e.g. 5.2
pinned_bpy_version() {
  sed -n 's/^bpy==\([0-9]*\.[0-9]*\).*/\1/p' "$ADDON_DIR/requirements-dev.txt"
}

# Blender's per-user add-on folder for a given major.minor version.
user_addons_dir() {
  local version="$1"
  if [[ "$(uname)" == "Darwin" ]]; then
    echo "$HOME/Library/Application Support/Blender/$version/scripts/addons"
  else
    echo "${XDG_CONFIG_HOME:-$HOME/.config}/blender/$version/scripts/addons"
  fi
}
