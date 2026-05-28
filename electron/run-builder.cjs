const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");

const builderBin = path.join(__dirname, "..", "node_modules", ".bin", process.platform === "win32" ? "electron-builder.cmd" : "electron-builder");
const args = process.argv.slice(2);

const child = spawn(builderBin, args, {
  cwd: path.join(__dirname, ".."),
  stdio: "inherit",
  env: {
    ...process.env,
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
