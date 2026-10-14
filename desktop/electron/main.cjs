const { app, BrowserWindow, dialog, globalShortcut, ipcMain, screen, session } = require("electron");
const { spawn } = require("node:child_process");
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { focusUrlAllowed: isFocusUrlAllowed } = require("./focus-policy.cjs");
const { findBackendPython, resolveBackendDataDirectory } = require("./backend-python.cjs");

const ROOT = path.resolve(__dirname, "..", "..");
const DESKTOP = path.resolve(__dirname, "..");
const BACKEND = path.join(ROOT, "backend");
const DEFAULT_PORT = Number(process.env.NEKO_PORT || 8765);
const PRODUCTION = app.isPackaged || process.argv.includes("--production");
const DEV_URL = "http://127.0.0.1:5173";
const DATA_DIR_OVERRIDE = process.env.NEKO_DATA_DIR?.trim();
let APP_DATA = path.resolve(ROOT, DATA_DIR_OVERRIDE || path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local"), "NekoAI"));
let RUN_INFO = path.join(APP_DATA, "run.json");

let backendProcess;
let viteProcess;
let petWindow;
let petWindowLoadPromise;
let dashboardWindow;
let focusBrowserWindow;
let focusBrowserTimer;
let focusBrowserPolicy;
let backendPort = DEFAULT_PORT;
let interactive = false;
let quitting = false;
let backendOutputTail = "";
const singleInstance = app.requestSingleInstanceLock();

if (!singleInstance) app.quit();
else app.on("second-instance", () => openDashboard());

function backendPython() {
  const result = findBackendPython(BACKEND, process.env);
  if (!result.usable) {
    const failures = result.failures.map((failure) => `  - ${failure}`).join("\n");
    throw new Error(`No usable Python backend runtime was found. Each candidate must start and import FastAPI and Uvicorn.\n${failures || "  - No Python candidates were configured."}\n\nInstall a supported Python runtime, then recreate a backend virtual environment and install backend/requirements.txt.`);
  }
  console.info(`[startup] selected Python ${result.version}: ${result.path}`);
  return result.path;
}

async function getHealth(port) {
  try {
    const result = await requestLoopback(port, "/api/health", 700);
    if (result.status !== 200) return null;
    return JSON.parse(result.body);
  } catch {
    return null;
  }
}

// Use Node's direct loopback HTTP client. Browser/Electron fetch can follow the
// machine's proxy configuration; localhost startup checks must never go through it.
function requestLoopback(port, requestPath, timeoutMs) {
  return new Promise((resolve, reject) => {
    const request = http.get({ hostname: "127.0.0.1", port: Number(port), path: requestPath, timeout: timeoutMs }, (response) => {
      let body = "";
      response.setEncoding("utf8");
      response.on("data", (chunk) => { body += chunk; });
      response.on("end", () => resolve({
        status: response.statusCode || 0,
        body,
        contentType: response.headers["content-type"] || "",
      }));
    });
    request.on("timeout", () => request.destroy(new Error(`Timed out after ${timeoutMs}ms`)));
    request.on("error", reject);
  });
}

async function verifyRunInfo(info) {
  try {
    const path = `/auth/verify?t=${encodeURIComponent(info.token)}`;
    const response = await requestLoopback(info.port, path, 1200);
    return { ok: response.status === 204, status: response.status, detail: response.body.trim() };
  } catch (error) {
    return { ok: false, status: 0, detail: error.message };
  }
}

async function exchangeBootstrapToken(info) {
  const response = await session.defaultSession.fetch(
    `http://127.0.0.1:${Number(info.port)}/auth/start?t=${encodeURIComponent(info.token)}`,
    { redirect: "manual" },
  );
  if (response.status !== 303) throw new Error("The backend rejected its desktop launch token.");
}

async function waitForManagedServer(child, timeoutMs = 25000) {
  const started = Date.now();
  let lastFailure = "run.json has not been created";
  while (Date.now() - started < timeoutMs) {
    let runInfo;
    try { runInfo = JSON.parse(fs.readFileSync(RUN_INFO, "utf8")); }
    catch (error) {
      lastFailure = error.code === "ENOENT" ? `run file not found at ${RUN_INFO}` : `could not read ${RUN_INFO}: ${error.message}`;
      runInfo = null;
    }
    if (runInfo?.token && Number.isInteger(Number(runInfo.port))) {
      if (Number(runInfo.port) !== DEFAULT_PORT) {
        lastFailure = `run.json port ${runInfo.port} does not match the Electron launch port ${DEFAULT_PORT}`;
      } else {
        try {
          const healthResponse = await requestLoopback(runInfo.port, "/api/health", 700);
          let health;
          try { health = JSON.parse(healthResponse.body); } catch { health = null; }
          if (healthResponse.status !== 200 || health?.app !== "nekoai") {
            lastFailure = `GET /api/health on port ${runInfo.port} returned HTTP ${healthResponse.status} and did not identify NekoAI`;
          } else {
            const verification = await verifyRunInfo(runInfo);
            if (!verification.ok) {
              lastFailure = `backend on port ${runInfo.port} rejected run.json token (HTTP ${verification.status}${verification.detail ? `: ${verification.detail}` : ""})`;
            } else {
              try {
                const root = await requestLoopback(runInfo.port, "/", 1200);
                if (root.status === 200 && (!PRODUCTION || root.contentType.includes("text/html"))) return runInfo;
                lastFailure = PRODUCTION && !root.contentType.includes("text/html")
                  ? `backend is accepting connections on port ${runInfo.port}, but / returned ${root.contentType || "no content type"}; the production frontend is not being served`
                  : `backend / endpoint returned HTTP ${root.status}`;
              } catch (error) {
                lastFailure = `authenticated backend did not serve / on port ${runInfo.port}: ${error.message}`;
              }
            }
          }
        } catch (error) {
          lastFailure = `GET /api/health on port ${runInfo.port} failed: ${error.message}`;
        }
      }
    } else if (runInfo) {
      lastFailure = `run.json at ${RUN_INFO} is missing a valid token or port`;
    }
    if (child?.spawnError) return { failure: `Python process failed to start: ${child.spawnError.message}` };
    if (child?.exitCode !== null && child?.exitCode !== undefined) {
      return { failure: `Python launcher exited with code ${child.exitCode}; ${lastFailure}` };
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  return { failure: lastFailure };
}

async function startBackend() {
  console.info(`[startup] Electron entry: ${path.join(__dirname, "main.cjs")}`);
  const python = backendPython();

  // Ask this interpreter to resolve both defaults and explicit overrides.
  // Windows Store Python redirects LOCALAPPDATA paths into its package cache.
  // Resolving only the default left Electron and Python watching different run.json paths.
  APP_DATA = resolveBackendDataDirectory(python, BACKEND, DATA_DIR_OVERRIDE);
  RUN_INFO = path.join(APP_DATA, "run.json");
  console.info(`[startup] Python: ${python}`);
  console.info(`[startup] backend working directory: ${BACKEND}`);
  console.info(`[startup] shared backend data directory: ${APP_DATA}`);
  console.info(`[startup] expected backend run file: ${RUN_INFO}`);

  let runInfo;
  try { runInfo = JSON.parse(fs.readFileSync(RUN_INFO, "utf8")); } catch { runInfo = null; }
  if (runInfo?.port && (await getHealth(runInfo.port))?.app === "nekoai" && (await verifyRunInfo(runInfo)).ok) {
    backendPort = Number(runInfo.port);
    return runInfo;
  }

  const existingHealth = await getHealth(DEFAULT_PORT);
  if (existingHealth?.app === "nekoai") {
    const error = new Error(`A NekoAI server is already using 127.0.0.1:${DEFAULT_PORT}, but it does not match the authenticated run file at ${RUN_INFO}. NekoAI did not trust it or start a duplicate. Close the terminal or process that started that server, then choose Retry here. NekoAI will start its managed backend in the same data directory without touching saved activity records.`);
    error.code = "NEKO_UNMANAGED_BACKEND";
    throw error;
  }

  const env = { ...process.env, NEKO_DATA_DIR: APP_DATA, NEKO_NO_BROWSER: "1" };
  if (!PRODUCTION) env.NEKO_EXTRA_ORIGINS = [env.NEKO_EXTRA_ORIGINS, DEV_URL].filter(Boolean).join(",");
  console.info(`[startup] passing the shared data directory explicitly to Python`);
  backendProcess = spawn(python, ["-u", "run_neko.py", "--data-dir", APP_DATA], {
    cwd: BACKEND, env, windowsHide: true, stdio: "pipe",
  });
  backendProcess.stdout.on("data", (data) => {
    const output = String(data);
    backendOutputTail = (backendOutputTail + output).slice(-5000);
    process.stdout.write(`[backend] ${output}`);
  });
  backendProcess.stderr.on("data", (data) => {
    const output = String(data);
    backendOutputTail = (backendOutputTail + output).slice(-5000);
    process.stderr.write(`[backend] ${output}`);
  });
  backendProcess.on("error", (error) => {
    backendProcess.spawnError = error;
    console.error("Could not start the Python backend:", error);
  });

  const result = await waitForManagedServer(backendProcess);
  runInfo = result?.failure ? null : result;
  if (!runInfo) {
    if (backendProcess.spawnError) {
      throw new Error(`Python could not start from ${python}. The virtual environment may point to a missing base Python. Install Python 3.10+ and rerun Start_NekoAI.bat.`);
    }
    const exit = backendProcess.exitCode === null ? "" : ` (Python launcher exit code ${backendProcess.exitCode})`;
    const detail = backendOutputTail.trim();
    throw new Error(`The managed backend could not complete authenticated startup: ${result?.failure || "unknown verification failure"}.${exit}\n\nExpected run file: ${RUN_INFO}\nExpected port: ${DEFAULT_PORT}${detail ? `\n\nBackend output:\n${detail}` : `\n\nBackend log: ${path.join(APP_DATA, "logs", "neko.log")}`}`);
  }
  backendPort = Number(runInfo.port);
  console.info(`[startup] backend healthy at http://127.0.0.1:${backendPort}; authenticated run file: ${RUN_INFO}`);
  return runInfo;
}

function startVite() {
  if (viteProcess) return Promise.resolve();
  const env = { ...process.env, NEKO_API_PORT: String(backendPort) };
  viteProcess = spawn("npm.cmd", ["run", "web:dev", "--", "--host", "127.0.0.1"], {
    cwd: DESKTOP, env, shell: true, windowsHide: true, stdio: "inherit",
  });
  viteProcess.on("error", (error) => console.error("Could not start Vite:", error));
  return waitForVite();
}

async function waitForVite() {
  for (let i = 0; i < 100; i += 1) {
    try {
      const response = await fetch(DEV_URL, { signal: AbortSignal.timeout(500) });
      if (response.ok) return;
    } catch { /* Vite is still starting. */ }
    if (viteProcess?.exitCode !== null && viteProcess?.exitCode !== undefined) break;
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error("Vite did not start on 127.0.0.1:5173.");
}

function clampBounds(bounds) {
  const displays = screen.getAllDisplays();
  const display = displays.find((item) => bounds.x >= item.workArea.x && bounds.y >= item.workArea.y &&
    bounds.x < item.workArea.x + item.workArea.width && bounds.y < item.workArea.y + item.workArea.height) || screen.getPrimaryDisplay();
  const area = display.workArea;
  return {
    x: Math.min(Math.max(bounds.x, area.x), area.x + area.width - bounds.width),
    y: Math.min(Math.max(bounds.y, area.y), area.y + area.height - bounds.height),
    width: bounds.width,
    height: bounds.height,
  };
}

function initialBounds() {
  const savedPath = path.join(app.getPath("userData"), "pet-window.json");
  try {
    const saved = JSON.parse(fs.readFileSync(savedPath, "utf8"));
    return clampBounds({ ...saved, width: 360, height: 440 });
  } catch {
    const area = screen.getPrimaryDisplay().workArea;
    return { x: area.x + area.width - 380, y: area.y + area.height - 480, width: 360, height: 440 };
  }
}

function savePetBounds() {
  if (!petWindow || petWindow.isDestroyed()) return;
  const savedPath = path.join(app.getPath("userData"), "pet-window.json");
  fs.mkdirSync(path.dirname(savedPath), { recursive: true });
  fs.writeFileSync(savedPath, JSON.stringify(petWindow.getBounds()), "utf8");
}

function allowedNavigation(url) {
  try {
    const origin = new URL(url).origin;
    return origin === new URL(DEV_URL).origin || origin === `http://127.0.0.1:${backendPort}`;
  } catch { return false; }
}

async function focusBackend(pathname, method = "GET", body) {
  const origin = PRODUCTION ? `http://127.0.0.1:${backendPort}` : DEV_URL;
  const response = await session.defaultSession.fetch(`http://127.0.0.1:${backendPort}${pathname}`, {
    method, headers: { Origin: origin, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new Error(`Focus service request failed (HTTP ${response.status}).`);
  return response.json();
}

async function reportFocusBrowserState() {
  if (!focusBrowserWindow || focusBrowserWindow.isDestroyed()) return;
  try {
    const policy = await focusBackend("/api/focus/browser-policy");
    focusBrowserPolicy = policy;
    if (!policy.session_id) return;
    const enforced = Boolean(policy.active && policy.mode === "controlled_browser");
    let domain = null;
    try { domain = new URL(focusBrowserWindow.webContents.getURL()).hostname; } catch { /* blank/start page */ }
    await focusBackend("/api/focus/browser-heartbeat", "POST", { enforced, domain });
  } catch (error) {
    focusBrowserPolicy = null;
    console.warn(`[focus-browser] policy disconnected; navigation fails closed: ${error.message}`);
  }
}

async function reportBlockedFocusNavigation(url, reason) {
  try { await focusBackend("/api/focus/browser-distraction", "POST", { domain: new URL(url).hostname, reason }); }
  catch { /* No privileged navigation is allowed when the backend is unavailable. */ }
}

async function openFocusBrowser(url) {
  url = /^[a-z][a-z0-9+.-]*:\/\//i.test(url) ? url : `https://${url}`;
  const policy = await focusBackend("/api/focus/browser-policy");
  focusBrowserPolicy = policy;
  if (!policy.active || policy.mode !== "controlled_browser") throw new Error("Start an active Neko Focus Browser session before opening a site.");
  if (!isFocusUrlAllowed(url, policy)) throw new Error("This address is not in the active focus session's approved website list.");
  if (focusBrowserWindow && !focusBrowserWindow.isDestroyed()) {
    focusBrowserWindow.show();
    focusBrowserWindow.focus();
    await focusBrowserWindow.loadURL(url);
    return true;
  }
  const window = new BrowserWindow({
    width: 1100, height: 760, minWidth: 640, minHeight: 480,
    title: "Neko Focus Browser", backgroundColor: "#ffffff",
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  focusBrowserWindow = window;
  window.webContents.on("page-title-updated", (event) => { event.preventDefault(); if (!window.isDestroyed()) window.setTitle("Neko Focus Browser"); });
  const guard = (event, target, reason = "blocked_navigation") => {
    const targetUrl = typeof target === "string" ? target : target?.url;
    if (!isFocusUrlAllowed(targetUrl, focusBrowserPolicy)) { event.preventDefault(); if (targetUrl) void reportBlockedFocusNavigation(targetUrl, reason); }
  };
  window.webContents.on("will-navigate", (event, target) => guard(event, target));
  window.webContents.on("will-redirect", (event, target) => guard(event, target, "unapproved_redirect"));
  window.webContents.on("will-frame-navigate", (event, target) => guard(event, target));
  window.webContents.setWindowOpenHandler(({ url: target }) => {
    if (isFocusUrlAllowed(target, focusBrowserPolicy)) void window.loadURL(target);
    else void reportBlockedFocusNavigation(target, "blocked_navigation");
    return { action: "deny" };
  });
  window.on("closed", () => {
    if (focusBrowserWindow === window) focusBrowserWindow = null;
    if (focusBrowserTimer) clearInterval(focusBrowserTimer);
    focusBrowserTimer = null;
    focusBrowserPolicy = null;
  });
  await window.loadURL(url);
  void reportFocusBrowserState();
  focusBrowserTimer = setInterval(() => void reportFocusBrowserState(), 8000);
  return true;
}

function ensurePetWindow() {
  if (petWindow && !petWindow.isDestroyed()) {
    return petWindowLoadPromise || Promise.resolve(petWindow);
  }

  const window = new BrowserWindow({
    ...initialBounds(),
    transparent: true,
    backgroundColor: "#00000000",
    frame: false,
    hasShadow: false,
    resizable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    focusable: false,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  petWindow = window;
  window.setAlwaysOnTop(true, "floating");
  window.setIgnoreMouseEvents(true, { forward: true });
  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event, url) => {
    if (!allowedNavigation(url)) event.preventDefault();
  });
  window.on("move", savePetBounds);
  window.on("closed", () => {
    if (petWindow === window) {
      petWindow = null;
      petWindowLoadPromise = null;
    }
  });

  const target = PRODUCTION ? `http://127.0.0.1:${backendPort}/?pet=1` : `${DEV_URL}/?pet=1`;
  const loading = window.loadURL(target).then(() => window).catch((error) => {
    if (petWindow === window) {
      petWindow = null;
      petWindowLoadPromise = null;
    }
    if (!window.isDestroyed()) window.destroy();
    throw new Error(`The desktop cat window could not load its React view from ${target}: ${error.message}`);
  });
  petWindowLoadPromise = loading;
  loading.catch((error) => console.error("[pet]", error.message));
  return loading;
}

function openDashboard() {
  if (dashboardWindow && !dashboardWindow.isDestroyed()) {
    dashboardWindow.show();
    dashboardWindow.focus();
    return;
  }
  dashboardWindow = new BrowserWindow({
    width: 640, height: 760, minWidth: 480, minHeight: 560,
    title: "NekoAI Dashboard", backgroundColor: "#fff7ec",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true, nodeIntegration: false, sandbox: true,
    },
  });
  dashboardWindow.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  dashboardWindow.webContents.on("will-navigate", (event, url) => {
    if (!allowedNavigation(url)) event.preventDefault();
  });
  dashboardWindow.on("closed", () => { dashboardWindow = null; });
  const target = PRODUCTION ? `http://127.0.0.1:${backendPort}/` : DEV_URL;
  dashboardWindow.loadURL(target).catch((error) => {
    const exitCode = backendProcess?.exitCode;
    const processState = exitCode === null || exitCode === undefined
      ? "The managed backend process has not reported an exit code."
      : `The managed backend exited with code ${exitCode}.`;
    const output = backendOutputTail.trim();
    const details = output ? `\n\nBackend stdout/stderr:\n${output}` : "\n\nNo backend output was captured.";
    const message = `NekoAI could not load ${target}: ${error.message}\n${processState}${details}`;
    console.error(`[startup] dashboard load failed: ${message}`);
    if (!dashboardWindow || dashboardWindow.isDestroyed()) return;
    dialog.showErrorBox("NekoAI dashboard could not connect", message);
  });
  dashboardWindow.show();
}

function setInteractive(enabled) {
  interactive = enabled;
  if (petWindow && !petWindow.isDestroyed()) {
    const bounds = petWindow.getBounds();
    const height = enabled ? 580 : 440;
    const y = enabled ? bounds.y - (height - bounds.height) : bounds.y + (bounds.height - height);
    petWindow.setBounds(clampBounds({ ...bounds, y, height }));
    petWindow.setFocusable(enabled);
    petWindow.setIgnoreMouseEvents(!enabled, { forward: true });
    if (enabled) petWindow.focus();
    else petWindow.blur();
    petWindow.webContents.send("neko:interaction-change", enabled);
  }
}

async function requestBackendShutdown() {
  const origin = PRODUCTION ? `http://127.0.0.1:${backendPort}` : DEV_URL;
  try {
    await Promise.race([
      session.defaultSession.fetch(`http://127.0.0.1:${backendPort}/api/shutdown`, {
        method: "POST", headers: { Origin: origin },
      }),
      new Promise((resolve) => setTimeout(resolve, 1500)),
    ]);
  } catch { /* The backend may already have exited. */ }
}

app.whenReady().then(async () => {
  if (!singleInstance) return;
  try {
    let runInfo;
    for (;;) {
      try { runInfo = await startBackend(); break; }
      catch (error) {
        if (error.code !== "NEKO_UNMANAGED_BACKEND") throw error;
        const choice = await dialog.showMessageBox({
          type: "warning", title: "NekoAI backend needs recovery", message: error.message,
          buttons: ["Retry after closing the other server", "Cancel"], defaultId: 0, cancelId: 1,
        });
        if (choice.response !== 0) throw new Error("NekoAI startup was cancelled. Run Start_NekoAI.bat again after closing the other backend.");
      }
    }
    if (!PRODUCTION) await startVite();
    backendPort = Number(runInfo.port);
    await exchangeBootstrapToken(runInfo);
    openDashboard();
    globalShortcut.register("CommandOrControl+Alt+N", () => setInteractive(!interactive));
    globalShortcut.register("CommandOrControl+Alt+D", openDashboard);
    ipcMain.on("neko:open-dashboard", openDashboard);
    ipcMain.handle("neko:open-focus-browser", (_event, url) => openFocusBrowser(url));
    ipcMain.on("neko:focus-reaction", (_event, message) => {
      if (typeof message === "string" && message.length <= 120 && petWindow && !petWindow.isDestroyed()) {
        petWindow.webContents.send("neko:focus-reaction", message);
      }
    });
    ipcMain.handle("neko:enable-pet", async () => {
      const window = await ensurePetWindow();
      if (window.isDestroyed()) throw new Error("The desktop cat window closed before it could be shown. Click Allow Neko on Desktop again.");
      window.setAlwaysOnTop(true, "floating");
      window.show();
      return true;
    });
    ipcMain.handle("neko:set-interactive", (_event, enabled) => {
      setInteractive(Boolean(enabled));
      return Boolean(petWindow && !petWindow.isDestroyed());
    });
    ipcMain.handle("neko:hide-pet", () => {
      if (!petWindow || petWindow.isDestroyed()) return false;
      setInteractive(false);
      petWindow.hide();
      return true;
    });
    ipcMain.on("neko:exit-app", () => app.quit());
  } catch (error) {
    dialog.showErrorBox("NekoAI could not start", error.message);
    app.quit();
  }
});

// Keep the independent floating pet alive when the dashboard is closed.
// If no pet was created, retain the normal Electron quit-on-last-window behavior.
app.on("window-all-closed", () => {
  if ((!petWindow || petWindow.isDestroyed()) && (!focusBrowserWindow || focusBrowserWindow.isDestroyed())) app.quit();
});

app.on("before-quit", (event) => {
  if (quitting) return;
  quitting = true;
  event.preventDefault();
  globalShortcut.unregisterAll();
  requestBackendShutdown().finally(() => {
    if (viteProcess && viteProcess.exitCode === null) viteProcess.kill();
    app.quit();
  });
});

