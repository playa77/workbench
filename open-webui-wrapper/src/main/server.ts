import { spawn, ChildProcess } from 'child_process';
import { createServer } from 'net';
import { EventEmitter } from 'events';
import { app } from 'electron';

const SERVER_READY_EVENT = 'server:ready';
const SERVER_ERROR_EVENT = 'server:error';

let serverProcess: ChildProcess | null = null;
let selectedPort: number | null = null;
const serverEvents = new EventEmitter();

const MAX_LOG_LINES = 50;
const stdoutLines: string[] = [];
const stderrLines: string[] = [];

function timestamp(): string {
  return new Date().toTimeString().slice(0, 8);
}

function addLogLine(buffer: string[], line: string, stream: 'stdout' | 'stderr'): void {
  console.log(`[${timestamp()}] [owui-server] ${line}`);
  buffer.push(line);
  while (buffer.length > MAX_LOG_LINES) {
    buffer.shift();
  }
  serverEvents.emit('server:log', { line, stream });
}

export async function getSelectedPort(): Promise<number | null> {
  return selectedPort;
}

export function getServerEvents(): EventEmitter {
  return serverEvents;
}

export function getRecentStderr(): string[] {
  return [...stderrLines];
}

async function findFreePort(start = 8080): Promise<number> {
  const maxPort = 8180;
  for (let port = start; port <= maxPort; port++) {
    const free = await new Promise<boolean>((resolve) => {
      const server = createServer();
      server.unref();
      server.on('error', () => resolve(false));
      server.listen(port, () => {
        server.close(() => resolve(true));
      });
    });
    if (free) {
      return port;
    }
  }
  throw new Error(`No free port found in range ${start}-${maxPort}`);
}

export async function startServer(): Promise<void> {
  if (serverProcess) {
    await stopServer();
  }

  stdoutLines.length = 0;
  stderrLines.length = 0;
  selectedPort = await findFreePort();

  const env = {
    ...process.env,
    PORT: String(selectedPort),
  };

  serverProcess = spawn('uvx', ['--from', 'open-webui', 'open-webui', 'serve', '--port', String(selectedPort)], {
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  serverProcess.stdout?.on('data', (data: Buffer) => {
    const lines = data.toString().split('\n');
    for (const line of lines) {
      if (line.trim()) {
        addLogLine(stdoutLines, line, 'stdout');
      }
    }
  });

  serverProcess.stderr?.on('data', (data: Buffer) => {
    const lines = data.toString().split('\n');
    for (const line of lines) {
      if (line.trim()) {
        addLogLine(stderrLines, line, 'stderr');
      }
    }
  });

  serverProcess.on('error', (err) => {
    console.error(`[owui-server] Failed to spawn: ${err.message}`);
    serverEvents.emit(SERVER_ERROR_EVENT, getRecentStderr());
  });

  serverProcess.on('close', (code) => {
    console.log(`[owui-server] Process exited with code ${code}`);
    if (code !== 0) {
      serverEvents.emit(SERVER_ERROR_EVENT, getRecentStderr());
    }
    serverProcess = null;
    selectedPort = null;
  });

  await pollForReady();
}

async function pollForReady(): Promise<void> {
  if (!serverProcess || !selectedPort) return;

  const startTime = Date.now();
  const timeoutMs = 300_000;
  const intervalMs = 500;

  while (Date.now() - startTime < timeoutMs) {
    if (!serverProcess || serverProcess.exitCode !== null) {
      serverEvents.emit(SERVER_ERROR_EVENT, getRecentStderr());
      return;
    }

    try {
      const response = await fetch(`http://localhost:${selectedPort}/health`);
      if (response.ok) {
        serverEvents.emit(SERVER_READY_EVENT, selectedPort);
        return;
      }
    } catch {
      // Server not ready yet
    }

    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }

  console.error('[owui-server] Server failed to start within timeout');
  serverEvents.emit(SERVER_ERROR_EVENT, getRecentStderr());
}

export async function stopServer(): Promise<void> {
  if (!serverProcess || !selectedPort) return;

  return new Promise((resolve) => {
    const child = serverProcess!;

    const forceKill = () => {
      try {
        child.kill('SIGKILL');
      } catch {
        // Already dead
      }
      serverProcess = null;
      selectedPort = null;
      resolve();
    };

    child.on('close', () => {
      serverProcess = null;
      selectedPort = null;
      resolve();
    });

    child.kill('SIGTERM');

    setTimeout(forceKill, 5000);
  });
}
