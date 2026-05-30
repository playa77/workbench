import { ipcMain, BrowserWindow } from 'electron';
import { startServer, getServerEvents, getRecentStderr } from './server';

export function registerIpcHandlers(mainWindow: BrowserWindow): void {
  const events = getServerEvents();

  events.on('server:ready', (port: number) => {
    mainWindow.loadURL(`http://localhost:${port}`);
  });

  events.on('server:error', (lines: string[]) => {
    mainWindow.webContents.send('server:error', { lines });
  });

  events.on('server:log', (entry: { line: string; stream: 'stdout' | 'stderr' }) => {
    mainWindow.webContents.send('server:log', entry);
  });

  ipcMain.on('server:retry', () => {
    startServer();
  });
}
