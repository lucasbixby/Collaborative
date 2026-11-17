"""Logging for the add-on, to the terminal that started Blender. Each line is tagged with
COLLAB_CLIENT (A / B), so two Blenders can share one terminal."""

import os
import time

CLIENT = os.environ.get("COLLAB_CLIENT", "-")


def log(*parts: object) -> None:
    stamp = time.strftime("%H:%M:%S")
    # flush so lines appear immediately even when Blender's output is piped or redirected
    print(f"[collab {CLIENT} {stamp}]", *parts, flush=True)
