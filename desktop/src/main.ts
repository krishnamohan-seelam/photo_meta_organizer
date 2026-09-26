import { app, BrowserWindow, dialog, ipcMain, session, shell } from 'electron';
import { randomBytes } from 'crypto';
import * as path from 'path';
import * as fs from 'fs';
import { ChildProcess, exec, spawn } from 'child_process';
import * as http from 'http';

import * as net from 'net';

let mainWindow: BrowserWindow | null = null;
let backendProcess: ChildProcess | null = null;
let backendPort = 8000;
let isOwnBackendProcess = false;
// Per-launch API token (PMO-26). Set only when the packaged app spawns its own backend;
// the backend requires it as a cookie that only this app's session holds.
let apiToken: string | null = null;
const TOKEN_COOKIE = 'pmo_token';
const isDev = process.argv.includes('--dev') || !app.isPackaged;

/**
 * Check if a Photo Meta Organizer backend is already running and healthy on the given port.
 */
function checkExistingBackend(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${port}/health`, (res) => {
      let data = '';
      res.on('data', (chunk) => {
        data += chunk;
      });
      res.on('end', () => {
        try {
          const json = JSON.parse(data);
          resolve(json.status === 'ok');
        } catch {
          resolve(false);
        }
      });
    });
    req.on('error', () => resolve(false));
    req.setTimeout(1200, () => {
      req.destroy();
      resolve(false);
    });
  });
}

/**
 * Find an available TCP port starting from the given port.
 */
function getAvailablePort(startingPort = 8000): Promise<number> {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.listen(startingPort, '127.0.0.1', () => {
      const addr = server.address() as net.AddressInfo;
      const port = addr.port;
      server.close(() => resolve(port));
    });
    server.on('error', () => {
      // Starting port is in use; find any free ephemeral port
      const ephemeralServer = net.createServer();
      ephemeralServer.listen(0, '127.0.0.1', () => {
        const addr = ephemeralServer.address() as net.AddressInfo;
        const port = addr.port;
        ephemeralServer.close(() => resolve(port));
      });
    });
  });
}

/**
 * Determine the command and arguments to launch the Python backend.
 */
function getBackendCommand(port: number): { cmd: string; args: string[]; cwd: string } {
  const rootDir = path.resolve(__dirname, '..', '..');

  if (app.isPackaged) {
    // Packaged production mode: look for packaged executable in resources
    const packagedExe = path.join(
      process.resourcesPath,
      'backend',
      'photo_meta_organizer_backend.exe'
    );
    if (fs.existsSync(packagedExe)) {
      // Everything the backend writes goes under the per-user data directory, never the
      // install directory (read-only for normal users, replaced on update). Older builds
      // kept their database in resources/; --legacy-dir adopts it once.
      const dataDir = app.getPath('userData');
      fs.mkdirSync(dataDir, { recursive: true });
      return {
        cmd: packagedExe,
        args: [
          '--port', port.toString(),
          '--host', '127.0.0.1',
          '--db', path.join(dataDir, 'photos.db'),
          // Not under userData/Cache: that is Chromium's HTTP cache (and on Windows
          // "cache" and "Cache" are the same directory).
          '--cache-dir', path.join(dataDir, 'thumbnails'),
          '--log-dir', path.join(dataDir, 'logs'),
          '--legacy-dir', process.resourcesPath,
        ],
        cwd: dataDir,
      };
    }
  }

  // Development / Local mode: locate python in .venv
  const venvPythonWin = path.join(rootDir, '.venv', 'Scripts', 'python.exe');
  const pythonCmd = fs.existsSync(venvPythonWin) ? venvPythonWin : 'python';
  const entryScript = path.join(rootDir, 'scripts', 'desktop_backend.py');

  return {
    cmd: pythonCmd,
    args: [entryScript, '--port', port.toString(), '--host', '127.0.0.1'],
    cwd: rootDir,
  };
}

/**
 * Poll the backend health endpoint until it responds or times out.
 */
function waitForBackendReady(port: number, timeoutMs = 15000): Promise<boolean> {
  const startTime = Date.now();
  return new Promise((resolve) => {
    const check = () => {
      const req = http.get(`http://127.0.0.1:${port}/health`, (res) => {
        if (res.statusCode === 200) {
          resolve(true);
        } else if (Date.now() - startTime < timeoutMs) {
          setTimeout(check, 300);
        } else {
          resolve(false);
        }
      });
      req.on('error', () => {
        if (Date.now() - startTime < timeoutMs) {
          setTimeout(check, 300);
        } else {
          resolve(false);
        }
      });
      req.end();
    };
    check();
  });
}

/**
 * Spawn the backend child process (or attach to an existing running backend).
 */
async function startBackend(): Promise<boolean> {
  // 1. In development, reuse a backend already running on port 8000 (e.g. uvicorn --reload).
  //    Never when packaged: that would silently use someone else's database.
  const isAlreadyRunning = !app.isPackaged && (await checkExistingBackend(8000));
  if (isAlreadyRunning) {
    console.log('[Desktop Main] Active backend detected on port 8000. Reusing existing instance.');
    backendPort = 8000;
    isOwnBackendProcess = false;
    return true;
  }

  // 2. Otherwise find an open port
  backendPort = await getAvailablePort(8000);
  const { cmd, args, cwd } = getBackendCommand(backendPort);
  console.log(`[Desktop Main] Spawning backend: ${cmd} ${args.join(' ')} (cwd: ${cwd})`);

  // The token goes in the child's environment, never on its command line (which any
  // local process can list). Dev mode loads through the Vite proxy on another host,
  // where this cookie would not be sent, so it relies on the PMO-11 host/CORS checks.
  apiToken = app.isPackaged ? randomBytes(32).toString('base64url') : null;
  const env = { ...process.env };
  delete env.ELECTRON_RUN_AS_NODE;
  if (apiToken) env.PMO_API_TOKEN = apiToken;

  try {
    backendProcess = spawn(cmd, args, {
      cwd,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });
    isOwnBackendProcess = true;

    backendProcess.stdout?.on('data', (data) => {
      console.log(`[Backend stdout] ${data.toString().trim()}`);
    });

    backendProcess.stderr?.on('data', (data) => {
      console.error(`[Backend stderr] ${data.toString().trim()}`);
    });

    backendProcess.on('exit', (code) => {
      console.log(`[Desktop Main] Backend exited with code: ${code}`);
      backendProcess = null;
    });

    const ready = await waitForBackendReady(backendPort, 15000);
    return ready;
  } catch (err) {
    console.error('[Desktop Main] Failed to spawn backend:', err);
    return false;
  }
}

/**
 * Terminate backend process tree cleanly on Windows.
 */
function killBackend() {
  if (!isOwnBackendProcess || !backendProcess || !backendProcess.pid) return;
  const pid = backendProcess.pid;
  console.log(`[Desktop Main] Terminating backend process tree (PID: ${pid})...`);
  if (process.platform === 'win32') {
    exec(`taskkill /pid ${pid} /T /F`, (err) => {
      if (err) console.warn('[Desktop Main] Taskkill warning:', err.message);
    });
  } else {
    backendProcess.kill('SIGTERM');
  }
  backendProcess = null;
}

/**
 * Create the main desktop window.
 */
async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: 'Photo Meta Organizer',
    autoHideMenuBar: true,
    backgroundColor: '#0f172a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // Forward renderer console logs to terminal
  mainWindow.webContents.on('console-message', (_event, _level, message, line, sourceId) => {
    console.log(`[Renderer] ${message} (${sourceId}:${line})`);
  });

  // Allow F12 to toggle DevTools
  mainWindow.webContents.on('before-input-event', (_event, input) => {
    if (input.key === 'F12' && input.type === 'keyDown') {
      mainWindow?.webContents.toggleDevTools();
    }
  });

  // Load UI: in dev mode check Vite dev server or fallback to FastAPI root
  if (isDev) {
    const devUrl = 'http://localhost:5173';
    // Verify Vite is actually running by checking the response body
    const checkVite = (): Promise<boolean> =>
      new Promise((resolve) => {
        const req = http.get(devUrl, (res) => {
          if (res.statusCode !== 200) { res.destroy(); return resolve(false); }
          let body = '';
          res.on('data', (c) => { body += c; });
          res.on('end', () => {
            // Vite dev server always injects /@vite/client or serves <div id="root">
            const isVite = body.includes('/@vite/client') || body.includes('@vite');
            resolve(isVite);
          });
        });
        req.on('error', () => resolve(false));
        req.setTimeout(1500, () => { req.destroy(); resolve(false); });
        req.end();
      });

    checkVite().then((isVite) => {
      if (isVite) {
        console.log(`[Desktop Main] Loading Vite dev server at ${devUrl}`);
        mainWindow?.loadURL(devUrl);
      } else {
        console.log(`[Desktop Main] Vite dev server not detected; loading backend server at http://127.0.0.1:${backendPort}/`);
        mainWindow?.loadURL(`http://127.0.0.1:${backendPort}/`);
      }
    });
  } else {
    const backendUrl = `http://127.0.0.1:${backendPort}`;
    if (apiToken) {
      // HttpOnly: page scripts cannot read it. SameSite=Strict: no other site can send it.
      await session.defaultSession.cookies.set({
        url: backendUrl,
        name: TOKEN_COOKIE,
        value: apiToken,
        httpOnly: true,
        sameSite: 'strict',
        path: '/',
      });
    }
    mainWindow.loadURL(`${backendUrl}/`);
  }
}

// Register IPC handlers
ipcMain.handle('dialog:open-directory', async () => {
  if (!mainWindow) return null;
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
    title: 'Select Photo Directory to Index',
  });
  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }
  return result.filePaths[0];
});

ipcMain.handle('shell:show-item-in-folder', async (_, filePath: string) => {
  if (filePath && fs.existsSync(filePath)) {
    shell.showItemInFolder(filePath);
  }
});

ipcMain.handle('app:get-backend-info', async () => {
  return {
    port: backendPort,
    host: '127.0.0.1',
    baseUrl: `http://127.0.0.1:${backendPort}`,
  };
});

app.whenReady().then(async () => {
  console.log('[Desktop Main] Application initializing...');
  const backendReady = await startBackend();
  if (!backendReady) {
    console.warn('[Desktop Main] Backend did not respond to health check in time, proceeding anyway...');
  }
  await createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('before-quit', () => {
  killBackend();
});

app.on('window-all-closed', () => {
  killBackend();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
