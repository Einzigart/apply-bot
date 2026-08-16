import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("electronAPI", {
  platform: process.platform,
  isElectron: true,
  openBrowserView: (url: string, bounds: { x: number; y: number; width: number; height: number }) => {
    ipcRenderer.send("browser-view:open", { url, bounds });
  },
  updateBrowserViewBounds: (bounds: { x: number; y: number; width: number; height: number }) => {
    ipcRenderer.send("browser-view:bounds", bounds);
  },
  navigateBrowserView: (url: string) => {
    ipcRenderer.send("browser-view:navigate", url);
  },
  goBackBrowserView: () => {
    ipcRenderer.send("browser-view:go-back");
  },
  goForwardBrowserView: () => {
    ipcRenderer.send("browser-view:go-forward");
  },
  reloadBrowserView: () => {
    ipcRenderer.send("browser-view:reload");
  },
  closeBrowserView: () => {
    ipcRenderer.send("browser-view:close");
  },
  onBrowserViewState: (callback: (state: { url: string; title: string; canGoBack: boolean; canGoForward: boolean; isLoading: boolean }) => void) => {
    const handler = (_: any, data: any) => callback(data);
    ipcRenderer.on("browser-view:state", handler);
    return () => ipcRenderer.removeListener("browser-view:state", handler);
  },
});
