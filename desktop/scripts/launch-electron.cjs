const { spawn } = require("node:child_process");

const electronPath = require("electron");
const env = { ...process.env };

// Editors such as VS Code can set this for their own Electron-hosted tools.
// Electron itself interprets it as "run the app entry point as Node" and then
// `require('electron').app` is unavailable in the NekoAI main process.
delete env.ELECTRON_RUN_AS_NODE;

const child = spawn(electronPath, process.argv.slice(2), {
  cwd: process.cwd(),
  env,
  stdio: "inherit",
  windowsHide: false,
});

child.on("error", (error) => {
  console.error(`Could not launch the Electron runtime at ${electronPath}:`, error.message);
  process.exitCode = 1;
});
child.on("exit", (code) => {
  process.exitCode = code ?? 1;
});
