import { useCallback, useEffect, useState } from 'react';
import { api, errorText } from '../../shell';
import { session } from '../../shell/session';

/*
 * The bundle brief editor's data: /api/forecast/brief/{cadence}/{period_label}/*
 * (app/routes/forecast_assessment_routes.py). Paths use the server's syntax:
 * `cross_cutting_themes[2].body`.
 */

export interface Finding { stage?: string; artefact_key?: string; severity?: 'info' | 'warning' | 'error'; finding?: string; suggested_fix?: string }

export interface TopicSummary {
  topic_briefing?: { headline?: string; lede?: string; intelligence_view?: string; tensions?: { name?: string; body?: string }[] };
  /** Objects on current runs ({horizon, headline, rationale}); plain strings on old ones */
  strategic_recommendations?: (Record<string, string> | string)[];
  /** Objects on current runs ({action, category}); plain strings on old ones */
  next_steps?: (Record<string, string> | string)[];
  [k: string]: unknown;
}

export interface Brief {
  cadence: string;
  period_label: string;
  payload: {
    exec_summary?: { letter?: string; signoff?: string };
    expert_commentary?: string;
    cross_cutting_themes?: Record<string, string>[];
    executive_decision_framework?: Record<string, string>[];
    whats_changed?: Record<string, string[]>;
    [k: string]: unknown;
  };
  locked_keys: string[];
  updated_at?: string;
  review: { status?: string; reviewer_findings?: Finding[]; approved_by?: string | null; approved_at?: string | null };
  per_topic: { topic: string; assessment_id: string; assessed_at?: string; summary: TopicSummary; summary_locked_keys: string[] }[];
}

export interface BriefEvent {
  id: number;
  topic: string;
  actor: string;
  action: string;
  subject: string;
  magnitude_value?: number | null;
  magnitude_unit?: string | null;
  event_date?: string | null;
  source_urls?: string[];
  confidence?: number | null;
  requires_review?: boolean;
  include_in_deck?: boolean;
  /** [{scenario, direction}]; older rows hold bare strings */
  scenario_relevance?: ({ scenario: string; direction?: string } | string)[];
  origin?: 'auto' | 'manual';
}

/** Server stage names for regenerate-stage */
export type Stage = 'exec_summary' | 'expert_commentary' | 'cross_topic' | 'briefing' | 'recommendations' | 'next_steps' | 'events';

/** Who edits: shown in the edit history */
export const editor = () => session.user.email || session.user.username || 'analyst';

/**
 * The server's own period label (wiley_delivery_service._period_label). The old editor guessed
 * "2026-Q4" when no bundle had run, which never matches the stored "Q4 2026".
 */
export function currentPeriodLabel(cadence: string, when = new Date()) {
  if (cadence === 'monthly') return when.toLocaleString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' });
  if (cadence === 'quarterly') return `Q${Math.floor(when.getUTCMonth() / 3) + 1} ${when.getUTCFullYear()}`;
  return when.toISOString().slice(0, 10);
}

export const briefBase = (cadence: string, period: string) => `/api/forecast/brief/${encodeURIComponent(cadence)}/${encodeURIComponent(period)}`;

/** Loads the brief and wraps every write; each write reloads, so locks and history stay in step. */
export function useBrief(cadence: string, period: string, notify: (m: string) => void) {
  const base = briefBase(cadence, period);
  const [brief, setBrief] = useState<Brief | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    try {
      setBrief(await api<Brief>(base));
      setError(null);
    } catch (e) {
      const t = errorText(e);
      setError(/404|no brief/i.test(t) ? `No bundle has been generated for ${cadence} “${period}” yet. Generate the bundle first.` : t);
    } finally {
      setLoading(false);
    }
  }, [base, cadence, period]);
  useEffect(() => {
    setLoading(true);
    void reload();
  }, [reload]);

  const write = async (fn: () => Promise<unknown>, done: string) => {
    try {
      await fn();
      await reload();
      notify(done);
      return true;
    } catch (e) {
      notify(`Not saved: ${errorText(e)}`);
      return false;
    }
  };

  return {
    brief, error, loading, reload, base,
    isLocked: (path: string) => Boolean(brief?.locked_keys.includes(path)),
    patch: (path: string, value: unknown) =>
      write(() => api(`${base}/field`, { method: 'PATCH', json: { path, value, edited_by: editor() } }), 'Saved'),
    lock: (path: string, locked: boolean) =>
      write(() => api(`${base}/lock`, { method: 'PATCH', json: { path, locked } }), locked ? 'Locked: a regenerate keeps it' : 'Unlocked'),
    patchTopic: (topic: string, assessmentId: string, path: string, value: unknown, lock?: boolean) =>
      write(
        () => api(`${base}/topic-field`, { method: 'PATCH', json: { topic, assessment_id: assessmentId, path, value, lock, edited_by: editor() } }),
        lock === undefined ? `Saved (${topic})` : lock ? `Locked (${topic})` : `Unlocked (${topic})`,
      ),
    approve: () => write(() => api(`${base}/approve`, { method: 'POST', json: { approved_by: editor() } }), 'Approved: the bundle can be downloaded and sent'),
  };
}
export type BriefApi = ReturnType<typeof useBrief>;
