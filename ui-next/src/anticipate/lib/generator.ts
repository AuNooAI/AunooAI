import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../../shell';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Event = Record<string, any>;

/**
 * POSTs and reads a "data: {json}" event stream (the generator scan endpoints). Calls onEvent for
 * each event; resolves with the `complete` event. Errors, timeouts, and a stream that ends with
 * no result all reject — the old hooks missed `status: 'timeout'`, errors without a `status`
 * (newsletter), and early ends, which left the tab spinning.
 */
export async function readStream(url: string, body: unknown, onEvent: (e: Event) => void, signal: AbortSignal): Promise<Event> {
  const res = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  });
  if (res.status === 401) {
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    throw new ApiError('Signed out', 401);
  }
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => '');
    let msg = `${res.status} ${res.statusText}`;
    try {
      const d = JSON.parse(text);
      if (typeof d.detail === 'string') msg = d.detail;
    } catch {
      if (text) msg = text.slice(0, 300);
    }
    throw new ApiError(msg, res.status);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() ?? '';
    for (const part of parts) {
      const line = part.split('\n').find((l) => l.startsWith('data:'));
      if (!line) continue;
      const raw = line.slice(5).trim();
      if (!raw || raw === '[DONE]') continue;
      let ev: Event;
      try {
        ev = JSON.parse(raw);
      } catch {
        continue;
      }
      if (ev.stage === 'error' || ev.status === 'error' || ev.status === 'timeout') {
        throw new Error(String(ev.error || ev.message || (ev.status === 'timeout' ? 'The run timed out' : 'The run failed')));
      }
      if (ev.stage === 'complete') return ev;
      onEvent(ev);
    }
  }
  throw new Error('The run ended without a result. Try again.');
}

export interface Stage {
  id: string;
  label: string;
  /** Share of overall progress where this stage starts and ends (0–1). */
  from: number;
  to: number;
}

export type GenStatus = 'idle' | 'running' | 'done' | 'error';

/**
 * One generator tab: runs the stream, tracks stage and progress, keeps streamed text, and keeps
 * the last result in this browser so it is still there after a reload.
 */
export function useGenerator<R>(opts: { url: string; stages: Stage[]; storageKey: string; toResult: (complete: Event) => R }) {
  const { url, stages, storageKey, toResult } = opts;
  const [status, setStatus] = useState<GenStatus>('idle');
  const [result, setResultState] = useState<R | null>(() => {
    try {
      return JSON.parse(localStorage.getItem(storageKey) ?? 'null');
    } catch {
      return null;
    }
  });
  const [stage, setStage] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [stats, setStats] = useState<Event>({});
  const [text, setText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  useEffect(() => () => abort.current?.abort(), []);

  const setResult = useCallback(
    (r: R | null) => {
      setResultState(r);
      try {
        if (r) localStorage.setItem(storageKey, JSON.stringify(r));
        else localStorage.removeItem(storageKey);
      } catch {
        // too big or unavailable: kept for this visit
      }
    },
    [storageKey],
  );

  const run = useCallback(
    async (body: unknown) => {
      abort.current?.abort();
      const ctl = new AbortController();
      abort.current = ctl;
      setStatus('running');
      setError(null);
      setStage(stages[0]?.id ?? null);
      setProgress(0);
      setStats({});
      setText('');
      try {
        const complete = await readStream(url, { ...(body as object), stream: true }, (ev) => {
          if (ev.stage) setStage(ev.stage);
          const s = stages.find((x) => x.id === ev.stage);
          // Events carry progress within their stage (0–1) or overall (0–100)
          const p = Number(ev.progress);
          if (s && Number.isFinite(p)) setProgress(Math.round((s.from + (s.to - s.from) * (p > 1 ? p / 100 : p)) * 100));
          if (typeof ev.chunk === 'string') setText((t) => t + ev.chunk);
          setStats((x) => ({ ...x, ...ev }));
        }, ctl.signal);
        setResult(toResult(complete));
        setProgress(100);
        setStatus('done');
      } catch (e) {
        if (ctl.signal.aborted) {
          setStatus(result ? 'done' : 'idle');
          return;
        }
        setError(e instanceof Error ? e.message : String(e));
        setStatus('error');
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [url, stages, toResult, setResult],
  );

  return {
    status: status === 'idle' && result ? 'done' : status,
    result,
    setResult,
    stage,
    stageLabel: stages.find((s) => s.id === stage)?.label ?? stage ?? '',
    progress,
    stats,
    text,
    error,
    run,
    cancel: () => abort.current?.abort(),
    clear: () => { setResult(null); setStatus('idle'); setError(null); },
  };
}

export type Generator<R> = ReturnType<typeof useGenerator<R>>;
