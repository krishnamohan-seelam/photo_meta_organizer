"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
const electronAPI = {
    openDirectory: () => electron_1.ipcRenderer.invoke('dialog:open-directory'),
    showItemInFolder: (path) => electron_1.ipcRenderer.invoke('shell:show-item-in-folder', path),
    getBackendInfo: () => electron_1.ipcRenderer.invoke('app:get-backend-info'),
    isDesktop: true,
};
electron_1.contextBridge.exposeInMainWorld('electronAPI', electronAPI);
