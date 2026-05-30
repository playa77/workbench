export {};

declare global {
  interface Window {
    owui?: {
      onServerReady(cb: (port: number) => void): void;
      onServerError(cb: (lines: string[]) => void): void;
      onServerLog(cb: (entry: { line: string; stream: 'stdout' | 'stderr' }) => void): void;
      retry(): void;
    };
  }
}
