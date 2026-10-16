import { useCallback, useEffect, useRef, useState } from 'react';
import { readSSEStream } from './sse';
import type { DetectionProgress, EmergingTopic } from './types';
import type { EmergingTopicsConfig } from '../overlays/ConfigDialog';

/*
 * Detection runs as a server-side job (POST /api/emerging-topics/detect/jobs), as on the old page.
 * The page only listens to its progress stream: leaving the page detaches the listener and the job
 * keeps going. On load the page re-attaches to a job that is still running (remembered in
 * localStorage, or found through /detect/jobs/active). Sites whose backend predates jobs answer 404,
 * and the run then streams over the request itself, as it used to.
 */

const JOB_KEY = 'emergingTopics.activeJob';
const store = {
  get: () => { try { return localStorage.getItem(JOB_KEY); } catch { return null; } },
  set: (v: string) => { try { localStorage.setItem(JOB_KEY, v); } catch { /* per visit only */ } },
  clear: () => { try { localStorage.removeItem(JOB_KEY); } catch { /* per visit only */ } },
};
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const conflictText = async (res: Response) => {
  const body = await res.json().catch(() => null) as { detail?: { message?: string } | string } | null;
  const d = body?.detail;
  return (typeof d === 'string' ? d : d?.message) || 'A detection run is already in progress for this topic.';
};

interface Options {
  topic?: string;
  /** Called with interim themes while a run streams them */
  onTopics: (t: EmergingTopic[]) => void;
  /** Called once a run ends, however it ended, to reload the lists */
  onFinished: () => void;
}

export function useDetection({ topic, onTopics, onFinished }: Options) {
  const [detecting, setDetecting] = useState(false);
  const [progress, setProgress] = useState<DetectionProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  const attached = useRef<string | null>(null);
  const cb = useRef({ onTopics, onFinished });
  cb.current = { onTopics, onFinished };

  const stopTimer = () => {
    if (timer.current !== null) window.clearInterval(timer.current);
    timer.current = null;
  };
  // Elapsed time ticks locally between server updates, so the panel never looks dead during a long model call
  const startTimer = (t0: number) => {
    stopTimer();
    timer.current = window.setInterval(() => setProgress((p) => (p ? { ...p, elapsed_seconds: (Date.now() - t0) / 1000 } : p)), 1000);
  };

  const finish = useCallback(() => {
    stopTimer();
    attached.current = null;
    store.clear();
    setDetecting(false);
    setProgress(null);
    cb.current.onFinished();
  }, []);

  const attach = useCallback(async (jobId: string, startedAt?: number) => {
    if (attached.current === jobId) return;
    attached.current = jobId;
    setDetecting(true);
    store.set(jobId);
    startTimer(startedAt ? startedAt * 1000 : Date.now());

    let after = 0;
    let terminal: 'complete' | 'error' | null = null;
    let streamError: string | null = null;
    let attempts = 0;
    while (!terminal && attached.current === jobId) {
      try {
        const res = await fetch(`/api/emerging-topics/detect/jobs/${jobId}/events?after=${after}`, { credentials: 'same-origin' });
        if (res.status === 404) { streamError = 'The detection job no longer exists (the service may have restarted).'; break; }
        if (!res.ok || !res.body) throw new Error(`Progress stream failed: ${res.status}`);
        attempts = 0;
        await readSSEStream(res.body, (ev) => {
          const data = ev.data as DetectionProgress | null;
          if (!data) return;
          if (ev.event === 'heartbeat') {
            setProgress((p) => (p ? { ...p, elapsed_seconds: data.elapsed_seconds } : p));
            return;
          }
          if (typeof data.seq === 'number') after = data.seq + 1;
          // A batch reports per-topic errors and carries on; only a final error frame ends the job
          if (ev.event === 'error') streamError = data.message || 'Detection failed';
          if (ev.event === 'complete') terminal = 'complete';
          setProgress(data);
          if (data.emerging_topics) cb.current.onTopics(data.emerging_topics);
        });
        if (!terminal) {
          // The stream closed: the job ended on an error frame or the connection dropped. Ask, then reconnect or stop.
          const s = await fetch(`/api/emerging-topics/detect/jobs/${jobId}`, { credentials: 'same-origin' });
          if (s.ok) {
            const info = await s.json() as { status?: string };
            if (info.status !== 'running') terminal = info.status === 'failed' ? 'error' : 'complete';
          }
          if (!terminal) await sleep(2000);
        }
      } catch (e) {
        attempts += 1;
        if (attempts > 30) { streamError = e instanceof Error ? e.message : 'Lost the progress stream'; break; }
        await sleep(Math.min(15000, 1000 * attempts));
      }
    }
    if (attached.current !== jobId) return; // superseded
    if (terminal === 'error' || (streamError && terminal !== 'complete')) setError(streamError || 'Detection failed');
    finish();
  }, [finish]);

  const runInline = async (body: Record<string, unknown>) => {
    const endpoint = topic ? '/api/emerging-topics/detect' : '/api/emerging-topics/detect/batch';
    startTimer(Date.now());
    try {
      const res = await fetch(endpoint, {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(topic ? { ...body, stream: true } : body),
      });
      if (res.status === 409) throw new Error(await conflictText(res));
      if (!res.ok || !res.body) throw new Error(`Detection failed: ${res.status}`);
      let streamError: string | null = null;
      await readSSEStream(res.body, (ev) => {
        const data = ev.data as DetectionProgress | null;
        if (!data) return;
        if (ev.event === 'error') { streamError = data.message || 'Detection failed'; return; }
        setProgress((p) => ({ ...data, elapsed_seconds: p?.elapsed_seconds ?? 0 }));
        if (data.emerging_topics) cb.current.onTopics(data.emerging_topics);
      });
      if (streamError) throw new Error(streamError);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Detection failed');
    }
    finish();
  };

  /** Calls the AI. Starts a run over the picked topic, or every configured topic when none is picked. */
  const run = async (config: EmergingTopicsConfig) => {
    setDetecting(true);
    setProgress({ message: 'Starting detection…', progress: 0, elapsed_seconds: 0 });
    setError(null);
    const body = {
      topic: topic || null,
      topics: null,
      days_back: config.daysBack,
      sample_size: config.sampleSize,
      distance_threshold: config.distanceThreshold,
      min_articles_per_theme: config.minArticlesPerTheme,
      max_articles_per_theme: config.maxArticlesPerTheme,
      model: config.model,
    };
    try {
      const res = await fetch('/api/emerging-topics/detect/jobs', {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      if (res.status === 409) throw new Error(await conflictText(res));
      if (res.status === 404) {
        await runInline(body);
        return;
      }
      if (!res.ok) throw new Error(`Detection failed: ${res.status}`);
      const job = await res.json() as { job_id: string; started_at?: number };
      await attach(job.job_id, job.started_at);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Detection failed');
      stopTimer();
      setDetecting(false);
      setProgress(null);
    }
  };

  // Re-attach to a job still running when the page opens. Reads only.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      let jobId = store.get();
      let startedAt: number | undefined;
      if (jobId) {
        const r = await fetch(`/api/emerging-topics/detect/jobs/${jobId}`, { credentials: 'same-origin' }).catch(() => null);
        const info = r && r.ok ? await r.json() as { status?: string; started_at?: number } : null;
        if (!info || info.status !== 'running') {
          jobId = null;
          store.clear();
        } else startedAt = info.started_at;
      }
      if (!jobId) {
        const r = await fetch('/api/emerging-topics/detect/jobs/active', { credentials: 'same-origin' }).catch(() => null);
        const info = r && r.ok ? await r.json() as { jobs?: { job_id: string; scope: string; started_at?: number }[] } : null;
        const running = info?.jobs?.find((j) => !topic || j.scope === topic || j.scope === '<all>');
        if (running) {
          jobId = running.job_id;
          startedAt = running.started_at;
        }
      }
      if (jobId && !cancelled) {
        setProgress({ message: 'Re-attaching to the running detection…', progress: 0, elapsed_seconds: 0 });
        void attach(jobId, startedAt);
      }
    })();
    return () => {
      cancelled = true;
      stopTimer();
      // Stop listening when the tab closes; the job carries on on the server
      attached.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { detecting, progress, error, setError, run };
}
