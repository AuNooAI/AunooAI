/**
 * Wiley Deliverables panel — recurring forecast-tracker delivery to Wiley.
 *
 * Two cadences:
 *   - Monthly per-topic updates
 *   - Quarterly bundle of the 5 core topics
 *
 * Per-topic cadence + recipient stored in forecast_topic_delivery. Bundle
 * generation reuses the per-topic PPTX slide builders.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, Download, Send, RefreshCw, Calendar, ChevronDown, ChevronRight, X, Edit3 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type {
  TopicDeliveryConfig,
  DeliverablePreview,
} from '@/types/forecastAssessment';
import { QuarterlyBriefEditor } from './QuarterlyBriefEditor';

const CADENCES = ['monthly', 'quarterly', 'none'] as const;
type Cadence = (typeof CADENCES)[number];

interface ReviewFinding {
  stage: string;
  artefact_key: string;
  severity: 'info' | 'warning' | 'error';
  finding: string;
  suggested_fix?: string;
}

interface ReviewState {
  cadence?: string;
  period_label?: string;
  status?: 'awaiting_synth' | 'under_review' | 'revision_requested' | 'approved_with_warnings' | 'approved' | 'shipped';
  reviewer_findings?: ReviewFinding[];
  reviewer_model?: string;
  approved_by?: string | null;
  approved_at?: string | null;
  shipped_at?: string | null;
}

export function WileyDeliverablesPanel() {
  const [open, setOpen] = useState<boolean>(false);
  const [configs, setConfigs] = useState<TopicDeliveryConfig[]>([]);
  const [knownTopics, setKnownTopics] = useState<string[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [savingTopic, setSavingTopic] = useState<string | null>(null);
  const [sending, setSending] = useState<Cadence | null>(null);
  const [monthlyPreview, setMonthlyPreview] = useState<DeliverablePreview | null>(null);
  const [quarterlyPreview, setQuarterlyPreview] = useState<DeliverablePreview | null>(null);
  const [updatesOnly, setUpdatesOnly] = useState<boolean>(true);
  const [toast, setToast] = useState<string | null>(null);
  // Quarterly Brief Editor — open as a full-screen overlay so the analyst
  // can review/edit/lock/approve before sending to Wiley.
  const [editorTarget, setEditorTarget] = useState<{ cadence: string; periodLabel: string } | null>(null);

  // Mirror backend `_period_label` so the "Edit & curate" button can target
  // the current period before a bundle has been generated (no review row
  // yet). Quarterly: YYYY-Qn, Monthly: YYYY-MM, All: YYYY-Hn.
  const computePeriodLabel = (cadence: string) => {
    const now = new Date();
    const y = now.getFullYear();
    const m = now.getMonth() + 1;
    if (cadence === 'quarterly') return `${y}-Q${Math.floor((m - 1) / 3) + 1}`;
    if (cadence === 'monthly') return `${y}-${String(m).padStart(2, '0')}`;
    return `${y}-H${m <= 6 ? 1 : 2}`;
  };

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [cfgR, monR, quaR] = await Promise.all([
        fetch('/api/forecast/topics/delivery'),
        fetch('/api/forecast/deliverables/preview?cadence=monthly'),
        fetch('/api/forecast/deliverables/preview?cadence=quarterly'),
      ]);
      if (cfgR.ok) {
        const data = await cfgR.json();
        setConfigs(data.configs || []);
      }
      if (monR.ok) setMonthlyPreview(await monR.json());
      if (quaR.ok) setQuarterlyPreview(await quaR.json());

      // The deliverables preview only returns configured topics. Pair it
      // with a snapshot of every topic that has a stored assessment so the
      // user can add new ones to a cadence.
      const snap = await fetch('/api/forecast/snapshots/by-topic?topic=');
      // The snapshots endpoint requires a topic, so we infer the topic
      // universe from the configs + the trend-convergence sidebar instead.
      // For now, knownTopics is just the configured set; new topics need
      // to be added via the configs table at the DB level. The UI lets you
      // edit cadence + recipient on already-configured rows.
      setKnownTopics([]);
    } catch (e: any) {
      setError(e?.message || 'Failed to load deliverables config');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (open) refresh(); }, [open, refresh]);

  const saveConfig = useCallback(async (topic: string, cadence: Cadence, recipientEmail: string | null) => {
    setSavingTopic(topic);
    try {
      const r = await fetch(`/api/forecast/topics/${encodeURIComponent(topic)}/delivery`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cadence, recipient_email: recipientEmail }),
      });
      if (!r.ok) {
        const body = await r.text();
        throw new Error(`${r.status} ${body || r.statusText}`);
      }
      await refresh();
    } catch (e: any) {
      setError(e?.message || 'Failed to save config');
    } finally {
      setSavingTopic(null);
    }
  }, [refresh]);

  // ── Bundle download with progress modal ──────────────────────────
  const [progressTask, setProgressTask] = useState<null | {
    cadence: 'monthly' | 'quarterly' | 'all';
    taskId: string;
    bundleUrl: string;
    pct: number;
    message: string;
    log: { pct: number; message: string; at: string }[];
    state: 'running' | 'completed' | 'failed';
    verdict?: string;
    errorCount?: number;
  }>(null);
  const pollHandle = useRef<number | null>(null);

  const cancelProgress = useCallback(() => {
    if (pollHandle.current) {
      window.clearInterval(pollHandle.current);
      pollHandle.current = null;
    }
    setProgressTask(null);
  }, []);

  const downloadBundle = useCallback(async (cadence: 'monthly' | 'quarterly' | 'all') => {
    setError(null);
    try {
      const r = await fetch(
        `/api/forecast/deliverables/bundle/start?cadence=${cadence}&updates_only=${updatesOnly}`,
        { method: 'POST' }
      );
      if (!r.ok) {
        const body = await r.text();
        throw new Error(`${r.status} ${body || r.statusText}`);
      }
      const data = await r.json();
      const taskId = data.task_id;
      const bundleUrl = data.bundle_url;

      setProgressTask({
        cadence, taskId, bundleUrl,
        pct: 0, message: 'Starting…',
        log: [{ pct: 0, message: 'Starting…', at: new Date().toLocaleTimeString() }],
        state: 'running',
      });

      pollHandle.current = window.setInterval(async () => {
        try {
          const sr = await fetch(`/api/forecast/assessment/job/${taskId}`);
          if (!sr.ok) return;
          const s = await sr.json();
          const pct = Math.round(s.progress || 0);
          const msg = s.current_item || s.status;
          setProgressTask(p => {
            if (!p) return p;
            const lastLog = p.log[p.log.length - 1];
            const newLog = (msg && (!lastLog || lastLog.message !== msg))
              ? [...p.log, { pct, message: msg, at: new Date().toLocaleTimeString() }]
              : p.log;
            return { ...p, pct, message: msg, log: newLog };
          });
          if (s.status === 'completed') {
            window.clearInterval(pollHandle.current!);
            pollHandle.current = null;
            const result = s.result || {};
            setProgressTask(p => p ? {
              ...p, state: 'completed', pct: 100, message: 'Complete — downloading…',
              verdict: result.verdict, errorCount: result.error_count,
            } : p);
            // Trigger the actual file download via a dynamic anchor
            try {
              const blobR = await fetch(bundleUrl);
              const blob = await blobR.blob();
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = `wiley_forecast_${cadence}${updatesOnly ? '_updates' : ''}.pptx`;
              document.body.appendChild(a);
              a.click();
              setTimeout(() => {
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
              }, 100);
            } catch (e: any) {
              setError(`Download failed: ${e?.message || e}`);
            }
            // Auto-close after a beat so the user sees the success state
            setTimeout(() => setProgressTask(null), 3000);
            await fetchReview(cadence);
          } else if (s.status === 'failed') {
            window.clearInterval(pollHandle.current!);
            pollHandle.current = null;
            setProgressTask(p => p ? {
              ...p, state: 'failed', message: s.error || 'Generation failed',
            } : p);
          }
        } catch (e) {
          console.warn('poll failed', e);
        }
      }, 1500);
    } catch (e: any) {
      setError(e?.message || 'Failed to start bundle generation');
    }
  }, [updatesOnly]);

  // Cleanup poll on unmount
  useEffect(() => {
    return () => {
      if (pollHandle.current) {
        window.clearInterval(pollHandle.current);
      }
    };
  }, []);

  const sendBundle = useCallback(async (cadence: Cadence) => {
    if (cadence === 'none') return;
    setSending(cadence);
    setError(null);
    setToast(null);
    try {
      const r = await fetch(
        `/api/forecast/deliverables/send?cadence=${cadence}&updates_only=${updatesOnly}`,
        { method: 'POST' }
      );
      // 202 Accepted = reviewer flagged errors, bundle is pending review
      if (r.status === 202) {
        const result = await r.json();
        setError(
          `Reviewer flagged ${(result.findings || []).filter((f: any) => f.severity === 'error').length} errors before this bundle can ship. Resolve them below.`
        );
        await refresh();
        return;
      }
      if (!r.ok) {
        const body = await r.text();
        throw new Error(`${r.status} ${body || r.statusText}`);
      }
      const result = await r.json();
      setToast(
        result.ok
          ? `Sent ${cadence} bundle "${result.period_label}" to ${(result.recipients || []).join(', ')}`
          : `Email send failed — check the email provider config`
      );
      await refresh();
    } catch (e: any) {
      setError(e?.message || 'Failed to send bundle');
    } finally {
      setSending(null);
    }
  }, [updatesOnly, refresh]);

  // ── Reviewer gate state ────────────────────────────────────────────
  const [reviews, setReviews] = useState<Record<string, ReviewState>>({});
  const fetchReview = useCallback(async (cadence: 'monthly' | 'quarterly' | 'all') => {
    try {
      const r = await fetch(`/api/forecast/deliverables/review-status?cadence=${cadence}`);
      if (!r.ok) return;
      const data = await r.json();
      setReviews((m) => ({ ...m, [cadence]: data.review || {} }));
    } catch {}
  }, []);
  useEffect(() => {
    if (open) {
      fetchReview('quarterly');
      fetchReview('monthly');
    }
  }, [open, fetchReview]);

  const approveReview = useCallback(async (cadence: 'monthly' | 'quarterly' | 'all') => {
    const r = reviews[cadence];
    if (!r?.period_label) return;
    const resp = await fetch('/api/forecast/deliverables/review/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cadence, period_label: r.period_label, approved_by: 'ui' }),
    });
    if (resp.ok) {
      await fetchReview(cadence);
      setToast(`Approved ${cadence} bundle for delivery. Now click "Send to recipients".`);
    }
  }, [reviews, fetchReview]);

  const requestRevision = useCallback(async (cadence: 'monthly' | 'quarterly' | 'all', targets: string[]) => {
    const r = reviews[cadence];
    if (!r?.period_label) return;
    const resp = await fetch('/api/forecast/deliverables/review/request-revision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cadence, period_label: r.period_label, target_stages: targets }),
    });
    if (resp.ok) {
      await fetchReview(cadence);
      setToast(`Revision requested for ${cadence}. Re-generate the bundle to re-run flagged stages.`);
    }
  }, [reviews, fetchReview]);

  return (
    <div className="p-4 bg-white dark:bg-gray-800/40 border border-pink-200 dark:border-pink-900/60 rounded-lg">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between text-left"
      >
        <div className="flex items-center gap-2">
          {open ? <ChevronDown className="w-4 h-4 text-pink-700 dark:text-pink-300" /> : <ChevronRight className="w-4 h-4 text-pink-700 dark:text-pink-300" />}
          <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
            Wiley deliverables
          </h3>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            Monthly per-topic · Quarterly bundle · scheduled email
          </span>
        </div>
        <Calendar className="w-4 h-4 text-pink-700 dark:text-pink-300" />
      </button>

      {open && (
        <div className="mt-4 space-y-4">
          {error && (
            <div className="p-3 bg-red-50 dark:bg-red-900/30 border border-red-300 rounded text-red-800 dark:text-red-200 text-sm">
              {error}
            </div>
          )}
          {toast && (
            <div className="p-3 bg-emerald-50 dark:bg-emerald-900/30 border border-emerald-300 rounded text-emerald-800 dark:text-emerald-200 text-sm">
              {toast}
            </div>
          )}

          {/* Per-topic config table */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-sm font-semibold text-gray-800 dark:text-gray-100">Per-topic cadence</h4>
              <button
                type="button"
                onClick={refresh}
                disabled={loading}
                className="text-xs text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 inline-flex items-center"
              >
                {loading ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <RefreshCw className="w-3 h-3 mr-1" />}
                Refresh
              </button>
            </div>

            {configs.length === 0 ? (
              <div className="text-xs text-gray-500 dark:text-gray-400 italic py-2">
                No topics configured yet. To add a topic to a cadence, open the topic's Forecast Tracker tab — there's a "Wiley cadence" control inline with the assessment header.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                      <th className="py-1 pr-3">Topic</th>
                      <th className="py-1 pr-3">Cadence</th>
                      <th className="py-1 pr-3">Recipient(s)</th>
                      <th className="py-1 pr-3">Last delivered</th>
                      <th className="py-1"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {configs.map((c) => (
                      <ConfigRow
                        key={c.topic}
                        config={c}
                        saving={savingTopic === c.topic}
                        onSave={saveConfig}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Reviewer gate — surfaces when the LLM-as-judge has flagged issues */}
          {(reviews.quarterly?.status === 'revision_requested' || reviews.monthly?.status === 'revision_requested') && (
            <ReviewGate
              reviews={reviews}
              onApprove={approveReview}
              onRequestRevision={requestRevision}
            />
          )}

          {/* Bundle generate + send */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <BundleCard
              cadence="monthly"
              preview={monthlyPreview}
              sending={sending === 'monthly'}
              generating={progressTask?.cadence === 'monthly' && progressTask?.state === 'running'}
              updatesOnly={updatesOnly}
              review={reviews.monthly}
              onSend={() => sendBundle('monthly')}
              onDownload={() => downloadBundle('monthly')}
              onEdit={() => setEditorTarget({
                cadence: 'monthly',
                periodLabel: reviews.monthly?.period_label || computePeriodLabel('monthly'),
              })}
            />
            <BundleCard
              cadence="quarterly"
              preview={quarterlyPreview}
              sending={sending === 'quarterly'}
              generating={progressTask?.cadence === 'quarterly' && progressTask?.state === 'running'}
              updatesOnly={updatesOnly}
              review={reviews.quarterly}
              onSend={() => sendBundle('quarterly')}
              onDownload={() => downloadBundle('quarterly')}
              onEdit={() => setEditorTarget({
                cadence: 'quarterly',
                periodLabel: reviews.quarterly?.period_label || computePeriodLabel('quarterly'),
              })}
            />
          </div>

          <label className="flex items-center gap-2 text-xs text-gray-700 dark:text-gray-200 cursor-pointer">
            <input
              type="checkbox"
              checked={updatesOnly}
              onChange={(e) => setUpdatesOnly(e.target.checked)}
              className="rounded border-gray-400"
            />
            Bundle in "updates only" mode (diff against each topic's prior snapshot)
          </label>
        </div>
      )}

      {/* Generation progress modal */}
      {progressTask && (
        <ProgressModal
          progress={progressTask}
          onClose={cancelProgress}
        />
      )}

      {/* Quarterly Brief Editor — full-screen overlay */}
      {editorTarget && editorTarget.periodLabel && (
        <QuarterlyBriefEditor
          cadence={editorTarget.cadence}
          periodLabel={editorTarget.periodLabel}
          onClose={() => setEditorTarget(null)}
        />
      )}
    </div>
  );
}


function ProgressModal({
  progress, onClose,
}: {
  progress: {
    cadence: string;
    pct: number;
    message: string;
    log: { pct: number; message: string; at: string }[];
    state: 'running' | 'completed' | 'failed';
    verdict?: string;
    errorCount?: number;
  };
  onClose: () => void;
}) {
  const isDone = progress.state !== 'running';
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white dark:bg-gray-900 rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        <div className="flex items-start justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Generating {progress.cadence} bundle
            </h3>
            <p className="text-xs text-gray-600 dark:text-gray-300 mt-1">
              {progress.state === 'running' && 'Multi-agent pipeline is running. This usually takes 1-5 minutes on first run, instant on cache hits.'}
              {progress.state === 'completed' && (progress.errorCount && progress.errorCount > 0
                ? `Done — reviewer flagged ${progress.errorCount} error${progress.errorCount === 1 ? '' : 's'}. The deck downloads with a "Review Pending" banner.`
                : 'Done — downloading the deck now.')}
              {progress.state === 'failed' && 'Generation failed. See the log below.'}
            </p>
          </div>
          {isDone && (
            <button onClick={onClose} className="text-gray-500 hover:text-gray-700 dark:text-gray-300 dark:hover:text-gray-100">
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        {/* Progress bar */}
        <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-medium text-gray-700 dark:text-gray-200">
              {progress.pct}% · {progress.message || '…'}
            </span>
            {progress.state === 'running' && (
              <Loader2 className="w-3 h-3 animate-spin text-pink-600 dark:text-pink-300" />
            )}
          </div>
          <div className="w-full bg-gray-200 dark:bg-gray-700 rounded h-2 overflow-hidden">
            <div
              className={`h-full transition-all ${
                progress.state === 'failed'
                  ? 'bg-red-500'
                  : progress.state === 'completed'
                    ? 'bg-emerald-500'
                    : 'bg-pink-600'
              }`}
              style={{ width: `${progress.pct}%` }}
            />
          </div>
        </div>

        {/* Stage log — newest at the bottom */}
        <div className="flex-1 overflow-y-auto p-4 space-y-1.5 text-xs">
          {progress.log.map((entry, i) => (
            <div key={i} className="flex gap-2 items-start">
              <span className="text-gray-400 dark:text-gray-500 tabular-nums font-mono w-12 flex-shrink-0">
                {entry.pct}%
              </span>
              <span className="text-gray-400 dark:text-gray-500 tabular-nums font-mono w-16 flex-shrink-0">
                {entry.at}
              </span>
              <span className="text-gray-800 dark:text-gray-100">{entry.message}</span>
            </div>
          ))}
        </div>

        {isDone && (
          <div className="p-3 border-t border-gray-200 dark:border-gray-700 flex justify-end">
            <Button onClick={onClose} className="text-xs bg-pink-600 hover:bg-pink-700 text-white">
              Close
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}


function ConfigRow({
  config, saving, onSave,
}: {
  config: TopicDeliveryConfig;
  saving: boolean;
  onSave: (topic: string, cadence: Cadence, recipientEmail: string | null) => void;
}) {
  const [cadence, setCadence] = useState<Cadence>(config.cadence);
  const [email, setEmail] = useState<string>(config.recipient_email || '');
  const dirty = cadence !== config.cadence || (email || '') !== (config.recipient_email || '');

  return (
    <tr className="border-b border-gray-100 dark:border-gray-800">
      <td className="py-2 pr-3 text-gray-800 dark:text-gray-100">{config.topic}</td>
      <td className="py-2 pr-3">
        <select
          value={cadence}
          onChange={(e) => setCadence(e.target.value as Cadence)}
          className="border rounded px-2 py-1 text-xs bg-white dark:bg-gray-800 dark:text-gray-100"
        >
          <option value="monthly">Monthly</option>
          <option value="quarterly">Quarterly</option>
          <option value="none">None</option>
        </select>
      </td>
      <td className="py-2 pr-3">
        <input
          type="text"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="recipient@wiley.com"
          className="border rounded px-2 py-1 text-xs bg-white dark:bg-gray-800 dark:text-gray-100 w-56"
        />
      </td>
      <td className="py-2 pr-3 text-gray-500 dark:text-gray-400">
        {config.last_delivered_at ? new Date(config.last_delivered_at).toLocaleDateString() : '—'}
      </td>
      <td className="py-2">
        {dirty && (
          <button
            type="button"
            onClick={() => onSave(config.topic, cadence, email.trim() || null)}
            disabled={saving}
            className="text-xs px-2 py-1 bg-pink-600 hover:bg-pink-700 text-white rounded disabled:opacity-60"
          >
            {saving ? <Loader2 className="w-3 h-3 animate-spin inline" /> : 'Save'}
          </button>
        )}
      </td>
    </tr>
  );
}


function BundleCard({
  cadence, preview, sending, generating, updatesOnly, review, onSend, onDownload, onEdit,
}: {
  cadence: 'monthly' | 'quarterly';
  preview: DeliverablePreview | null;
  sending: boolean;
  generating?: boolean;
  updatesOnly: boolean;
  review?: ReviewState;
  onSend: () => void;
  onDownload: () => void;
  onEdit?: () => void;
}) {
  const [mdLoading, setMdLoading] = useState(false);
  const [docxLoading, setDocxLoading] = useState(false);
  const [htmlLoading, setHtmlLoading] = useState(false);
  // Per-topic overlay status — fetched alongside the preview so missing
  // / auto-generated overlays are visible BEFORE the deck is generated
  // (saves reviewer-roundtrip cost).
  const [overlayMap, setOverlayMap] = useState<Record<string, string>>({});
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch('/api/forecast/topics');
        if (!r.ok) return;
        const data = await r.json();
        if (cancelled) return;
        const m: Record<string, string> = {};
        for (const t of (data.topics || [])) {
          if (t?.topic) m[t.topic] = t.overlay_status || 'missing';
        }
        setOverlayMap(m);
      } catch {}
    })();
    return () => { cancelled = true; };
  }, [preview?.topics?.length]);
  const downloadDocx = async () => {
    setDocxLoading(true);
    try {
      const r = await fetch(
        `/api/forecast/deliverables/bundle.docx?cadence=${cadence}&updates_only=${updatesOnly}`,
      );
      if (!r.ok) {
        const body = await r.text();
        throw new Error(`${r.status} ${body || r.statusText}`);
      }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `wiley_forecast_${cadence}${updatesOnly ? '_updates' : ''}.docx`;
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }, 100);
    } catch (e: any) {
      // eslint-disable-next-line no-alert
      alert(`DOCX download failed: ${e?.message || e}`);
    } finally {
      setDocxLoading(false);
    }
  };
  const downloadHtml = async () => {
    setHtmlLoading(true);
    try {
      const r = await fetch(
        `/api/forecast/deliverables/bundle.html?cadence=${cadence}&updates_only=${updatesOnly}`,
      );
      if (!r.ok) {
        const body = await r.text();
        throw new Error(`${r.status} ${body || r.statusText}`);
      }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `wiley_foresight_${cadence}${updatesOnly ? '_updates' : ''}.html`;
      document.body.appendChild(a);
      a.click();
      setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 100);
    } catch (e: any) {
      // eslint-disable-next-line no-alert
      alert(`HTML download failed: ${e?.message || e}`);
    } finally {
      setHtmlLoading(false);
    }
  };
  const downloadMarkdown = async () => {
    setMdLoading(true);
    try {
      const r = await fetch(
        `/api/forecast/deliverables/bundle.md?cadence=${cadence}&updates_only=${updatesOnly}`,
      );
      if (!r.ok) {
        const body = await r.text();
        throw new Error(`${r.status} ${body || r.statusText}`);
      }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `wiley_forecast_${cadence}${updatesOnly ? '_updates' : ''}.md`;
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }, 100);
    } catch (e: any) {
      // eslint-disable-next-line no-alert
      alert(`MD download failed: ${e?.message || e}`);
    } finally {
      setMdLoading(false);
    }
  };
  const cadenceLabel = cadence === 'monthly' ? 'Monthly' : 'Quarterly';
  const ready = preview?.ready_count ?? 0;
  const configured = preview?.configured_count ?? 0;
  const blocked = review?.status === 'revision_requested';
  const errorCount = (review?.reviewer_findings || []).filter(f => f.severity === 'error').length;
  return (
    <div className={`p-3 ${blocked ? 'bg-red-50 dark:bg-red-900/20 border-red-300 dark:border-red-800' : 'bg-pink-50 dark:bg-pink-900/20 border-pink-200 dark:border-pink-800'} border rounded`}>
      <div className="flex items-center justify-between">
        <div className="font-medium text-gray-900 dark:text-gray-100">{cadenceLabel} bundle</div>
        {review?.status && review.status !== 'awaiting_synth' && (
          <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
            blocked ? 'bg-red-200 text-red-900 dark:bg-red-800 dark:text-red-100'
            : review.status === 'approved' ? 'bg-emerald-200 text-emerald-900 dark:bg-emerald-800 dark:text-emerald-100'
            : 'bg-amber-200 text-amber-900 dark:bg-amber-800 dark:text-amber-100'
          }`}>
            {review.status.replace(/_/g, ' ')}
            {blocked && errorCount > 0 && ` · ${errorCount} error${errorCount === 1 ? '' : 's'}`}
          </span>
        )}
      </div>
      <div className="text-xs text-gray-600 dark:text-gray-300 mt-1">
        {configured} {configured === 1 ? 'topic' : 'topics'} configured · {ready} ready
      </div>
      {preview?.topics?.length ? (
        <ul className="text-[11px] text-gray-700 dark:text-gray-200 mt-2 space-y-0.5">
          {preview.topics.slice(0, 6).map((t) => {
            const ov = overlayMap[t.topic] || 'missing';
            // Surface missing / auto-generated overlays inline so the
            // reviewer sees the problem BEFORE the bundle is rendered.
            const ovBadge = ov === 'missing'
              ? <span className="ml-1 text-[9px] font-semibold px-1 py-0 rounded bg-red-200 text-red-900 dark:bg-red-800 dark:text-red-100">no overlay</span>
              : ov === 'auto_generated'
                ? <span className="ml-1 text-[9px] font-semibold px-1 py-0 rounded bg-amber-200 text-amber-900 dark:bg-amber-800 dark:text-amber-100">overlay pending review</span>
                : null;
            return (
              <li key={t.topic} className="line-clamp-1">
                {t.ready ? '✓' : '○'} {t.topic}{t.recipient_email ? ` → ${t.recipient_email}` : ''}
                {ovBadge}
              </li>
            );
          })}
        </ul>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onDownload}
          disabled={ready === 0 || generating}
          className={`inline-flex items-center text-xs px-3 py-1.5 border rounded ${
            ready === 0 || generating
              ? 'border-gray-300 text-gray-400 cursor-not-allowed'
              : 'border-pink-400 text-pink-700 dark:text-pink-200 dark:border-pink-700 hover:bg-pink-100 dark:hover:bg-pink-900/40'
          }`}
        >
          {generating ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Download className="w-3 h-3 mr-1" />}
          {generating ? 'Generating…' : 'Download .pptx'}
        </button>
        <button
          type="button"
          onClick={downloadDocx}
          disabled={ready === 0 || docxLoading}
          title="Word-document executive briefing — emailable, with the rewritten exec-summary letter as the lead"
          className={`inline-flex items-center text-xs px-3 py-1.5 border rounded ${
            ready === 0 || docxLoading
              ? 'border-gray-300 text-gray-400 cursor-not-allowed'
              : 'border-pink-400 text-pink-700 dark:text-pink-200 dark:border-pink-700 hover:bg-pink-100 dark:hover:bg-pink-900/40'
          }`}
        >
          {docxLoading ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Download className="w-3 h-3 mr-1" />}
          {docxLoading ? 'Generating…' : 'Download .docx'}
        </button>
        <button
          type="button"
          onClick={downloadMarkdown}
          disabled={ready === 0 || mdLoading}
          title="Plain-markdown export of the same synthesis — fast review pass before regenerating PPTX"
          className={`inline-flex items-center text-xs px-3 py-1.5 border rounded ${
            ready === 0 || mdLoading
              ? 'border-gray-300 text-gray-400 cursor-not-allowed'
              : 'border-gray-400 text-gray-700 dark:text-gray-200 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800'
          }`}
        >
          {mdLoading ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Download className="w-3 h-3 mr-1" />}
          {mdLoading ? 'Generating…' : 'Download .md'}
        </button>
        <button
          type="button"
          onClick={downloadHtml}
          disabled={ready === 0 || htmlLoading}
          title="Interactive self-contained HTML — calibration matrix + clickable evidence ledgers, works offline"
          className={`inline-flex items-center text-xs px-3 py-1.5 border rounded ${
            ready === 0 || htmlLoading
              ? 'border-gray-300 text-gray-400 cursor-not-allowed'
              : 'border-indigo-400 text-indigo-700 dark:text-indigo-200 dark:border-indigo-700 hover:bg-indigo-50 dark:hover:bg-indigo-900/40'
          }`}
        >
          {htmlLoading ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Download className="w-3 h-3 mr-1" />}
          {htmlLoading ? 'Generating…' : 'Interactive .html'}
        </button>
        {onEdit && (
          <button
            type="button"
            onClick={onEdit}
            disabled={ready === 0}
            title="Open the Quarterly Brief Editor — review, edit, lock, and approve before sending"
            className={`inline-flex items-center text-xs px-3 py-1.5 border rounded ${
              ready === 0
                ? 'border-gray-300 text-gray-400 cursor-not-allowed'
                : 'border-indigo-400 text-indigo-700 dark:text-indigo-200 dark:border-indigo-700 hover:bg-indigo-50 dark:hover:bg-indigo-900/40'
            }`}
          >
            <Edit3 className="w-3 h-3 mr-1" /> Edit & curate
          </button>
        )}
        <Button
          type="button"
          onClick={onSend}
          disabled={sending || ready === 0 || blocked}
          className="text-xs bg-pink-600 hover:bg-pink-700 text-white h-7 py-0 px-3"
          title={blocked ? 'Reviewer flagged errors — resolve in the review gate above before sending' : ''}
        >
          {sending ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Send className="w-3 h-3 mr-1" />}
          Send now
        </Button>
      </div>
    </div>
  );
}


function ReviewGate({
  reviews,
  onApprove,
  onRequestRevision,
}: {
  reviews: Record<string, ReviewState>;
  onApprove: (cadence: 'monthly' | 'quarterly' | 'all') => Promise<void>;
  onRequestRevision: (cadence: 'monthly' | 'quarterly' | 'all', targets: string[]) => Promise<void>;
}) {
  const cadencesNeedingReview = (['monthly', 'quarterly', 'all'] as const).filter(
    c => reviews[c]?.status === 'revision_requested'
  );
  if (!cadencesNeedingReview.length) return null;

  return (
    <div className="p-3 bg-red-50 dark:bg-red-900/20 border-2 border-red-300 dark:border-red-800 rounded">
      <h4 className="text-sm font-semibold text-red-900 dark:text-red-100 mb-2">
        ⚠ Reviewer flagged errors — bundle held for review
      </h4>
      {cadencesNeedingReview.map(cadence => {
        const review = reviews[cadence];
        const findings = review?.reviewer_findings || [];
        const errors = findings.filter(f => f.severity === 'error');
        const warnings = findings.filter(f => f.severity === 'warning');
        // Collect distinct stages flagged so we can target the revision
        const errorStages = Array.from(new Set(errors.map(f => f.stage)));
        return (
          <div key={cadence} className="mt-2 pt-2 border-t border-red-200 dark:border-red-800 first:border-t-0 first:pt-0 first:mt-0">
            <div className="text-xs font-medium text-red-900 dark:text-red-100">
              {cadence.toUpperCase()} · {review?.period_label} · {errors.length} error{errors.length === 1 ? '' : 's'} · {warnings.length} warning{warnings.length === 1 ? '' : 's'}
            </div>
            <ul className="mt-2 space-y-1.5">
              {findings.slice(0, 8).map((f, i) => (
                <li key={i} className="text-xs flex gap-2">
                  <span className={`flex-shrink-0 inline-block w-14 text-[10px] font-bold uppercase tracking-wide ${
                    f.severity === 'error' ? 'text-red-700 dark:text-red-300'
                    : f.severity === 'warning' ? 'text-amber-700 dark:text-amber-300'
                    : 'text-gray-500 dark:text-gray-400'
                  }`}>{f.severity}</span>
                  <span className="flex-1 text-gray-800 dark:text-gray-100">
                    <span className="font-mono text-[10px] text-gray-500 dark:text-gray-400">{f.artefact_key}</span>
                    <br />
                    {f.finding}
                    {f.suggested_fix && (
                      <span className="text-gray-600 dark:text-gray-300 italic"> · Fix: {f.suggested_fix}</span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={() => onApprove(cadence)}
                className="text-xs px-3 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded"
              >
                Approve overrides → ship
              </button>
              <button
                type="button"
                onClick={() => onRequestRevision(cadence, errorStages)}
                className="text-xs px-3 py-1 bg-amber-600 hover:bg-amber-700 text-white rounded"
              >
                Request fix → regenerate ({errorStages.join(', ')})
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
