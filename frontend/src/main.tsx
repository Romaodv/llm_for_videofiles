import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";

declare global {
  interface Window {
    __LLM_FORFILES_API_BASE__?: string;
    __LLM_FORFILES_HOME_DIR__?: string;
  }
}

async function bootstrap() {
  if (window.llmForfilesDesktop?.getRuntimeConfig) {
    const runtimeConfig = await window.llmForfilesDesktop.getRuntimeConfig();
    if (runtimeConfig?.apiBaseUrl) {
      window.__LLM_FORFILES_API_BASE__ = runtimeConfig.apiBaseUrl;
    }
    if (runtimeConfig?.homeDir) {
      window.__LLM_FORFILES_HOME_DIR__ = runtimeConfig.homeDir;
    }
  }

  createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}

void bootstrap();
