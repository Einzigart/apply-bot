import { contextBridge } from "electron";

const api = {
  platform: process.platform,
  isElectron: true,
};

contextBridge.exposeInMainWorld("electronAPI", api);
