import { useState, useEffect, useRef } from 'react';

interface LogEntry {
  line: string;
  stream: 'stdout' | 'stderr';
}

const STYLES: Record<string, React.CSSProperties> = {
  container: {
    height: '100vh',
    width: '100vw',
    background: '#0f0f0f',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#e0e0e0',
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  },
  spinner: {
    width: 40,
    height: 40,
    border: '4px solid #333',
    borderTop: '4px solid #6b8cff',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
    marginBottom: 20,
  },
  text: {
    fontSize: 16,
    color: '#a0a0a0',
  },
  heading: {
    fontSize: 22,
    fontWeight: 600,
    marginBottom: 12,
    color: '#f87171',
  },
  logBlock: {
    background: '#1a1a1a',
    border: '1px solid #333',
    borderRadius: 6,
    padding: 16,
    fontSize: 12,
    fontFamily: 'monospace',
    color: '#c0c0c0',
    maxWidth: '80vw',
    maxHeight: '40vh',
    overflow: 'auto',
    whiteSpace: 'pre-wrap',
    marginBottom: 16,
    lineHeight: 1.5,
  },
  retryBtn: {
    padding: '10px 28px',
    fontSize: 14,
    fontWeight: 500,
    background: '#6b8cff',
    color: '#fff',
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
  },
};

export default function App() {
  const [state, setState] = useState<'loading' | 'error'>('loading');
  const [errorLines, setErrorLines] = useState<string[]>([]);
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!window.owui) return;

    window.owui.onServerLog((entry: LogEntry) => {
      setLogEntries((prev) => {
        const next = [...prev, entry];
        return next.length > 200 ? next.slice(-200) : next;
      });
    });

    window.owui.onServerError((lines: string[]) => {
      setErrorLines(lines);
      setState('error');
    });
  }, []);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logEntries]);

  const handleRetry = () => {
    setState('loading');
    setErrorLines([]);
    setLogEntries([]);
    window.owui?.retry();
  };

  if (state === 'loading') {
    return (
      <div style={STYLES.container}>
        <>
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
          <div style={STYLES.spinner} />
          <div style={STYLES.text}>Starting Open WebUI…</div>
          {logEntries.length > 0 && (
            <pre style={{ ...STYLES.logBlock, marginTop: 20 }}>
              {logEntries.map((e, i) => (
                <div
                  key={i}
                  style={{ color: e.stream === 'stderr' ? '#f87171' : '#c0c0c0' }}
                >
                  {e.line}
                </div>
              ))}
              <div ref={logEndRef} />
            </pre>
          )}
        </>
      </div>
    );
  }

  return (
    <div style={STYLES.container}>
      <div style={STYLES.heading}>Open WebUI failed to start</div>
      {errorLines.length > 0 && (
        <pre style={STYLES.logBlock}>{errorLines.join('\n')}</pre>
      )}
      <button style={STYLES.retryBtn} onClick={handleRetry}>
        Retry
      </button>
    </div>
  );
}
