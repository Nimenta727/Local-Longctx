const { contextBridge, ipcRenderer } = require('electron')

const invoke = (name, ...args) => ipcRenderer.invoke('farstack:' + name, ...args)
contextBridge.exposeInMainWorld('farstack', {
  status: () => invoke('status'),
  pick: kind => invoke('pick', kind),
  pickSsd: () => invoke('pick-ssd'),
  openData: () => invoke('open-data'),
  start: settings => invoke('start', settings),
  stop: () => invoke('stop'),
  saveStartup: settings => invoke('save-startup', settings),
  cacheStatus: () => invoke('cache-status'),
  cacheApply: draft => invoke('cache-apply', draft),
  conversations: () => invoke('conversation-list'),
  loadConversation: id => invoke('conversation-load', id),
  send: (id, text) => invoke('conversation-send', id, text),
  cancel: () => invoke('conversation-cancel'),
  onDelta: callback => {
    const receive = (_event, delta) => callback(delta)
    ipcRenderer.on('farstack:delta', receive)
    return () => ipcRenderer.removeListener('farstack:delta', receive)
  },
})
