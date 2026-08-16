import { contextBridge } from "electron";

const api = {
  platform: process.platform,
  isElectron: true,
};

try {
  contextBridge.exposeInMainWorld("electronAPI", api);
} catch {
  (window as any).electronAPI = api;
}
(window as any).electronAPI = api;
