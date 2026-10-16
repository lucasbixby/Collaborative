"""Apply remote operations to the local scene without re-sending them.

Sets a guard while applying so detect.py ignores the resulting depsgraph updates,
and drops any operation whose origin ID is this client's own.
"""

# TODO: apply(operation) for transforms, create, delete.
