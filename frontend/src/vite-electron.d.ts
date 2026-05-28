interface DesktopRuntimeConfig {
  apiBaseUrl: string;
  homeDir?: string;
}

interface Window {
  llmForfilesDesktop?: {
    getRuntimeConfig(): Promise<DesktopRuntimeConfig>;
    pickVideo(): Promise<string | null>;
    pickFolder(): Promise<string | null>;
  };
}
