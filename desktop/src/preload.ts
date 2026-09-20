import { contextBridge, ipcRenderer } from 'electron';

export interface ElectronAPI {
  openDirectory: () => Promise<string | null>;
  showItemInFolder: (path: string) => Promise<void>;
  getBackendInfo: () => Promise<{ port: number; host: string; baseUrl: string }>;
  isDesktop: boolean;
}

const electronAPI: ElectronAPI = {
  openDirectory: () => ipcRenderer.invoke('dialog:open-directory'),
  showItemInFolder: (path: string) => ipcRenderer.invoke('shell:show-item-in-folder', path),
  getBackendInfo: () => ipcRenderer.invoke('app:get-backend-info'),
  isDesktop: true,
};

contextBridge.exposeInMainWorld('electronAPI', electronAPI);
