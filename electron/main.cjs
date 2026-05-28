const path = require("node:path");
const os = require("node:os");
const { app, BrowserWindow, dialog, ipcMain } = require("electron");
const log = require("electron-log/main");
const { createBackendRuntime } = require("./python-runtime.cjs");

log.initialize();
log.transports.file.level = "info";

let mainWindow = null;
let backendRuntime = null;

function createLoadingPage(statusText) {
  return `
    <!doctype html>
    <html lang="pt-BR">
      <head>
        <meta charset="utf-8" />
        <title>LLM Forfiles</title>
        <style>
          :root {
            color-scheme: light;
            font-family: "Segoe UI", sans-serif;
            background: radial-gradient(circle at top, #f5f7fb 0%, #e4ebf5 45%, #d9e1ec 100%);
            color: #102033;
          }
          body {
            margin: 0;
            min-height: 100vh;
            display: grid;
            place-items: center;
          }
          main {
            width: min(520px, calc(100vw - 48px));
            padding: 28px;
            border-radius: 20px;
            background: rgba(255, 255, 255, 0.86);
            box-shadow: 0 18px 48px rgba(28, 44, 74, 0.14);
          }
          h1 {
            margin: 0 0 8px;
            font-size: 1.5rem;
          }
          p {
            margin: 0;
            line-height: 1.5;
            color: #415266;
          }
        </style>
      </head>
      <body>
        <main>
          <h1>Preparando o app</h1>
          <p>${statusText}</p>
        </main>
      </body>
    </html>
  `;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1500,
    height: 980,
    minWidth: 1180,
    minHeight: 760,
    show: false,
    backgroundColor: "#d9e1ec",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  return mainWindow;
}

function registerIpcHandlers(apiBaseUrl) {
  ipcMain.removeHandler("llm-forfiles:get-runtime-config");
  ipcMain.removeHandler("llm-forfiles:pick-video");
  ipcMain.removeHandler("llm-forfiles:pick-folder");

  ipcMain.handle("llm-forfiles:get-runtime-config", () => ({
    apiBaseUrl,
    homeDir: os.homedir(),
  }));

  ipcMain.handle("llm-forfiles:pick-video", async () => {
    const result = await dialog.showOpenDialog(mainWindow ?? undefined, {
      title: "Selecionar video",
      properties: ["openFile"],
      filters: [
        { name: "Videos", extensions: ["mp4", "mkv", "mov", "avi", "webm", "m4v"] },
        { name: "Todos os arquivos", extensions: ["*"] },
      ],
    });
    if (result.canceled) {
      return null;
    }
    return result.filePaths[0] ?? null;
  });

  ipcMain.handle("llm-forfiles:pick-folder", async () => {
    const result = await dialog.showOpenDialog(mainWindow ?? undefined, {
      title: "Selecionar pasta",
      defaultPath: os.homedir(),
      properties: ["openDirectory"],
    });
    if (result.canceled) {
      return null;
    }
    return result.filePaths[0] ?? null;
  });
}

async function loadRenderer(windowRef, apiBaseUrl) {
  registerIpcHandlers(apiBaseUrl);
  await windowRef.loadURL(`${apiBaseUrl}/app`);
}

async function boot() {
  const windowRef = createWindow();
  await windowRef.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(createLoadingPage("Instalando dependencias e iniciando o backend local."))}`);

  try {
    backendRuntime = createBackendRuntime({ app, log });
    const apiBaseUrl = await backendRuntime.start();
    await loadRenderer(windowRef, apiBaseUrl);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    log.error("Falha ao iniciar runtime desktop", detail);
    await windowRef.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(createLoadingPage(`Falha ao iniciar o backend: ${detail}`))}`);
    await dialog.showErrorBox("Falha ao iniciar o LLM Forfiles", detail);
  }
}

app.whenReady().then(boot);

app.on("window-all-closed", async () => {
  if (backendRuntime) {
    await backendRuntime.stop();
  }
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", async () => {
  if (backendRuntime) {
    await backendRuntime.stop();
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    boot().catch((error) => {
      log.error("Falha ao reativar a janela", error);
    });
  }
});
