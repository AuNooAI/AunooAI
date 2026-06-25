/**
 * Topic Reports tab — on-demand generation of full-fat Wiley-style topic
 * report PPTX decks for any combination of tracked topics.
 *
 * Sister tab to the Forecast Tracker's Wiley Deliverables panel:
 *   - Wiley Deliverables ships the cadence-locked quarterly/monthly bundle.
 *   - Topic Reports lets the analyst spin up a one-off deck on whatever
 *     topic set they need, with the 8-slide intro pack (team profiles,
 *     methodology, "What We Monitor") prepended.
 *
 * Visual style matches WileyDeliverablesPanel — pink-border cards, the
 * shared ProgressModal pattern, and the same .pptx/.docx/.md/.html
 * multi-format download row.
 *
 * Reuses the multi-agent supervisor pipeline behind the quarterly bundle,
 * keyed by (sorted topics, period) so the same selection in the same
 * period serves from cache instantly.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Loader2, Download, FileText, RefreshCw, X, AlertTriangle,
  Tag, User, Calendar,
} from 'lucide-react';
import { Button } from '@/components/ui/button';

interface TopicRow {
  topic: string;
  display_name: string | null;
  description: string | null;
  owner: string | null;
  status: 'draft' | 'active' | 'archived';
  tags: string[] | null;
  assessment_id: string | null;
  assessed_at: string | null;
  scenarios_count: number | null;
}

interface RecentReport {
  period_label: string;
  generated_at: string;
  size_bytes: number;
  download_url: string;
}

interface ProgressLog {
  pct: number;
  message: string;
  at: string;
}

interface ProgressTask {
  taskId: string;
  periodLabel: string;
  pct: number;
  message: string;
  log: ProgressLog[];
  state: 'running' | 'completed' | 'failed';
  verdict?: string;
  errorCount?: number;
}

const DEFAULT_PERIOD = (() => {
  const now = new Date();
  const q = Math.floor(now.getMonth() / 3) + 1;
  return `Q${q} ${now.getFullYear()}`;
})();

export function TopicReportsPanel() {
  const [topics, setTopics] = useState<TopicRow[]>([]);
  const [loadingTopics, setLoadingTopics] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [period, setPeriod] = useState<string>(DEFAULT_PERIOD);
  const [search, setSearch] = useState<string>('');

  const [recent, setRecent] = useState<RecentReport[]>([]);
  const [loadingRecent, setLoadingRecent] = useState(false);

  const [progressTask, setProgressTask] = useState<ProgressTask | null>(null);
  const pollHandle = useRef<number | null>(null);
  // Guard against the double-download race: when polling sees
  // ``status==='completed'`` we want EXACTLY ONE auto-download to fire,
  // even if two in-flight poll callbacks both observe the completion
  // before clearInterval takes effect.
  const downloadTriggered = useRef<boolean>(false);

  const refreshTopics = useCallback(async () => {
    setLoadingTopics(true);
    setError(null);
    try {
      const r = await fetch('/api/forecast/topics');
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const data = await r.json();
      const rows = ((data.topics || []) as TopicRow[])
        .filter(t => t.status !== 'archived' && t.assessment_id);
      setTopics(rows);
    } catch (e: any) {
      setError(e?.message || 'Failed to load topics');
    } finally {
      setLoadingTopics(false);
    }
  }, []);

  const refreshRecent = useCallback(async () => {
    setLoadingRecent(true);
    try {
      const r = await fetch('/api/topic-reports/recent?limit=20');
      if (r.ok) {
        const d = await r.json();
        setRecent((d.reports || []) as RecentReport[]);
      }
    } catch {} finally {
      setLoadingRecent(false);
    }
  }, []);

  useEffect(() => { refreshTopics(); refreshRecent(); }, [refreshTopics, refreshRecent]);
  useEffect(() => {
    return () => { if (pollHandle.current) window.clearInterval(pollHandle.current); };
  }, []);

  const toggleSelected = (topic: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(topic)) next.delete(topic); else next.add(topic);
      return next;
    });
  };
  const selectAll = () => setSelected(new Set(filteredTopics.map(t => t.topic)));
  const clearAll = () => setSelected(new Set());

  const filteredTopics = (() => {
    if (!search.trim()) return topics;
    const q = search.toLowerCase();
    return topics.filter(t =>
      (t.display_name || t.topic).toLowerCase().includes(q) ||
      (t.tags || []).some(tag => (tag || '').toLowerCase().includes(q))
    );
  })();

  const triggerDownload = useCallback(async (url: string, filename: string) => {
    const resp = await fetch(url);
    if (!resp.ok) {
      const body = await resp.text();
      throw new Error(`${resp.status} ${body || resp.statusText}`);
    }
    const blob = await resp.blob();
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      document.body.removeChild(a);
      URL.revokeObjectURL(blobUrl);
    }, 100);
  }, []);

  const startGeneration = useCallback(async (options?: { rerunForecast?: boolean; forceModel?: string }) => {
    if (selected.size === 0) { setError('Pick at least one topic.'); return; }
    setError(null);
    downloadTriggered.current = false;
    try {
      const r = await fetch('/api/topic-reports/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topics: Array.from(selected),
          period: period || undefined,
          rerun_forecast: options?.rerunForecast || false,
          force_model: options?.forceModel || undefined,
        }),
      });
      if (!r.ok) {
        const body = await r.text();
        throw new Error(`${r.status} ${body || r.statusText}`);
      }
      const data = await r.json();
      const { task_id, period_label, download_url } = data;
      setProgressTask({
        taskId: task_id,
        periodLabel: period_label,
        pct: 0,
        message: 'Starting…',
        log: [{ pct: 0, message: 'Starting…', at: new Date().toLocaleTimeString() }],
        state: 'running',
      });

      // Clear any prior interval before starting a new one (defensive
      // against rapid double-clicks).
      if (pollHandle.current) {
        window.clearInterval(pollHandle.current);
        pollHandle.current = null;
      }
      const intervalId = window.setInterval(async () => {
        try {
          const sr = await fetch(`/api/forecast/assessment/job/${task_id}`);
          if (!sr.ok) return;
          const s = await sr.json();
          const pct = Math.round(s.progress || 0);
          const msg = s.current_item || s.status || '';
          setProgressTask(p => {
            if (!p) return p;
            const lastLog = p.log[p.log.length - 1];
            const newLog = (msg && (!lastLog || lastLog.message !== msg))
              ? [...p.log, { pct, message: msg, at: new Date().toLocaleTimeString() }]
              : p.log;
            return { ...p, pct, message: msg, log: newLog };
          });
          if (s.status === 'completed') {
            // Guard: only trigger ONE download even if two callbacks race.
            if (downloadTriggered.current) return;
            downloadTriggered.current = true;
            window.clearInterval(intervalId);
            if (pollHandle.current === intervalId) pollHandle.current = null;
            const result = s.result || {};
            setProgressTask(p => p ? {
              ...p, state: 'completed', pct: 100, message: 'Complete — downloading…',
              verdict: result.verdict, errorCount: result.error_count,
            } : p);
            try {
              await triggerDownload(download_url, `topic_report_${period_label}.pptx`);
            } catch (e: any) {
              setError(`Download failed: ${e?.message || e}`);
            }
            await refreshRecent();
            setTimeout(() => setProgressTask(null), 3000);
          } else if (s.status === 'failed') {
            window.clearInterval(intervalId);
            if (pollHandle.current === intervalId) pollHandle.current = null;
            setProgressTask(p => p ? {
              ...p, state: 'failed', message: s.error || 'Generation failed',
            } : p);
          }
        } catch (e) {
          console.warn('poll failed', e);
        }
      }, 1500);
      pollHandle.current = intervalId;
    } catch (e: any) {
      setError(e?.message || 'Failed to start generation');
    }
  }, [selected, period, refreshRecent, triggerDownload]);

  const cancelProgress = () => {
    if (pollHandle.current) {
      window.clearInterval(pollHandle.current);
      pollHandle.current = null;
    }
    setProgressTask(null);
  };

  const regenerate = async (periodLabel: string) => {
    try {
      await fetch(`/api/topic-reports/${encodeURIComponent(periodLabel)}/regenerate`, {
        method: 'POST',
      });
      await refreshRecent();
    } catch {}
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Topic Reports</h2>
          <p className="text-xs text-gray-600 dark:text-gray-300 mt-0.5">
            On-demand long-form Wiley-style report decks. Pick one or more
            topics, set a period label, generate. Same multi-agent pipeline
            as the quarterly bundle — cached per (topics, period).
          </p>
        </div>
        <button
          type="button"
          onClick={() => { refreshTopics(); refreshRecent(); }}
          className="inline-flex items-center text-xs px-2 py-1 border border-gray-300 dark:border-gray-700 rounded text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800"
        >
          <RefreshCw className="w-3 h-3 mr-1" /> Refresh
        </button>
      </div>

      {error && (
        <div className="p-3 bg-red-50 dark:bg-red-900/30 border border-red-300 rounded text-red-800 dark:text-red-200 text-sm flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <span className="flex-1">{error}</span>
          <button onClick={() => setError(null)} className="text-red-600 hover:text-red-800">
            <X className="w-3 h-3" />
          </button>
        </div>
      )}

      {/* Builder card — matches Wiley deliverables pink-border aesthetic */}
      <div className="p-4 bg-white dark:bg-gray-800/40 border border-pink-200 dark:border-pink-900/60 rounded-lg">
        <div className="flex items-center gap-2 mb-3">
          <Calendar className="w-4 h-4 text-pink-700 dark:text-pink-300" />
          <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
            New report
          </h3>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {selected.size} of {topics.length} topics selected
          </span>
        </div>

        <div className="flex flex-wrap gap-3 mb-3">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs text-gray-600 dark:text-gray-300 mb-1">Period label</label>
            <input
              type="text"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              placeholder="Q3 2026"
              className="w-full text-sm px-2 py-1.5 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100"
            />
            <p className="text-[10px] text-gray-500 dark:text-gray-400 mt-1">
              Shown on the cover. Combined with the topic set into the cache key.
            </p>
          </div>
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs text-gray-600 dark:text-gray-300 mb-1">Search topics</label>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter by name or tag…"
              className="w-full text-sm px-2 py-1.5 border border-gray-300 dark:border-gray-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100"
            />
          </div>
        </div>

        <div className="flex items-center justify-between mb-2">
          <div className="text-xs text-gray-600 dark:text-gray-300">Topics to include</div>
          <div className="flex items-center gap-2">
            <button type="button" onClick={selectAll} className="text-xs text-pink-600 hover:text-pink-800">
              Select all {filteredTopics.length > 0 && `(${filteredTopics.length})`}
            </button>
            <button type="button" onClick={clearAll} className="text-xs text-gray-500 hover:text-gray-800">
              Clear
            </button>
          </div>
        </div>

        <div className="border border-gray-200 dark:border-gray-700 rounded max-h-[300px] overflow-y-auto bg-white dark:bg-gray-900">
          {loadingTopics ? (
            <div className="p-4 text-xs text-gray-500 flex items-center">
              <Loader2 className="w-3 h-3 mr-2 animate-spin" /> Loading topics…
            </div>
          ) : filteredTopics.length === 0 ? (
            <div className="p-4 text-xs text-gray-500 italic">
              No topics with stored assessments. Run a Forecast Assessment first under the Topics tab.
            </div>
          ) : (
            <ul className="divide-y divide-gray-100 dark:divide-gray-800">
              {filteredTopics.map(t => {
                const sc = t.scenarios_count ?? 0;
                return (
                  <li
                    key={t.topic}
                    onClick={() => toggleSelected(t.topic)}
                    className="flex items-start gap-3 px-3 py-2 hover:bg-pink-50 dark:hover:bg-pink-900/10 cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={selected.has(t.topic)}
                      onChange={() => toggleSelected(t.topic)}
                      onClick={(e) => e.stopPropagation()}
                      className="mt-0.5 accent-pink-600"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {t.display_name || t.topic}
                      </div>
                      {t.description && (
                        <div className="text-[11px] text-gray-500 dark:text-gray-400 line-clamp-1">
                          {t.description}
                        </div>
                      )}
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-[10px] text-gray-500">
                          {sc} forecast scenario{sc === 1 ? '' : 's'}
                        </span>
                        {t.owner && (
                          <span className="inline-flex items-center text-[10px] text-gray-500">
                            <User className="w-2.5 h-2.5 mr-0.5" /> {t.owner}
                          </span>
                        )}
                        {(t.tags || []).slice(0, 3).map(tag => (
                          <span key={tag} className="inline-flex items-center text-[10px] px-1 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200">
                            <Tag className="w-2 h-2 mr-0.5" /> {tag}
                          </span>
                        ))}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="mt-3 flex flex-wrap items-center justify-end gap-2">
          <Button
            onClick={() => startGeneration({ rerunForecast: true, forceModel: 'gpt-5.4' })}
            disabled={selected.size === 0 || progressTask?.state === 'running'}
            title="Re-run a fresh Three Horizons analysis with gpt-5.4 (flagship) for each topic before rendering — adds ~25-40s per topic"
            className="text-xs bg-pink-600 hover:bg-pink-700 text-white h-7 py-0 px-3"
          >
            {progressTask?.state === 'running'
              ? <Loader2 className="w-3 h-3 mr-1 animate-spin" />
              : <RefreshCw className="w-3 h-3 mr-1" />}
            Re-run analysis + generate
          </Button>
          <Button
            onClick={() => startGeneration()}
            disabled={selected.size === 0 || progressTask?.state === 'running'}
            title="Render the deck from the existing Future Horizons forecasts (no LLM re-run, fast)"
            className="text-xs bg-gray-700 hover:bg-gray-800 text-white h-7 py-0 px-3"
          >
            {progressTask?.state === 'running'
              ? <Loader2 className="w-3 h-3 mr-1 animate-spin" />
              : <FileText className="w-3 h-3 mr-1" />}
            Generate from cache
          </Button>
        </div>
      </div>

      {/* Recent reports — matches WileyDeliverablesPanel card style */}
      <div className="p-4 bg-white dark:bg-gray-800/40 border border-pink-200 dark:border-pink-900/60 rounded-lg">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
            Recent reports
          </h3>
          <button
            type="button"
            onClick={refreshRecent}
            disabled={loadingRecent}
            className="text-xs text-gray-600 dark:text-gray-300 hover:text-gray-900 inline-flex items-center"
          >
            {loadingRecent ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <RefreshCw className="w-3 h-3 mr-1" />}
            Refresh
          </button>
        </div>
        {recent.length === 0 ? (
          <div className="text-xs text-gray-500 italic">
            No reports generated yet.
          </div>
        ) : (
          <ul className="space-y-2">
            {recent.map(r => (
              <RecentReportRow
                key={r.period_label}
                report={r}
                onTriggerDownload={triggerDownload}
                onRegenerate={() => regenerate(r.period_label)}
              />
            ))}
          </ul>
        )}
      </div>

      {progressTask && (
        <ProgressModal
          progress={progressTask}
          onClose={cancelProgress}
        />
      )}
    </div>
  );
}


function RecentReportRow({
  report, onTriggerDownload, onRegenerate,
}: {
  report: RecentReport;
  onTriggerDownload: (url: string, filename: string) => Promise<void>;
  onRegenerate: () => Promise<void>;
}) {
  const [busy, setBusy] = useState<'pptx' | 'docx' | 'md' | 'html' | 'regen' | null>(null);
  const base = `/api/topic-reports/${encodeURIComponent(report.period_label)}`;

  const run = async (kind: 'pptx' | 'docx' | 'md' | 'html', url: string, ext: string) => {
    setBusy(kind);
    try {
      await onTriggerDownload(url, `topic_report_${report.period_label}.${ext}`);
    } catch (e: any) {
      // eslint-disable-next-line no-alert
      alert(`${kind.toUpperCase()} download failed: ${e?.message || e}`);
    } finally { setBusy(null); }
  };

  return (
    <li className="p-3 bg-pink-50/40 dark:bg-pink-900/10 border border-pink-200 dark:border-pink-900/50 rounded">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <FileText className="w-4 h-4 text-pink-700 dark:text-pink-300 shrink-0" />
          <div className="font-medium text-sm text-gray-900 dark:text-gray-100 truncate">
            {report.period_label}
          </div>
        </div>
        <div className="text-[11px] text-gray-500 dark:text-gray-400 shrink-0 ml-2">
          {new Date(report.generated_at).toLocaleString()} · {(report.size_bytes / 1024 / 1024).toFixed(1)} MB
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => run('pptx', `${base}/download.pptx`, 'pptx')}
          disabled={busy === 'pptx'}
          className="inline-flex items-center text-xs px-3 py-1.5 border border-pink-400 text-pink-700 dark:text-pink-200 dark:border-pink-700 hover:bg-pink-100 dark:hover:bg-pink-900/40 rounded disabled:opacity-60"
        >
          {busy === 'pptx' ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Download className="w-3 h-3 mr-1" />}
          .pptx
        </button>
        <button
          type="button"
          onClick={() => run('docx', `${base}/download.docx`, 'docx')}
          disabled={busy === 'docx'}
          title="Word-document executive briefing"
          className="inline-flex items-center text-xs px-3 py-1.5 border border-pink-400 text-pink-700 dark:text-pink-200 dark:border-pink-700 hover:bg-pink-100 dark:hover:bg-pink-900/40 rounded disabled:opacity-60"
        >
          {busy === 'docx' ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Download className="w-3 h-3 mr-1" />}
          .docx
        </button>
        <button
          type="button"
          onClick={() => run('md', `${base}/download.md`, 'md')}
          disabled={busy === 'md'}
          title="Plain-markdown export — fast review pass before regenerating PPTX"
          className="inline-flex items-center text-xs px-3 py-1.5 border border-gray-400 text-gray-700 dark:text-gray-200 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 rounded disabled:opacity-60"
        >
          {busy === 'md' ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Download className="w-3 h-3 mr-1" />}
          .md
        </button>
        <button
          type="button"
          onClick={() => run('html', `${base}/download.html`, 'html')}
          disabled={busy === 'html'}
          title="Interactive self-contained HTML — works offline"
          className="inline-flex items-center text-xs px-3 py-1.5 border border-indigo-400 text-indigo-700 dark:text-indigo-200 dark:border-indigo-700 hover:bg-indigo-50 dark:hover:bg-indigo-900/40 rounded disabled:opacity-60"
        >
          {busy === 'html' ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Download className="w-3 h-3 mr-1" />}
          Interactive .html
        </button>
        <button
          type="button"
          onClick={async () => { setBusy('regen'); try { await onRegenerate(); } finally { setBusy(null); } }}
          disabled={busy === 'regen'}
          title="Drop the cache so the next generation re-runs the full pipeline"
          className="ml-auto inline-flex items-center text-xs px-3 py-1.5 border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded disabled:opacity-60"
        >
          {busy === 'regen' ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <RefreshCw className="w-3 h-3 mr-1" />}
          Regenerate
        </button>
      </div>
    </li>
  );
}


function ProgressModal({
  progress, onClose,
}: {
  progress: ProgressTask;
  onClose: () => void;
}) {
  const isDone = progress.state !== 'running';
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white dark:bg-gray-900 rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        <div className="flex items-start justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Generating topic report
            </h3>
            <p className="text-xs text-gray-600 dark:text-gray-300 mt-1">
              {progress.state === 'running' && 'Multi-agent pipeline is running. First run on a (topics, period) takes 2-5 minutes; subsequent runs are instant from cache.'}
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
