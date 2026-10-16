import { useCallback, useEffect, useRef, useState } from 'react';
import { api, errorText } from '../../shell';

/** Background task as GET …/job/{id} returns it (app/services/background_task_manager.py). */
export interface Job {
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | string;
  progress?: number;
  current_item?: string;
  error?: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  result?: any;
}

export type JobState =
  | { kind: 'idle' }
  | { kind: 'running'; pct: number; message: string }
  | { kind: 'done'; job: Job }
  | { kind: 'failed'; message: string };

/**
 * Polls a background job until it ends. Stops on unmount, and on 404: tasks live in server
 * memory, so a restart loses them (the old page kept polling forever then).
 */
export function useJob(intervalMs = 3000) {
  const [state, setState] = useState<JobState>({ kind: 'idle' });
  const timer = useRef<number | undefined>(undefined);
  const stop = useCallback(() => window.clearTimeout(timer.current), []);
  useEffect(() => stop, [stop]);

  const watch = useCallback(
    (statusUrl: string, onDone?: (job: Job) => void) => {
      stop();
      setState({ kind: 'running', pct: 0, message: 'Starting…' });
      const tick = async () => {
        try {
          const job = await api<Job>(statusUrl);
          if (job.status === 'completed') {
            setState({ kind: 'done', job });
            onDone?.(job);
            return;
          }
          if (job.status === 'failed' || job.status === 'cancelled') {
            setState({ kind: 'failed', message: job.error || `Job ${job.status}` });
            return;
          }
          setState({ kind: 'running', pct: Math.round(Number(job.progress) || 0), message: job.current_item || 'Working…' });
          timer.current = window.setTimeout(tick, intervalMs);
        } catch (e) {
          const msg = errorText(e);
          setState({ kind: 'failed', message: /404|not found/i.test(msg) ? 'The job was lost (the server restarted). Run it again.' : msg });
        }
      };
      void tick();
    },
    [intervalMs, stop],
  );

  return { state, watch, reset: () => { stop(); setState({ kind: 'idle' }); } };
}

/** "3 days ago" for an ISO date; null when there's no date. */
export function daysAgo(iso?: string | null) {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return null;
  return Math.floor((Date.now() - t) / 86400000);
}

export const fmtDate = (iso?: string | null) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
};
