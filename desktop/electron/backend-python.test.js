import { createRequire } from "node:module";
import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);
const { findBackendPython, probePython, resolveBackendDataDirectory } = require("./backend-python.cjs");

describe("managed Python startup diagnostics", () => {
  it("selects only a Python that starts and imports the backend dependencies", () => {
    const result = findBackendPython("C:/NekoAi/backend", {}, {
      existsSync: () => true,
      spawnSync: (candidate) => candidate.includes("desktop-runtime-venv")
        ? { status: 1, stdout: "", stderr: "ModuleNotFoundError: fastapi", error: null }
        : { status: 0, stdout: "3.11.9\n", stderr: "", error: null },
    });

    expect(result.usable).toBe(true);
    expect(result.version).toBe("3.11.9");
    expect(result.path).toContain(".venv");
    expect(result.failures[0]).toContain("ModuleNotFoundError: fastapi");
  });

  it("reports a broken virtual environment's missing base interpreter", () => {
    const candidate = "C:/NekoAi/backend/.venv/Scripts/python.exe";
    const missingBase = "C:/Users/example/AppData/Local/Microsoft/WindowsApps/old/python.exe";
    const result = probePython(candidate, {
      existsSync: (target) => target === candidate,
      readFileSync: () => `home = ${missingBase}\nexecutable = ${missingBase}\n`,
      spawnSync: () => ({ status: 103, stdout: "", stderr: "", error: null }),
    });

    expect(result.usable).toBe(false);
    expect(result.detail).toContain(`pyvenv.cfg executable is missing or unresolved: ${missingBase}`);
  });

  it("preserves operating-system spawn errors in the diagnostic", () => {
    const candidate = "C:/python/python.exe";
    const result = probePython(candidate, {
      existsSync: () => true,
      spawnSync: () => ({ status: null, stdout: "", stderr: "", error: new Error("Access is denied") }),
    });

    expect(result.detail).toContain("process error: Access is denied");
  });

  it("uses the interpreter-resolved path for an explicit data directory override", () => {
    const override = "C:/Users/example/AppData/Local/NekoAI";
    const redirected = "C:/Users/example/AppData/Local/Packages/Python/LocalCache/Local/NekoAI";
    let invocation;

    const resolved = resolveBackendDataDirectory("C:/NekoAi/backend/.venv/Scripts/python.exe", "C:/NekoAi/backend", override, {
      env: { PATH: "test" },
      spawnSync: (python, args, options) => {
        invocation = { python, args, options };
        return { status: 0, stdout: `${redirected}\r\n`, stderr: "" };
      },
    });

    expect(resolved.replaceAll("\\", "/")).toBe(redirected);
    expect(invocation.options.env.NEKO_DATA_DIR).toBe(override);
    expect(invocation.options.cwd).toBe("C:/NekoAi/backend");
    expect(invocation.args[0]).toContain("default_data_dir");
  });
});
