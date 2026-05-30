import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('owui', {
  onServerReady: (cb: (port: number) => void) =>
    ipcRenderer.on('server:ready', (_event, data) => cb(data.port)),
  onServerError: (cb: (lines: string[]) => void) =>
    ipcRenderer.on('server:error', (_event, data) => cb(data.lines)),
  onServerLog: (cb: (entry: { line: string; stream: 'stdout' | 'stderr' }) => void) =>
    ipcRenderer.on('server:log', (_event, data) => cb(data)),
  retry: () => ipcRenderer.send('server:retry'),
});
