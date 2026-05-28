const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");

const builderCli = path.join(__dirname, "..", "node_modules", "electron-builder", "cli.js");
const args = process.argv.slice(2);

const child = spawn(process.execPath, [builderCli, ...args], {
  cwd: path.join(__dirname, ".."),
  stdio: "inherit",
  env: {
    ...process.env,
    CSC_IDENTITY_AUTO_DISCOVERY: process.env.CSC_IDENTITY_AUTO_DISCOVERY || "false",
    ELECTRON_BUILDER_CACHE: process.env.ELECTRON_BUILDER_CACHE || path.join(os.tmpdir(), "llm-forfiles-electron-builder-cache"),
  },
});

child.on("exit", (code) => {
  process.exit(code ?? 1);
});

child.on("error", (error) => {
  console.error(error);
  process.exit(1);
});
