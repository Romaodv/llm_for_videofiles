const fs = require("node:fs");
const path = require("node:path");
const net = require("node:net");
const { spawn } = require("node:child_process");
const os = require("node:os");

function createBackendRuntime({ app, log }) {
  let backendProcess = null;
  let stopped = false;
  let shutdownPromise = null;

  function resolveResourcePath(...segments) {
    if (app.isPackaged) {
      return path.join(process.resourcesPath, ...segments);
    }
    return path.join(app.getAppPath(), ...segments);
  }

  function resolveProjectRoot() {
    return app.isPackaged ? process.resourcesPath : app.getAppPath();
  }

  function resolvePythonCandidates() {
    const bundledRoot = resolveResourcePath("python");
    const envPython = process.env.LLM_FORFILES_PYTHON_BIN;
    const candidates = [];
    if (envPython) {
      candidates.push(envPython);
    }
    if (process.platform === "win32") {
      candidates.push(
        path.join(bundledRoot, "python.exe"),
        path.join(bundledRoot, "Scripts", "python.exe")
      );
    } else {
      candidates.push(
        path.join(bundledRoot, "bin", "python3"),
        path.join(bundledRoot, "bin", "python"),
        path.join(bundledRoot, "python3"),
        path.join(bundledRoot, "python")
      );
      candidates.push("/usr/bin/python3", "/usr/local/bin/python3");
    }
    return candidates;
  }

  function findPythonExecutable() {
    for (const candidate of resolvePythonCandidates()) {
      if (candidate && fs.existsSync(candidate)) {
        return candidate;
      }
    }
    throw new Error(
      [
        "Nenhum runtime Python foi encontrado.",
        "Para build empacotada, coloque uma distribuicao Python completa com venv e pip em vendor/python antes de gerar o instalador.",
        "Em desenvolvimento, tambem vale definir LLM_FORFILES_PYTHON_BIN.",
      ].join(" ")
    );
  }

  function getVenvPython(venvDir) {
    return process.platform === "win32"
      ? path.join(venvDir, "Scripts", "python.exe")
      : path.join(venvDir, "bin", "python");
  }

  function runCommand(command, args, options = {}) {
    return new Promise((resolve, reject) => {
      const child = spawn(command, args, {
        cwd: options.cwd,
        env: options.env,
        stdio: ["ignore", "pipe", "pipe"],
      });
      let output = "";
      child.stdout.on("data", (chunk) => {
        const text = chunk.toString();
        output += text;
        if (text.trim()) {
          log.info(text.trim());
        }
      });
      child.stderr.on("data", (chunk) => {
        const text = chunk.toString();
        output += text;
        if (text.trim()) {
          log.warn(text.trim());
        }
      });
      child.on("error", reject);
      child.on("close", (code) => {
        if (code === 0) {
          resolve(output);
          return;
        }
        reject(new Error(`Comando falhou (${code}): ${command} ${args.join(" ")}\n${output.trim()}`));
      });
    });
  }

  function getUserRuntimePaths() {
    const runtimeRoot = path.join(app.getPath("userData"), "python-runtime");
    const toolsRoot = path.join(app.getPath("userData"), "tools");
    return {
      runtimeRoot,
      toolsRoot,
      venvDir: path.join(runtimeRoot, "venv"),
      stampPath: path.join(runtimeRoot, "install-state.json"),
      appSourceDir: path.join(runtimeRoot, "app-source"),
      dataDir: path.join(app.getPath("userData"), "data"),
      logsDir: path.join(app.getPath("logs"), "backend"),
    };
  }

  function readInstallStamp(stampPath) {
    if (!fs.existsSync(stampPath)) {
      return null;
    }
    try {
      return JSON.parse(fs.readFileSync(stampPath, "utf-8"));
    } catch {
      return null;
    }
  }

  function writeInstallStamp(stampPath, payload) {
    fs.mkdirSync(path.dirname(stampPath), { recursive: true });
    fs.writeFileSync(stampPath, JSON.stringify(payload, null, 2), "utf-8");
  }

  function copyDirectory(sourceDir, targetDir) {
    fs.mkdirSync(targetDir, { recursive: true });
    for (const entry of fs.readdirSync(sourceDir, { withFileTypes: true })) {
      const sourcePath = path.join(sourceDir, entry.name);
      const targetPath = path.join(targetDir, entry.name);
      if (entry.isDirectory()) {
        copyDirectory(sourcePath, targetPath);
        continue;
      }
      fs.copyFileSync(sourcePath, targetPath);
    }
  }

  function binaryName(name) {
    return process.platform === "win32" ? `${name}.exe` : name;
  }

  function pathContainsBinary(name, envPath = process.env.PATH || "") {
    const parts = envPath.split(path.delimiter).filter(Boolean);
    const fileName = binaryName(name);
    for (const part of parts) {
      const candidate = path.join(part, fileName);
      if (fs.existsSync(candidate)) {
        return candidate;
      }
    }
    return null;
  }

  function findBundledTool(name, toolsRoot) {
    const fileName = binaryName(name);
    const envKey = name === "ffmpeg" ? "LLM_FORFILES_FFMPEG_BIN" : "LLM_FORFILES_FFPROBE_BIN";
    const envValue = process.env[envKey];
    if (envValue && fs.existsSync(envValue)) {
      return envValue;
    }
    const fromPath = pathContainsBinary(name);
    if (fromPath) {
      return fromPath;
    }
    const localCandidate = path.join(toolsRoot, "ffmpeg", "bin", fileName);
    if (fs.existsSync(localCandidate)) {
      return localCandidate;
    }
    if (process.platform === "win32") {
      const roots = [process.env.LOCALAPPDATA, process.env.ProgramFiles, process.env["ProgramFiles(x86)"]].filter(Boolean);
      for (const root of roots) {
        const directCandidates = [
          path.join(root, "ffmpeg", "bin", fileName),
          path.join(root, "Microsoft", "WinGet", "Packages"),
        ];
        for (const candidate of directCandidates) {
          if (candidate.endsWith(fileName) && fs.existsSync(candidate)) {
            return candidate;
          }
        }
        const packagesRoot = path.join(root, "Microsoft", "WinGet", "Packages");
        if (!fs.existsSync(packagesRoot)) {
          continue;
        }
        for (const vendorDir of fs.readdirSync(packagesRoot, { withFileTypes: true })) {
          if (!vendorDir.isDirectory() || !vendorDir.name.startsWith("Gyan.FFmpeg")) {
            continue;
          }
          const vendorPath = path.join(packagesRoot, vendorDir.name);
          const stack = [vendorPath];
          while (stack.length > 0) {
            const current = stack.pop();
            if (!current) continue;
            let entries = [];
            try {
              entries = fs.readdirSync(current, { withFileTypes: true });
            } catch {
              continue;
            }
            for (const entry of entries) {
              const entryPath = path.join(current, entry.name);
              if (entry.isDirectory()) {
                stack.push(entryPath);
                continue;
              }
              if (entry.isFile() && entry.name.toLowerCase() === fileName.toLowerCase()) {
                return entryPath;
              }
            }
          }
        }
      }
    }
    return null;
  }

  async function downloadFile(url, destinationPath) {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Falha ao baixar ${url}: HTTP ${response.status}`);
    }
    const arrayBuffer = await response.arrayBuffer();
    fs.mkdirSync(path.dirname(destinationPath), { recursive: true });
    fs.writeFileSync(destinationPath, Buffer.from(arrayBuffer));
  }

  async function installPortableFfmpegWindows(toolsRoot) {
    const ffmpegRoot = path.join(toolsRoot, "ffmpeg");
    const ffmpegExe = path.join(ffmpegRoot, "bin", "ffmpeg.exe");
    if (fs.existsSync(ffmpegExe)) {
      return ffmpegExe;
    }

    const ffmpegUrl = process.env.LLM_FORFILES_FFMPEG_URL || "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip";
    const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "llm-forfiles-ffmpeg-"));
    const archivePath = path.join(tempRoot, "ffmpeg-release-essentials.zip");
    const extractRoot = path.join(tempRoot, "extract");
    fs.mkdirSync(extractRoot, { recursive: true });

    log.info(`Baixando FFmpeg portatil: ${ffmpegUrl}`);
    await downloadFile(ffmpegUrl, archivePath);
    await runCommand(
      "powershell.exe",
      ["-NoProfile", "-NonInteractive", "-Command", "Expand-Archive -LiteralPath $args[0] -DestinationPath $args[1] -Force", archivePath, extractRoot],
      { cwd: resolveProjectRoot() }
    );

    const stack = [extractRoot];
    let resolvedRoot = null;
    while (stack.length > 0) {
      const current = stack.pop();
      if (!current) continue;
      let entries = [];
      try {
        entries = fs.readdirSync(current, { withFileTypes: true });
      } catch {
        continue;
      }
      for (const entry of entries) {
        const entryPath = path.join(current, entry.name);
        if (entry.isDirectory()) {
          stack.push(entryPath);
          continue;
        }
        if (entry.isFile() && entry.name.toLowerCase() === "ffmpeg.exe") {
          resolvedRoot = path.dirname(path.dirname(entryPath));
          break;
        }
      }
      if (resolvedRoot) {
        break;
      }
    }

    if (!resolvedRoot) {
      throw new Error("Pacote do FFmpeg foi baixado, mas ffmpeg.exe nao foi encontrado apos extracao.");
    }

    fs.rmSync(ffmpegRoot, { recursive: true, force: true });
    fs.mkdirSync(toolsRoot, { recursive: true });
    fs.cpSync(resolvedRoot, ffmpegRoot, { recursive: true });
    fs.rmSync(tempRoot, { recursive: true, force: true });
    return ffmpegExe;
  }

  async function ensureFfmpegAvailable(toolsRoot) {
    const existing = findBundledTool("ffmpeg", toolsRoot);
    if (existing) {
      return existing;
    }
    if (process.platform === "win32") {
      return installPortableFfmpegWindows(toolsRoot);
    }
    return null;
  }

  function prepareWritableSource(appSourceDir) {
    const sourceBackendDir = resolveResourcePath("backend");
    const sourceFrontendDistDir = resolveResourcePath("frontend", "dist");
    const sourcePyproject = resolveResourcePath("pyproject.toml");
    const targetBackendDir = path.join(appSourceDir, "backend");
    const targetFrontendDistDir = path.join(appSourceDir, "frontend", "dist");
    const targetPyproject = path.join(appSourceDir, "pyproject.toml");

    fs.rmSync(appSourceDir, { recursive: true, force: true });
    fs.mkdirSync(appSourceDir, { recursive: true });
    copyDirectory(sourceBackendDir, targetBackendDir);
    if (fs.existsSync(sourceFrontendDistDir)) {
      copyDirectory(sourceFrontendDistDir, targetFrontendDistDir);
    }
    fs.copyFileSync(sourcePyproject, targetPyproject);
  }

  async function ensureVirtualenv(basePython, venvDir) {
    const venvPython = getVenvPython(venvDir);
    if (fs.existsSync(venvPython)) {
      return venvPython;
    }
    fs.mkdirSync(path.dirname(venvDir), { recursive: true });
    await runCommand(basePython, ["-m", "venv", venvDir], { cwd: resolveProjectRoot() });
    return venvPython;
  }

  async function ensureDependencies(basePython, venvPython, stampPath, appSourceDir) {
    const pyprojectPath = resolveResourcePath("pyproject.toml");
    const pyprojectStat = fs.statSync(pyprojectPath);
    const installStamp = readInstallStamp(stampPath);
    const alreadyInstalled =
      installStamp &&
      installStamp.pyprojectMtimeMs === pyprojectStat.mtimeMs &&
      installStamp.appVersion === app.getVersion();
    if (alreadyInstalled) {
      return;
    }

    prepareWritableSource(appSourceDir);
    await runCommand(basePython, ["-m", "ensurepip", "--upgrade"], { cwd: resolveProjectRoot() }).catch(() => {});
    await runCommand(venvPython, ["-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], {
      cwd: resolveProjectRoot(),
    });
    await runCommand(venvPython, ["-m", "pip", "install", "-e", appSourceDir], {
      cwd: appSourceDir,
      env: { ...process.env, PIP_DISABLE_PIP_VERSION_CHECK: "1" },
    });
    writeInstallStamp(stampPath, {
      pyprojectMtimeMs: pyprojectStat.mtimeMs,
      appVersion: app.getVersion(),
      installedAt: new Date().toISOString(),
    });
  }

  function getFreePort() {
    return new Promise((resolve, reject) => {
      const server = net.createServer();
      server.listen(0, "127.0.0.1", () => {
        const address = server.address();
        if (!address || typeof address === "string") {
          server.close(() => reject(new Error("Nao foi possivel reservar uma porta local.")));
          return;
        }
        const { port } = address;
        server.close(() => resolve(port));
      });
      server.on("error", reject);
    });
  }

  function waitForHealth(url, timeoutMs) {
    return new Promise((resolve, reject) => {
      const deadline = Date.now() + timeoutMs;
      const tryFetch = async () => {
        if (stopped) {
          reject(new Error("Inicializacao interrompida."));
          return;
        }
        try {
          const response = await fetch(url);
          if (response.ok) {
            resolve();
            return;
          }
        } catch {}
        if (Date.now() >= deadline) {
          reject(new Error("Backend nao respondeu ao healthcheck dentro do prazo."));
          return;
        }
        setTimeout(tryFetch, 800);
      };
      tryFetch().catch(reject);
    });
  }

  function startBackendProcess(venvPython, port, dataDir, logsDir, toolsRoot) {
    fs.mkdirSync(dataDir, { recursive: true });
    fs.mkdirSync(logsDir, { recursive: true });
    const ffmpeg = findBundledTool("ffmpeg", toolsRoot);
    const ffprobe = findBundledTool("ffprobe", toolsRoot);
    const extraPathEntries = [];
    if (ffmpeg) {
      extraPathEntries.push(path.dirname(ffmpeg));
    }
    const env = {
      ...process.env,
      LLM_FORFILES_DATA_DIR: dataDir,
      LLM_FORFILES_FFMPEG_BIN: ffmpeg || process.env.LLM_FORFILES_FFMPEG_BIN || "",
      LLM_FORFILES_FFPROBE_BIN: ffprobe || process.env.LLM_FORFILES_FFPROBE_BIN || "",
      PATH: extraPathEntries.length > 0 ? `${extraPathEntries.join(path.delimiter)}${path.delimiter}${process.env.PATH || ""}` : process.env.PATH,
      PYTHONUNBUFFERED: "1",
    };

    backendProcess = spawn(
      venvPython,
      ["-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", String(port)],
      {
        cwd: resolveProjectRoot(),
        env,
        stdio: ["ignore", "pipe", "pipe"],
      }
    );

    backendProcess.stdout.on("data", (chunk) => {
      const text = chunk.toString().trim();
      if (text) {
        log.info(`[backend] ${text}`);
      }
    });
    backendProcess.stderr.on("data", (chunk) => {
      const text = chunk.toString().trim();
      if (text) {
        log.error(`[backend] ${text}`);
      }
    });
    backendProcess.on("exit", (code) => {
      if (!stopped && code !== 0) {
        log.error(`Backend encerrado inesperadamente com codigo ${code}`);
      }
    });
  }

  async function start() {
    stopped = false;
    const { venvDir, stampPath, appSourceDir, dataDir, logsDir, toolsRoot } = getUserRuntimePaths();
    const basePython = findPythonExecutable();
    const venvPython = await ensureVirtualenv(basePython, venvDir);
    await ensureDependencies(basePython, venvPython, stampPath, appSourceDir);
    await ensureFfmpegAvailable(toolsRoot);
    const port = await getFreePort();
    startBackendProcess(venvPython, port, dataDir, logsDir, toolsRoot);
    const apiBaseUrl = `http://127.0.0.1:${port}`;
    await waitForHealth(`${apiBaseUrl}/health`, 90000);
    return apiBaseUrl;
  }

  async function stop() {
    if (shutdownPromise) {
      return shutdownPromise;
    }
    stopped = true;
    if (!backendProcess) {
      return;
    }
    shutdownPromise = new Promise((resolve) => {
      const child = backendProcess;
      backendProcess = null;
      child.once("exit", () => {
        shutdownPromise = null;
        resolve();
      });
      child.kill("SIGTERM");
      setTimeout(() => {
        if (!child.killed) {
          child.kill("SIGKILL");
        }
        shutdownPromise = null;
        resolve();
      }, 5000);
    });
    return shutdownPromise;
  }

  return { start, stop };
}

module.exports = { createBackendRuntime };
