export interface ElectronAPI {
  openDirectory: () => Promise<string | null>;
  showItemInFolder: (path: string) => Promise<void>;
  getBackendInfo: () => Promise<{ port: number; host: string; baseUrl: string }>;
  isDesktop: boolean;
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI;
  }
}
