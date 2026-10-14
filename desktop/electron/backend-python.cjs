const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

function resolveBackendDataDirectory(python, backendDir, override, options = {}) {
  const run = options.spawnSync || spawnSync;
  const env = { ...(options.env || process.env), NEKO_DATA_DIR: override || "" };
  const result = run(python, ["-c", "from app.core.config import default_data_dir; print(default_data_dir())"], {
    cwd: backendDir,
    encoding: "utf8",
    timeout: 10000,
    windowsHide: true,
    env,
  });
  const resolved = result.stdout?.trim().split(/\r?\n/).at(-1);
  if (result.status !== 0 || !resolved || !path.isAbsolute(resolved)) {
    const details = [result.error?.message, result.stderr?.trim(), result.stdout?.trim()].filter(Boolean).join("\n");
    throw new Error(`Could not resolve the backend data directory using ${python}.${details ? `\n${details}` : ""}`);
  }
  return path.resolve(resolved);
}

function probePython(candidate, options = {}) {
  const existsSync = options.existsSync || fs.existsSync;
  const readFileSync = options.readFileSync || fs.readFileSync;
  const run = options.spawnSync || spawnSync;

  if (!existsSync(candidate)) return { usable: false, detail: `${candidate}: executable not found` };

  const result = run(candidate, ["-c", "import sys, fastapi, uvicorn; print(sys.version.split()[0])"], {
    timeout: 10000,
    windowsHide: true,
    encoding: "utf8",
    stdio: "pipe",
  });
  if (result.status === 0) return { usable: true, path: candidate, version: result.stdout.trim() };

  const details = [];
  if (result.error) details.push(`process error: ${result.error.message}`);
  if (result.status !== null && result.status !== undefined) details.push(`exit code ${result.status}`);
  if (result.signal) details.push(`signal ${result.signal}`);
  const output = [result.stdout, result.stderr].filter(Boolean).join("\n").trim();
  if (output) details.push(output);

  const configPath = path.join(path.dirname(path.dirname(candidate)), "pyvenv.cfg");
  try {
    const config = readFileSync(configPath, "utf8");
    const home = config.match(/^home\s*=\s*(.+)$/mi)?.[1]?.trim();
    const executable = config.match(/^executable\s*=\s*(.+)$/mi)?.[1]?.trim();
    if (executable && !existsSync(executable)) details.push(`pyvenv.cfg executable is missing or unresolved: ${executable}`);
    else if (home && !existsSync(home)) details.push(`pyvenv.cfg base Python directory is missing: ${home}`);
    else if (home) details.push(`pyvenv.cfg base Python directory: ${home}`);
  } catch { /* Custom Python executables do not have a venv config. */ }

  return { usable: false, detail: `${candidate}: ${details.join("; ") || "could not import fastapi and uvicorn"}` };
}

function findBackendPython(backendDir, env = process.env, options = {}) {
  const candidates = [env.NEKO_PYTHON].filter(Boolean);
  for (const directory of ["desktop-runtime-venv", ".venv", "venv"]) {
    candidates.push(path.join(backendDir, directory, "Scripts", "python.exe"));
  }

  const failures = [];
  for (const candidate of candidates) {
    const probe = probePython(candidate, options);
    if (probe.usable) return { ...probe, failures };
    failures.push(probe.detail);
  }
  return { usable: false, failures };
}

module.exports = { findBackendPython, probePython, resolveBackendDataDirectory };
