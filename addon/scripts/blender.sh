#!/usr/bin/env bash
# Start Blender with the add-on's output in this terminal.
#
#   addon/scripts/blender.sh                one Blender
#   addon/scripts/blender.sh --two          two Blenders, A and B, for testing sync
#   addon/scripts/blender.sh scene.blend    extra arguments go to Blender
#
# print() from the add-on goes to the terminal that started Blender, not to Blender's
# Python console. Each instance gets COLLAB_CLIENT=A/B (see collaborative_blender/log.py),
# so with --two you can tell the two clients' log lines apart.
# Run link_addon.sh once first so Blender loads the add-on from this repo.
set -euo pipefail
# shellcheck source=_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
find_blender

if [[ "${1:-}" == "--two" ]]; then
  shift
  COLLAB_CLIENT=A "$BLENDER" "$@" &
  pid_a=$!
  COLLAB_CLIENT=B "$BLENDER" "$@" &
  pid_b=$!
  # Ctrl+C closes both.
  trap 'kill $pid_a $pid_b 2>/dev/null' INT TERM
  wait
else
  COLLAB_CLIENT="${COLLAB_CLIENT:-A}" exec "$BLENDER" "$@"
fi
