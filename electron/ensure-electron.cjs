const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

const extract = require("extract-zip");
const { downloadArtifact } = require("@electron/get");

const electronRoot = path.join(__dirname, "..", "node_modules", "electron");
const electronPackage = require(path.join(electronRoot, "package.json"));
const version = electronPackage.version;

function platformExecutable() {
  switch (process.platform) {
    case "darwin":
      return "Electron.app/Contents/MacOS/Electron";
    case "linux":
      return "electron";
    case "win32":
      return "electron.exe";
    default:
      throw new Error(`Plataforma sem suporte para bootstrap local do Electron: ${process.platform}`);
  }
}

function distRoot() {
  return path.join(electronRoot, "dist");
}

function executablePath() {
  return path.join(distRoot(), platformExecutable());
}

function pathFile() {
  return path.join(electronRoot, "path.txt");
}

function isReady() {
  return fs.existsSync(executablePath()) && fs.existsSync(pathFile());
}

async function ensureElectron() {
  if (isReady()) {
    console.log("Electron local ja esta pronto.");
    return;
  }

  console.log("Preparando binario local do Electron...");
  fs.mkdirSync(distRoot(), { recursive: true });

  const zipPath = await downloadArtifact({
    version,
    artifactName: "electron",
    platform: process.platform,
    arch: process.arch,
    cacheRoot: process.env.electron_config_cache || path.join(os.homedir(), ".cache", "electron"),
  });

  if (process.platform === "linux") {
    execFileSync("unzip", ["-o", zipPath, "-d", distRoot()], { stdio: "inherit" });
  } else {
    await extract(zipPath, { dir: distRoot() });
  }
  fs.writeFileSync(pathFile(), platformExecutable(), "utf-8");

  if (!fs.existsSync(executablePath())) {
    throw new Error(`Electron foi baixado, mas o executavel nao apareceu em ${executablePath()}`);
  }

  console.log(`Electron local pronto em ${executablePath()}`);
}

ensureElectron().catch((error) => {
  console.error(error);
  process.exit(1);
});
