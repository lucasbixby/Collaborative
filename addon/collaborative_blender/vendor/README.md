# Vendored libraries

Blender's bundled Python has no WebSocket library, and an add-on can't rely on users
having run `pip install` for it, so the library ships inside the add-on instead (#12).

| Package | Version | Source | License |
|---|---|---|---|
| [`websocket-client`](https://github.com/websocket-client/websocket-client) | 1.9.2 | [PyPI](https://pypi.org/project/websocket-client/1.9.2/) (`websocket_client-1.9.2-py3-none-any.whl`) | Apache-2.0 (`vendor/websocket/LICENSE`) |

`websocket/` is the wheel's `websocket` package unmodified, minus its `tests/` folder
(not needed at runtime). All of its internal imports are relative (`from ._core import
...`), so `from .vendor import websocket` in `client.py` works with no `sys.path`
changes — which also means it can't clash with another add-on's own copy of the same
library.

Excluded from `ruff` (`server`'s and `addon`'s configs don't lint code we didn't write)
and from the type checker (`pyrightconfig.json`).

To update: download the new version's wheel (`pip download websocket-client==<version>
--no-deps`), unzip it, and replace `websocket/` with its `websocket/` folder (again minus
`tests/`), carrying over the new `LICENSE`. Update the version in this table.
