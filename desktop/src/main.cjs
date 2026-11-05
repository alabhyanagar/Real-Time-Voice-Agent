const { app, BrowserWindow, globalShortcut, Menu, nativeImage, Tray, session, ipcMain } = require('electron');
const path = require('node:path');
const fs = require('node:fs');

const backendUrl = process.env.VOICE_AGENT_URL || 'http://localhost:8000';
let windowRef = null;
let trayRef = null;
let currentAssistantState = 'idle';

function getSessionStorePath() {
  const userDataDir = app.getPath('userData');
  return path.join(userDataDir, 'session_store.json');
}

function readStoredSessionHandle() {
  try {
    const storePath = getSessionStorePath();
    if (fs.existsSync(storePath)) {
      const data = JSON.parse(fs.readFileSync(storePath, 'utf8'));
      return data.sessionHandle || null;
    }
  } catch (err) {
    console.error('Failed to read session handle:', err);
  }
  return null;
}

function writeStoredSessionHandle(handle) {
  try {
    const storePath = getSessionStorePath();
    fs.mkdirSync(path.dirname(storePath), { recursive: true });
    fs.writeFileSync(storePath, JSON.stringify({ sessionHandle: handle, updatedAt: Date.now() }), 'utf8');
    return true;
  } catch (err) {
    console.error('Failed to save session handle:', err);
    return false;
  }
}

function clearStoredSessionHandle() {
  try {
    const storePath = getSessionStorePath();
    if (fs.existsSync(storePath)) {
      fs.unlinkSync(storePath);
    }
    return true;
  } catch (err) {
    console.error('Failed to clear session handle:', err);
    return false;
  }
}

function createWindow() {
  windowRef = new BrowserWindow({
    width: 480,
    height: 780,
    minWidth: 380,
    minHeight: 540,
    show: false,
    frame: true,
    title: 'Voice Agent',
    backgroundColor: '#0f172a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  windowRef.loadURL(backendUrl);

  windowRef.on('close', (event) => {
    if (!app.isQuitting) {
      event.preventDefault();
      windowRef.hide();
    }
  });

  windowRef.on('closed', () => {
    windowRef = null;
  });
}

function toggleWindow() {
  if (!windowRef) {
    createWindow();
  }
  if (windowRef.isVisible()) {
    windowRef.hide();
  } else {
    windowRef.show();
    windowRef.focus();
    windowRef.webContents.send('shortcut-toggle');
  }
}

function updateTrayMenu() {
  if (!trayRef) return;
  const contextMenu = Menu.buildFromTemplate([
    { label: `Status: ${currentAssistantState}`, enabled: false },
    { type: 'separator' },
    { label: 'Show/Hide Assistant', click: toggleWindow },
    {
      label: 'Always on Top',
      type: 'checkbox',
      checked: windowRef ? windowRef.isAlwaysOnTop() : false,
      click: (item) => {
        if (windowRef) windowRef.setAlwaysOnTop(item.checked);
      },
    },
    { type: 'separator' },
    {
      label: 'Quit Voice Agent',
      click: () => {
        app.isQuitting = true;
        app.quit();
      },
    },
  ]);
  trayRef.setContextMenu(contextMenu);
  trayRef.setToolTip(`Voice Agent (${currentAssistantState})`);
}

app.whenReady().then(() => {
  // IPC Handlers
  ipcMain.on('toggle-assistant', toggleWindow);

  ipcMain.on('set-always-on-top', (_event, alwaysOnTop) => {
    if (windowRef) {
      windowRef.setAlwaysOnTop(alwaysOnTop);
      updateTrayMenu();
    }
  });

  ipcMain.handle('get-stored-session-handle', () => readStoredSessionHandle());
  ipcMain.handle('set-stored-session-handle', (_event, handle) => writeStoredSessionHandle(handle));
  ipcMain.handle('clear-stored-session-handle', () => clearStoredSessionHandle());

  ipcMain.on('assistant-state-changed', (_event, state) => {
    currentAssistantState = String(state || 'idle');
    updateTrayMenu();
  });

  // Media permission handler
  session.defaultSession.setPermissionRequestHandler((_webContents, permission, callback) => {
    callback(permission === 'media');
  });

  createWindow();

  // System Tray setup
  const icon = nativeImage.createEmpty();
  trayRef = new Tray(icon);
  updateTrayMenu();
  trayRef.on('click', toggleWindow);

  // Global shortcut
  const registered = globalShortcut.register('CommandOrControl+Space', toggleWindow);
  if (!registered) {
    console.warn('Global shortcut registration failed for CommandOrControl+Space');
  }
});

app.on('window-all-closed', (event) => {
  event.preventDefault();
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});
