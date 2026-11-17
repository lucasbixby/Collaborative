// The only bridge between the page and this computer. The page gets these few functions and
// nothing else: no Node, no file paths it didn't get from a dialog, no way to run a program
// other than the Blender chosen in Settings.
const { contextBridge, ipcRenderer } = require('electron')

// Electron wraps a handler's error as "Error invoking remote method '…': Error: <message>";
// the page shows errors to the user, so only the message is passed on.
const call = (channel) => async (argument) => {
  try {
    return await ipcRenderer.invoke(channel, argument)
  } catch (error) {
    throw new Error(String(error.message).replace(/^Error invoking remote method '[^']+': (Error: )?/, ''))
  }
}

contextBridge.exposeInMainWorld('collab', {
  getSettings: call('settings:get'),
  saveSettings: call('settings:save'),
  pickBlendFile: call('pick:blend'),
  pickBlender: call('pick:blender'),
  hostFile: call('room:host-file'),
  launch: call('room:launch'),
  forgetRoom: call('room:forget'),
  notify: (title, body) => ipcRenderer.send('notify', { title, body }),
  onProgress: (listener) => {
    const handler = (_event, message) => listener(message)
    ipcRenderer.on('progress', handler)
    return () => ipcRenderer.removeListener('progress', handler)
  },
})
