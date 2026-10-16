#!/usr/bin/env bash
# Make your installed Blender load the add-on straight from this repo.
#
#   addon/scripts/link_addon.sh            link and enable
#   addon/scripts/link_addon.sh --unlink   remove the link
#
# Creates a symlink in Blender's per-user add-on folder pointing at
# addon/collaborative_blender, then enables the add-on in your preferences. After this,
# edits in VS Code take effect in Blender after F3 > "Reload Scripts" (or automatically,
# if you start Blender through the VS Code extension with reload-on-save).
set -euo pipefail
# shellcheck source=_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

find_blender
version="$(blender_version)"
addons_dir="$(user_addons_dir "$version")"
link="$addons_dir/$ADDON_NAME"

if [[ "${1:-}" == "--unlink" ]]; then
  if [[ -L "$link" ]]; then
    rm "$link"
    echo "Removed $link"
  else
    echo "Nothing to remove at $link"
  fi
  exit 0
fi

mkdir -p "$addons_dir"
if [[ -e "$link" && ! -L "$link" ]]; then
  echo "A real folder already exists at:" >&2
  echo "  $link" >&2
  echo "It is probably an installed copy of the add-on. Remove it in Blender" >&2
  echo "(Preferences > Add-ons > Collaborative > Remove), then re-run this script." >&2
  exit 1
fi
ln -sfn "$ADDON_SOURCE" "$link"
echo "Linked $link -> $ADDON_SOURCE"

echo "Enabling the add-on in Blender $version preferences..."
"$BLENDER" --background --python-expr "
import bpy, addon_utils
module = addon_utils.enable('$ADDON_NAME', default_set=True)
if module is None:
    raise SystemExit('Blender could not enable the add-on; see the error above.')
bpy.ops.wm.save_userpref()
" >/dev/null
echo "Done. Start Blender and look for the Collaborative tab in the 3D viewport sidebar (N)."
