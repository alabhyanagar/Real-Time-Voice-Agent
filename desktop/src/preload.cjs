const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('voiceAgentDesktop', {
  platform: process.platform,
  isDesktop: true,
  toggleAssistant: () => ipcRenderer.send('toggle-assistant'),
  setAlwaysOnTop: (alwaysOnTop) => ipcRenderer.send('set-always-on-top', Boolean(alwaysOnTop)),
  getStoredSessionHandle: () => ipcRenderer.invoke('get-stored-session-handle'),
  setStoredSessionHandle: (handle) => ipcRenderer.invoke('set-stored-session-handle', handle),
  clearStoredSessionHandle: () => ipcRenderer.invoke('clear-stored-session-handle'),
  notifyState: (state) => ipcRenderer.send('assistant-state-changed', state),
  onShortcutTriggered: (callback) => {
    if (typeof callback !== 'function') return () => {};
    const subscription = () => callback();
    ipcRenderer.on('shortcut-toggle', subscription);
    return () => ipcRenderer.removeListener('shortcut-toggle', subscription);
  },
});
