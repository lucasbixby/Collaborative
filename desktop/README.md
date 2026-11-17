# The Collaborative app

An Electron window around the web UI (`../web`), plus what a web page can't do.

| File | Role |
|---|---|
| `main.cjs` | The window, the `app://` protocol that serves the UI, and the handlers below |
| `preload.cjs` | The bridge the page sees as `window.collab` (typed in `web/src/platform.ts`) |
| `lib/settings.cjs` | Server address, Blender's location, and each hosted room's file, in one JSON file |
| `lib/blender.cjs` | Finding Blender; the command that starts it in a room |
| `lib/files.cjs` | Uploading and downloading a room's project file, with a content check |
| `lib/launch.cjs` | Launch: get the right file in place, then start Blender |
| `blender/launch.py` | Run by Blender at startup: loads the add-on from `../addon` for that session |

```bash
npm install
npm start        # builds ../web, then opens the app
npm test         # the lib/ logic, with a fake server and a stand-in for Blender; no Electron needed
```

## What the page can and can't do

The page runs sandboxed, with no Node. Through the bridge it can ask for a file dialog, upload a file the dialog returned (by a handle, never a path), launch Blender into a room, and read and set the server address. It can't name a path, and Blender's location is only ever set from a dialog, so the page can't make the app run some other program. Everything it sends for a launch is checked first (`lib/launch.cjs`).

## Where things are kept

In the app's user-data folder (`~/Library/Application Support/Collaborative` on macOS): `settings.json`, and `rooms/<server>/<room>/` with the downloaded copy of each joined room's file. A guest's copy is a cache: it's replaced whenever it differs from the server's.

The room and the login token reach Blender in environment variables, not arguments, which other programs can read.

## Not done

- **Packaging.** There's no installer yet; run it with `npm start`. A packaged build must ship `blender/launch.py` and `../addon/collaborative_blender` as plain files (outside the asar archive), since Blender reads them.
- **Windows and Linux** are handled in `lib/blender.cjs` but only macOS paths and Linux have been exercised.
