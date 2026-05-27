/**
 * Candidates inbox — emerging clusters the weekly scan flagged as
 * in_scope / adjacent for the Wiley track. Analyst triages each one:
 * promote (auto-fires horizons + assessment + draft overlay), snooze,
 * reject, or merge into an existing tracked topic.
 *
 * Backed by GET /api/forecast/candidates and the POST .../{id}/{action}
 * endpoints. Polls a promote-job's progress and forwards the resulting
 * topic up to the parent so the wizard can open at step 4.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Loader2, RefreshCw, Sparkles, AlertTriangle, X, Clock, GitMerge,
  ChevronDown, ChevronUp, Play,
} from 'lucide-react';
import { Button } from '@/components/ui/button';

type Verdict = 'in_scope' | 'adjacent' | 'off_scope';
type Triage = 'pending' | 'snoozed' | 'rejected' | 'promoted' | 'merged';

interface CandidateRow {
  id: number;
  emerging_topic_id: number;
  relevance_verdict: Verdict;
  relevance_score: number | null;
  relevance_rationale: string | null;
  proposed_topic_name: string | null;
  proposed_description: string | null;
  proposed_tags: string[] | null;
  triage_status: Triage;
  snooze_until: string | null;
  rejected_reason: string | null;
  promoted_to_topic: string | null;
  triaged_at: string | null;
  created_at: string;
  // From the emerging-topic join
  topic_label: string;
  topic_description: string | null;
  article_count: number | null;
  growth_rate: number | null;
  velocity: string | null;
  avg_novelty_score: number | null;
  et_confidence: number | null;
  key_themes: any;
  representative_keywords: any;
  sample_article_uris: string[] | null;
  detection_date: string | null;
  detection_type: string | null;
}

interface Props {
  /** Existing tracked-topic names — populates the merge picker. */
  knownTopics: string[];
  /** Called when promotion finishes; parent navigates to wizard step 4. */
  onPromotionComplete?: (topic: string) => void;
}

const VERDICT_CHIP: Record<Verdict, string> = {
  in_scope: 'bg-emerald-100 text-emerald-900 dark:bg-emerald-800/50 dark:text-emerald-100',
  adjacent: 'bg-amber-100 text-amber-900 dark:bg-amber-800/50 dark:text-amber-100',
  off_scope: 'bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-200',
};

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return `${Math.round(v * 100)}%`;
}

function fmtRelativeDate(iso: string | null): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso).getTime();
    if (Number.isNaN(d)) return '—';
    const days = Math.floor((Date.now() - d) / (1000 * 60 * 60 * 24));
    if (days < 1) return 'today';
    if (days === 1) return '1d ago';
    return `${days}d ago`;
  } catch { return '—'; }
}

function asList(value: any): string[] {
  if (!value) return [];
  if (Array.isArray(value)) return value.map(String);
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed.map(String) : [];
    } catch { return []; }
  }
  return [];
}

export function CandidatesInbox({ knownTopics, onPromotionComplete }: Props) {
  const [rows, setRows] = useState<CandidateRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] =
    useState<'pending' | 'snoozed' | 'rejected' | 'promoted' | 'all'>('pending');
  const [scanning, setScanning] = useState(false);
  const [scanTaskId, setScanTaskId] = useState<string | null>(null);
  const [busy, setBusy] = useState<Record<number, string>>({});
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const url = `/api/forecast/candidates?triage_status=${statusFilter}`;
      const r = await fetch(url);
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const data = await r.json();
      setRows((data.candidates || []) as CandidateRow[]);
    } catch (e: any) {
      setError(e?.message || 'Failed to load candidates');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => { refresh(); }, [refresh]);

  // Poll a scan/promote job until it finishes.
  const pollJob = useCallback(async (taskId: string, onDone?: (status: any) => void) => {
    const start = Date.now();
    while (Date.now() - start < 15 * 60 * 1000) {  // 15 min cap
      try {
        const r = await fetch(`/api/forecast/candidates/job/${taskId}`);
        if (!r.ok) throw new Error(`${r.status}`);
        const status = await r.json();
        if (status.status === 'completed' || status.status === 'error' ||
            status.status === 'failed') {
          if (onDone) onDone(status);
          return status;
        }
      } catch (e) {
        // Transient network errors are fine — keep polling.
      }
      await new Promise(res => setTimeout(res, 3000));
    }
    return null;
  }, []);

  const startScan = useCallback(async () => {
    setScanning(true);
    try {
      const r = await fetch('/api/forecast/candidates/scan', { method: 'POST' });
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const data = await r.json();
      setScanTaskId(data.task_id);
      await pollJob(data.task_id);
      setScanTaskId(null);
      await refresh();
    } catch (e: any) {
      setError(e?.message || 'Scan failed');
    } finally {
      setScanning(false);
    }
  }, [pollJob, refresh]);

  const act = useCallback(async (id: number, action: string, body?: any, label?: string) => {
    setBusy(prev => ({ ...prev, [id]: label || action }));
    try {
      const r = await fetch(`/api/forecast/candidates/${id}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body || {}),
      });
      if (!r.ok) {
        const text = await r.text();
        throw new Error(`${r.status}: ${text}`);
      }
      const data = await r.json();
      // Promote returns a task_id — poll the background job.
      if (action === 'promote' && data?.task_id) {
        const status = await pollJob(data.task_id);
        const topic = status?.result?.topic;
        if (topic && onPromotionComplete) onPromotionComplete(topic);
      }
      await refresh();
    } catch (e: any) {
      setError(e?.message || `${action} failed`);
    } finally {
      setBusy(prev => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
    }
  }, [pollJob, refresh, onPromotionComplete]);

  const summary = useMemo(() => {
    const data = rows || [];
    return {
      n: data.length,
      in_scope: data.filter(r => r.relevance_verdict === 'in_scope').length,
      adjacent: data.filter(r => r.relevance_verdict === 'adjacent').length,
    };
  }, [rows]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Candidates</h2>
          <p className="text-xs text-gray-600 dark:text-gray-300 mt-0.5">
            {summary.n} {statusFilter} · {summary.in_scope} in-scope · {summary.adjacent} adjacent.
            Promote to track formally, snooze if too early, reject if off-topic, or merge into an existing topic.
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as any)}
            className="text-xs px-2 py-1 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100"
          >
            <option value="pending">Pending</option>
            <option value="snoozed">Snoozed</option>
            <option value="rejected">Rejected</option>
            <option value="promoted">Promoted</option>
            <option value="all">All</option>
          </select>
          <button
            type="button"
            onClick={refresh}
            className="inline-flex items-center text-xs px-2 py-1 border border-gray-300 dark:border-gray-700 rounded text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <RefreshCw className="w-3 h-3 mr-1" /> Refresh
          </button>
          <Button
            type="button"
            onClick={startScan}
            disabled={scanning}
            className="text-xs h-7 py-0 px-3 bg-pink-600 hover:bg-pink-700 text-white"
            title="Run the emerging-themes scan over the last 14 days and judge new clusters against the Wiley brief."
          >
            {scanning ? (
              <><Loader2 className="w-3 h-3 mr-1 animate-spin" /> Scanning…</>
            ) : (
              <><Sparkles className="w-3 h-3 mr-1" /> Scan now</>
            )}
          </Button>
        </div>
      </div>

      {scanning && scanTaskId && (
        <div className="text-xs px-3 py-2 bg-pink-50 dark:bg-pink-900/30 border border-pink-200 dark:border-pink-800 text-pink-900 dark:text-pink-100 rounded">
          Running detection + Wiley-fit judging. Job <code className="font-mono">{scanTaskId}</code>.
          This typically takes 2–6 minutes depending on corpus size.
        </div>
      )}

      {error && (
        <div className="text-xs px-3 py-2 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-900 dark:text-red-100 rounded flex items-center gap-2">
          <AlertTriangle className="w-3 h-3" /> {error}
          <button onClick={() => setError(null)} className="ml-auto"><X className="w-3 h-3" /></button>
        </div>
      )}

      {loading && !rows ? (
        <div className="flex items-center text-xs text-gray-600 dark:text-gray-300">
          <Loader2 className="w-3 h-3 mr-2 animate-spin" /> Loading candidates…
        </div>
      ) : (rows || []).length === 0 ? (
        <div className="text-xs text-gray-600 dark:text-gray-300 italic p-6 border border-dashed border-gray-300 dark:border-gray-700 rounded text-center">
          No {statusFilter} candidates. The weekly scan runs automatically — click "Scan now" to force a fresh pass.
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
          {(rows || []).map(c => {
            const isBusy = !!busy[c.id];
            const themes = asList(c.key_themes).slice(0, 4);
            const kws = asList(c.representative_keywords).slice(0, 6);
            const sampleUris = (c.sample_article_uris || []).slice(0, 5);
            return (
              <div key={c.id} className="border border-gray-200 dark:border-gray-700 rounded p-3 bg-white dark:bg-gray-900 space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${VERDICT_CHIP[c.relevance_verdict]}`}>
                        {c.relevance_verdict.replace('_', '-')}
                      </span>
                      <span className="text-[10px] text-gray-500 dark:text-gray-400">
                        score {fmtPct(c.relevance_score)}
                      </span>
                    </div>
                    <h3 className="font-semibold text-sm text-gray-900 dark:text-gray-100 mt-1">
                      {c.proposed_topic_name || c.topic_label}
                    </h3>
                  </div>
                  <div className="text-[10px] text-gray-500 dark:text-gray-400 text-right shrink-0">
                    detected<br />{fmtRelativeDate(c.detection_date)}
                  </div>
                </div>

                <p className="text-xs text-gray-700 dark:text-gray-200 line-clamp-3">
                  {c.proposed_description || c.topic_description || c.relevance_rationale || ''}
                </p>

                {c.relevance_rationale && c.proposed_description && (
                  <p className="text-[10px] italic text-gray-500 dark:text-gray-400 line-clamp-2">
                    judge: {c.relevance_rationale}
                  </p>
                )}

                <div className="grid grid-cols-4 gap-1 text-[10px]">
                  <Stat label="articles" value={c.article_count} />
                  <Stat label="growth" value={c.growth_rate != null ? `${(c.growth_rate * 100).toFixed(0)}%` : null} />
                  <Stat label="novelty" value={c.avg_novelty_score != null ? c.avg_novelty_score.toFixed(0) : null} />
                  <Stat label="velocity" value={c.velocity || null} />
                </div>

                {themes.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {themes.map(t => (
                      <span key={t} className="text-[10px] px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/40 text-blue-900 dark:text-blue-100">
                        {t}
                      </span>
                    ))}
                  </div>
                )}

                {(c.proposed_tags || []).length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {(c.proposed_tags || []).map(t => (
                      <span key={t} className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200">
                        #{t}
                      </span>
                    ))}
                  </div>
                )}

                {sampleUris.length > 0 && (
                  <div>
                    <button
                      type="button"
                      onClick={() => setExpanded(prev => ({ ...prev, [c.id]: !prev[c.id] }))}
                      className="text-[10px] text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 inline-flex items-center"
                    >
                      {expanded[c.id] ? <ChevronUp className="w-3 h-3 mr-0.5" /> : <ChevronDown className="w-3 h-3 mr-0.5" />}
                      {sampleUris.length} sample article{sampleUris.length > 1 ? 's' : ''}
                      {kws.length > 0 && ` · keywords: ${kws.join(', ')}`}
                    </button>
                    {expanded[c.id] && (
                      <ul className="mt-1 ml-3 list-disc text-[10px] text-gray-600 dark:text-gray-300 space-y-0.5">
                        {sampleUris.map(uri => (
                          <li key={uri}>
                            <a href={uri} target="_blank" rel="noreferrer" className="hover:underline break-all">
                              {uri}
                            </a>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}

                {c.triage_status === 'pending' && (
                  <CardActions
                    isBusy={isBusy}
                    busyLabel={busy[c.id]}
                    knownTopics={knownTopics}
                    onPromote={() => act(c.id, 'promote', {}, 'Promoting')}
                    onSnooze={(days) => act(c.id, 'snooze', { days }, `Snoozing ${days}d`)}
                    onReject={(reason) => act(c.id, 'reject', { reason }, 'Rejecting')}
                    onMerge={(into_topic) => act(c.id, 'merge', { into_topic }, 'Merging')}
                  />
                )}
                {c.triage_status !== 'pending' && (
                  <div className="text-[10px] text-gray-500 dark:text-gray-400 italic pt-1 border-t border-gray-100 dark:border-gray-800">
                    {c.triage_status === 'snoozed' && c.snooze_until && `Snoozed until ${c.snooze_until}`}
                    {c.triage_status === 'rejected' && (c.rejected_reason || 'rejected')}
                    {c.triage_status === 'promoted' && c.promoted_to_topic && `Promoted to '${c.promoted_to_topic}'`}
                    {c.triage_status === 'merged' && c.promoted_to_topic && `Merged into '${c.promoted_to_topic}'`}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: any }) {
  return (
    <div className="text-center bg-gray-50 dark:bg-gray-800 rounded p-1">
      <div className="font-medium text-gray-900 dark:text-gray-100">{value ?? '—'}</div>
      <div className="text-gray-500 dark:text-gray-400 leading-none">{label}</div>
    </div>
  );
}

function CardActions(props: {
  isBusy: boolean;
  busyLabel?: string;
  knownTopics: string[];
  onPromote: () => void;
  onSnooze: (days: number) => void;
  onReject: (reason: string) => void;
  onMerge: (into_topic: string) => void;
}) {
  const [showReject, setShowReject] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [showMerge, setShowMerge] = useState(false);
  const [mergeTarget, setMergeTarget] = useState('');

  if (props.isBusy) {
    return (
      <div className="pt-1 border-t border-gray-100 dark:border-gray-800 flex items-center text-[10px] text-gray-600 dark:text-gray-300">
        <Loader2 className="w-3 h-3 mr-1 animate-spin" /> {props.busyLabel || 'Working…'}
      </div>
    );
  }

  if (showReject) {
    return (
      <div className="pt-1 border-t border-gray-100 dark:border-gray-800 space-y-1">
        <input
          autoFocus
          type="text"
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
          placeholder="Reason (e.g. 'not Wiley-relevant')"
          className="text-[10px] w-full px-2 py-1 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100"
        />
        <div className="flex gap-1">
          <button onClick={() => { props.onReject(rejectReason); setShowReject(false); }}
            className="text-[10px] px-2 py-0.5 bg-red-600 hover:bg-red-700 text-white rounded">
            Reject
          </button>
          <button onClick={() => setShowReject(false)}
            className="text-[10px] px-2 py-0.5 border border-gray-300 dark:border-gray-700 rounded text-gray-700 dark:text-gray-200">
            Cancel
          </button>
        </div>
      </div>
    );
  }

  if (showMerge) {
    return (
      <div className="pt-1 border-t border-gray-100 dark:border-gray-800 space-y-1">
        <select
          autoFocus
          value={mergeTarget}
          onChange={(e) => setMergeTarget(e.target.value)}
          className="text-[10px] w-full px-2 py-1 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100"
        >
          <option value="">Pick an existing topic…</option>
          {props.knownTopics.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <div className="flex gap-1">
          <button disabled={!mergeTarget}
            onClick={() => { props.onMerge(mergeTarget); setShowMerge(false); }}
            className="text-[10px] px-2 py-0.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white rounded">
            Merge
          </button>
          <button onClick={() => setShowMerge(false)}
            className="text-[10px] px-2 py-0.5 border border-gray-300 dark:border-gray-700 rounded text-gray-700 dark:text-gray-200">
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="pt-1 border-t border-gray-100 dark:border-gray-800 flex flex-wrap gap-1">
      <button
        onClick={props.onPromote}
        className="text-[10px] px-2 py-0.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded inline-flex items-center"
      >
        <Play className="w-3 h-3 mr-0.5" /> Promote
      </button>
      <button
        onClick={() => props.onSnooze(7)}
        className="text-[10px] px-2 py-0.5 border border-gray-300 dark:border-gray-700 rounded text-gray-700 dark:text-gray-200 inline-flex items-center"
        title="Re-surface in 7 days"
      >
        <Clock className="w-3 h-3 mr-0.5" /> 7d
      </button>
      <button
        onClick={() => props.onSnooze(14)}
        className="text-[10px] px-2 py-0.5 border border-gray-300 dark:border-gray-700 rounded text-gray-700 dark:text-gray-200 inline-flex items-center"
        title="Re-surface in 14 days"
      >
        <Clock className="w-3 h-3 mr-0.5" /> 14d
      </button>
      <button
        onClick={() => setShowMerge(true)}
        disabled={props.knownTopics.length === 0}
        className="text-[10px] px-2 py-0.5 border border-gray-300 dark:border-gray-700 rounded text-gray-700 dark:text-gray-200 inline-flex items-center disabled:opacity-40"
      >
        <GitMerge className="w-3 h-3 mr-0.5" /> Merge
      </button>
      <button
        onClick={() => setShowReject(true)}
        className="text-[10px] px-2 py-0.5 border border-gray-300 dark:border-gray-700 rounded text-gray-700 dark:text-gray-200 inline-flex items-center"
      >
        <X className="w-3 h-3 mr-0.5" /> Reject
      </button>
    </div>
  );
}
