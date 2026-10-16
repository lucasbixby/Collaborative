"""Logging for the add-on.

Output goes to the terminal that started Blender. Each line is tagged with the client
name from COLLAB_CLIENT (set by scripts/blender.sh), so two Blenders started with
`blender.sh --two` can share one terminal.
"""

import os
import time

CLIENT = os.environ.get("COLLAB_CLIENT", "-")


def log(*parts: object) -> None:
    stamp = time.strftime("%H:%M:%S")
    # flush so lines appear immediately even when Blender's output is piped or redirected
    print(f"[collab {CLIENT} {stamp}]", *parts, flush=True)
