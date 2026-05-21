/**
 * Forecast Assessment tab — back-tests a stored Three Horizons forecast
 * against articles that arrived after the forecast was generated.
 *
 * Two render paths:
 *   - no assessment yet → CTA + "Run assessment" button
 *   - assessment present → per-scenario verdict cards + surprises panel
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, Play, Sparkles, AlertTriangle, CheckCircle2, MinusCircle, TrendingDown, TrendingUp, Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type {
  ForecastAssessment,
  ForecastAssessmentResponse,
  ScenarioVerdict,
  SurpriseCluster,
  VerdictLabel,
} from '@/types/forecastAssessment';

interface ForecastAssessmentTabProps {
  runId: string | null;
  topic: string;
  forecastGeneratedAt?: string | null;
}

const VERDICT_STYLES: Record<VerdictLabel, { label: string; chip: string; icon: JSX.Element }> = {
  Accelerating: {
    label: 'Accelerating',
    chip: 'bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-900/40 dark:text-emerald-200',
    icon: <TrendingUp className="w-4 h-4" />,
  },
  'On-track': {
    label: 'On-track',
    chip: 'bg-blue-100 text-blue-800 border-blue-300 dark:bg-blue-900/40 dark:text-blue-200',
    icon: <CheckCircle2 className="w-4 h-4" />,
  },
  Stalled: {
    label: 'Stalled',
    chip: 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-900/40 dark:text-amber-200',
    icon: <MinusCircle className="w-4 h-4" />,
  },
  'Off-track': {
    label: 'Off-track',
    chip: 'bg-red-100 text-red-800 border-red-300 dark:bg-red-900/40 dark:text-red-200',
    icon: <TrendingDown className="w-4 h-4" />,
  },
  Inconclusive: {
    label: 'Inconclusive',
    chip: 'bg-gray-100 text-gray-700 border-gray-300 dark:bg-gray-800 dark:text-gray-300',
    icon: <AlertTriangle className="w-4 h-4" />,
  },
};

const HORIZON_LABEL: Record<string, string> = { h1: 'H1 · Declining', h2: 'H2 · Transition', h3: 'H3 · Future' };

type BaselineLabel = 'Above baseline' | 'At baseline' | 'Below baseline';
const BASELINE_STYLES: Record<BaselineLabel, { chip: string; icon: JSX.Element }> = {
  'Above baseline': {
    chip: 'bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-900/40 dark:text-emerald-200',
    icon: <TrendingUp className="w-4 h-4" />,
  },
  'At baseline': {
    chip: 'bg-gray-100 text-gray-700 border-gray-300 dark:bg-gray-800 dark:text-gray-300',
    icon: <MinusCircle className="w-4 h-4" />,
  },
  'Below baseline': {
    chip: 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-900/40 dark:text-amber-200',
    icon: <TrendingDown className="w-4 h-4" />,
  },
};

export function ForecastAssessmentTab({ runId, topic, forecastGeneratedAt }: ForecastAssessmentTabProps) {
  const [assessment, setAssessment] = useState<ForecastAssessment | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [running, setRunning] = useState<boolean>(false);
  const [progress, setProgress] = useState<{ pct: number; msg: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [topicFallback, setTopicFallback] = useState<boolean>(false);
  const [mode, setMode] = useState<'live' | 'placebo' | 'paired'>('live');
  const [windowWeeks, setWindowWeeks] = useState<number>(8);
  const pollRef = useRef<number | null>(null);

  const fetchAssessment = useCallback(async () => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`/api/forecast/${runId}/assessment`);
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const data: ForecastAssessmentResponse = await r.json();
      setAssessment(data.assessment);
      setTopicFallback(!!data.topic_fallback);
    } catch (e: any) {
      setError(e?.message || 'Failed to load assessment');
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    fetchAssessment();
  }, [fetchAssessment]);

  // cleanup poller on unmount or run change
  useEffect(() => {
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, []);

  const runAssessment = useCallback(async () => {
    if (!runId) return;
    setRunning(true);
    setError(null);
    setProgress({ pct: 0, msg: 'Starting…' });
    try {
      const isPaired = mode === 'paired';
      const path = isPaired
        ? `/api/forecast/${runId}/assess-paired?window_weeks=${windowWeeks}`
        : `/api/forecast/${runId}/assess?mode=${mode}&window_weeks=${windowWeeks}`;
      const r = await fetch(path, { method: 'POST' });
      if (!r.ok) {
        const body = await r.text();
        throw new Error(`${r.status} ${body || r.statusText}`);
      }
      const { task_id, status_url } = await r.json();
      // Poll
      pollRef.current = window.setInterval(async () => {
        try {
          const sr = await fetch(status_url);
          if (!sr.ok) return;
          const status = await sr.json();
          setProgress({ pct: Math.round(status.progress || 0), msg: status.current_item || status.status });
          if (status.status === 'completed') {
            window.clearInterval(pollRef.current!);
            pollRef.current = null;
            setRunning(false);
            setProgress(null);
            await fetchAssessment();
          } else if (status.status === 'failed') {
            window.clearInterval(pollRef.current!);
            pollRef.current = null;
            setRunning(false);
            setProgress(null);
            setError(status.error || 'Assessment failed');
          }
        } catch (pollErr) {
          console.warn('poll failed', pollErr);
        }
      }, 4000);
    } catch (e: any) {
      setRunning(false);
      setProgress(null);
      setError(e?.message || 'Failed to start assessment');
    }
  }, [runId, mode, fetchAssessment]);

  if (!runId) {
    return (
      <EmptyHint
        title="No stored Future Horizons run for this topic"
        body="Generate a Three Horizons forecast on the Future Horizons tab first. Once you have a stored analysis, return here to assess how the forecast is tracking against fresh evidence."
      />
    );
  }

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center text-gray-500">
        <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading assessment…
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Header
        topic={topic}
        forecastGeneratedAt={forecastGeneratedAt}
        assessment={assessment}
        running={running}
        progress={progress}
        mode={mode}
        onModeChange={setMode}
        windowWeeks={windowWeeks}
        onWindowWeeksChange={setWindowWeeks}
        onRun={runAssessment}
      />

      {error && (
        <div className="p-4 bg-red-50 dark:bg-red-900/30 border border-red-300 rounded text-red-800 dark:text-red-200 text-sm">
          {error}
        </div>
      )}

      {topicFallback && assessment && (
        <div className="p-3 bg-amber-50 dark:bg-amber-900/30 border border-amber-300 dark:border-amber-700 rounded text-amber-800 dark:text-amber-200 text-sm">
          Showing the latest assessment for this topic, tied to a different horizons run
          (assessment_id <code className="font-mono text-xs">{assessment.id}</code> · run_id
          <code className="font-mono text-xs"> {assessment.run_id}</code>). Run a new
          assessment to score the current page's forecast instead.
        </div>
      )}

      {assessment ? (
        <>
          <VerdictDistribution assessment={assessment} />
          <ScenarioGrid
            verdicts={assessment.scenario_verdicts || []}
            baseline={assessment.summary?.baseline_correction}
          />
          <SurprisesPanel surprises={assessment.surprises || []} />
        </>
      ) : !running && (
        <EmptyHint
          title="No assessment has been run yet for this forecast"
          body="Click 'Run assessment' above to score each scenario against articles that have arrived since the forecast was generated. This typically takes 5–15 minutes."
        />
      )}
    </div>
  );
}

function Header({
  topic, forecastGeneratedAt, assessment, running, progress, mode, onModeChange,
  windowWeeks, onWindowWeeksChange, onRun,
}: {
  topic: string;
  forecastGeneratedAt?: string | null;
  assessment: ForecastAssessment | null;
  running: boolean;
  progress: { pct: number; msg: string } | null;
  mode: 'live' | 'placebo' | 'paired';
  onModeChange: (m: 'live' | 'placebo' | 'paired') => void;
  windowWeeks: number;
  onWindowWeeksChange: (n: number) => void;
  onRun: () => void;
}) {
  return (
    <div className="p-5 bg-gradient-to-r from-indigo-50 to-purple-50 dark:from-indigo-900/30 dark:to-purple-900/30 border-l-4 border-indigo-500 rounded-r-lg">
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-indigo-600 dark:text-indigo-300" />
            Forecast Tracker — {topic}
          </h2>
          <p className="text-sm text-gray-700 dark:text-gray-200 mt-1">
            Back-tests the stored Three Horizons forecast against articles that arrived afterwards.
            {forecastGeneratedAt && (
              <> Forecast generated <strong>{new Date(forecastGeneratedAt).toLocaleDateString()}</strong>.</>
            )}
            {assessment && (
              <> Last assessed <strong>{new Date(assessment.assessed_at).toLocaleString()}</strong> over <strong>{assessment.evidence_count}</strong> post-forecast articles.</>
            )}
          </p>
        </div>
        <div className="flex flex-col gap-2 items-end">
          <div className="flex items-center gap-2 text-xs">
            <label className="text-gray-600 dark:text-gray-300">Mode:</label>
            <select
              value={mode}
              onChange={(e) => onModeChange(e.target.value as 'live' | 'placebo' | 'paired')}
              className="border rounded px-2 py-1 text-xs bg-white dark:bg-gray-800"
              disabled={running}
            >
              <option value="paired">Paired (live + placebo, baseline-corrected)</option>
              <option value="live">Live only (post-forecast)</option>
              <option value="placebo">Placebo only (pre-forecast canary)</option>
            </select>
            <label className="text-gray-600 dark:text-gray-300 ml-2">Window (weeks):</label>
            <input
              type="number"
              min={1}
              max={52}
              value={windowWeeks}
              onChange={(e) => onWindowWeeksChange(Math.max(1, parseInt(e.target.value || '8')))}
              disabled={running}
              className="border rounded px-2 py-1 text-xs bg-white dark:bg-gray-800 w-16"
            />
          </div>
          <div className="flex items-center gap-2">
            {assessment && (
              <a
                href={`/api/forecast/${assessment.run_id}/assessment/${assessment.id}/export.pptx`}
                className="inline-flex items-center text-xs px-3 py-2 border border-indigo-300 text-indigo-700 dark:text-indigo-200 dark:border-indigo-700 rounded hover:bg-indigo-50 dark:hover:bg-indigo-900/40"
                download
              >
                <Download className="w-3.5 h-3.5 mr-1" /> Export .pptx
              </a>
            )}
            <Button onClick={onRun} disabled={running} className="bg-indigo-600 hover:bg-indigo-700 text-white">
              {running ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Play className="w-4 h-4 mr-2" />}
              {running ? `${progress?.pct ?? 0}% — ${progress?.msg ?? 'Running'}` : assessment ? 'Re-run assessment' : 'Run assessment'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function VerdictDistribution({ assessment }: { assessment: ForecastAssessment }) {
  const dist = assessment.summary?.verdict_distribution || {};
  const total = Object.values(dist).reduce((s, v) => s + (v as number || 0), 0);
  if (total === 0) return null;
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
      {(['Accelerating', 'On-track', 'Stalled', 'Off-track', 'Inconclusive'] as VerdictLabel[]).map((label) => {
        const n = (dist as any)[label] || 0;
        const style = VERDICT_STYLES[label];
        return (
          <div key={label} className={`p-3 rounded border ${style.chip} flex items-center gap-2`}>
            {style.icon}
            <div>
              <div className="text-xs uppercase tracking-wide">{label}</div>
              <div className="text-xl font-semibold">{n}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ScenarioGrid({ verdicts, baseline }: {
  verdicts: ScenarioVerdict[];
  baseline?: import('@/types/forecastAssessment').BaselineCorrection;
}) {
  if (!verdicts.length) return null;
  return (
    <div className="space-y-4">
      <h3 className="text-base font-semibold text-gray-800 dark:text-gray-100">
        Per-scenario tracking
        {baseline && (
          <span className="ml-2 text-xs font-normal text-gray-500 dark:text-gray-400">
            Baseline-corrected against placebo (pool sizes:
            live={baseline.live_pool}, placebo={baseline.placebo_pool})
          </span>
        )}
      </h3>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {verdicts.map((v) => (
          <ScenarioCard
            key={v.scenario_idx}
            verdict={v}
            baseline={baseline?.per_scenario?.[String(v.scenario_idx)]}
          />
        ))}
      </div>
    </div>
  );
}

function ScenarioCard({ verdict, baseline }: {
  verdict: ScenarioVerdict;
  baseline?: import('@/types/forecastAssessment').BaselineCorrection['per_scenario'][string];
}) {
  const rawStyle = VERDICT_STYLES[verdict.verdict_label] || VERDICT_STYLES.Inconclusive;
  const baselineStyle = baseline ? BASELINE_STYLES[baseline.label as BaselineLabel] : undefined;
  // Promote the baseline-corrected verdict to the headline chip whenever
  // paired mode was used; the raw verdict still shows below as a secondary
  // pill so users can sanity-check the correction.
  const headline = baselineStyle
    ? { label: baseline!.label, ...baselineStyle }
    : { label: rawStyle.label, chip: rawStyle.chip, icon: rawStyle.icon };
  const horizon = HORIZON_LABEL[verdict.horizon_type] || verdict.horizon_type.toUpperCase();
  const deckInfo = verdict.top_articles?.deck_info;
  return (
    <div className="p-4 bg-white dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400 flex items-center gap-2">
            <span>{horizon}</span>
            {deckInfo?.consensus_pct != null && (
              <span className="px-1.5 py-0.5 bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300 rounded text-[10px] font-medium">
                {deckInfo.consensus_pct}% original consensus
              </span>
            )}
          </div>
          <div className="font-semibold text-gray-900 dark:text-gray-100 leading-snug">
            {deckInfo?.deck_scenario_name || verdict.scenario_title}
          </div>
          {deckInfo?.primary_signal && (
            <div className="text-xs text-gray-600 dark:text-gray-300 mt-1 italic line-clamp-2">
              {deckInfo.primary_signal}
            </div>
          )}
        </div>
        <span className={`flex-shrink-0 text-xs font-medium px-2 py-1 rounded border ${headline.chip} flex items-center gap-1`}>
          {headline.icon} {headline.label}
        </span>
      </div>
      {baselineStyle && (
        <div className="text-[11px] text-gray-500 dark:text-gray-400 -mt-1 mb-1">
          raw verdict: <span className="font-medium">{rawStyle.label}</span>
        </div>
      )}

      <div className="grid grid-cols-4 gap-2 mt-3 text-center text-xs">
        <Metric label="Rate" value={verdict.directional_rate.toFixed(2)} />
        <Metric label="Velocity" value={verdict.velocity.toFixed(1)} />
        <Metric label="Milestones" value={`${Math.round(verdict.milestone_density * 100)}%`} />
        <Metric label="Coverage" value={verdict.coverage.toFixed(2)} />
      </div>

      <div className="mt-3 text-xs text-gray-600 dark:text-gray-300">
        <span className="font-medium text-emerald-700 dark:text-emerald-300">{verdict.supports} support</span>
        {' · '}
        <span className="font-medium text-red-700 dark:text-red-300">{verdict.contradicts} contradict</span>
        {' · '}
        <span>{verdict.neutral} neutral</span>
      </div>

      {baseline && (
        <div className="mt-3 p-2 bg-slate-50 dark:bg-slate-900/40 border border-slate-200 dark:border-slate-700 rounded text-xs">
          <div className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1">
            Baseline-corrected
          </div>
          <div className="flex items-baseline justify-between gap-3">
            <div>
              live <span className="font-mono">{(baseline.live_rate * 100).toFixed(2)}%</span>
              {'  −  '}
              placebo <span className="font-mono">{(baseline.placebo_rate * 100).toFixed(2)}%</span>
              {'  ='}
            </div>
            <div className="text-right">
              <span className={`font-mono font-semibold ${
                baseline.net_rate > 0
                  ? 'text-emerald-700 dark:text-emerald-300'
                  : baseline.net_rate < 0
                    ? 'text-red-700 dark:text-red-300'
                    : 'text-gray-600 dark:text-gray-300'
              }`}>
                {baseline.net_rate > 0 ? '+' : ''}{(baseline.net_rate * 100).toFixed(2)}%
              </span>
              <span className="ml-2 text-[11px] text-gray-500 dark:text-gray-400">{baseline.label}</span>
            </div>
          </div>
          <div className="text-[11px] text-gray-500 dark:text-gray-400 mt-1">
            live {baseline.live_supports}/{baseline.live_pool}  ·  placebo {baseline.placebo_supports}/{baseline.placebo_pool}
          </div>
        </div>
      )}

      {verdict.top_articles?.supports?.length ? (
        <div className="mt-3">
          <div className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1">Top supporting</div>
          <ul className="text-xs space-y-1">
            {verdict.top_articles.supports.slice(0, 3).map((a) => (
              <li key={a.article_uri} className="border-l-2 border-emerald-400 pl-2">
                <div className="font-medium text-gray-800 dark:text-gray-100 line-clamp-1">{a.title || a.article_uri}</div>
                {a.rationale && <div className="text-gray-600 dark:text-gray-300 italic">{a.rationale}</div>}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {verdict.top_articles?.contradicts?.length ? (
        <div className="mt-3">
          <div className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1">Strongest contradiction</div>
          <ul className="text-xs space-y-1">
            {verdict.top_articles.contradicts.slice(0, 2).map((a) => (
              <li key={a.article_uri} className="border-l-2 border-red-400 pl-2">
                <div className="font-medium text-gray-800 dark:text-gray-100 line-clamp-1">{a.title || a.article_uri}</div>
                {a.rationale && <div className="text-gray-600 dark:text-gray-300 italic">{a.rationale}</div>}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="p-2 bg-gray-50 dark:bg-gray-900/40 border border-gray-200 dark:border-gray-700 rounded">
      <div className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">{label}</div>
      <div className="font-semibold text-gray-800 dark:text-gray-100">{value}</div>
    </div>
  );
}

function SurprisesPanel({ surprises }: { surprises: SurpriseCluster[] }) {
  if (!surprises?.length) return null;
  return (
    <div className="space-y-3">
      <h3 className="text-base font-semibold text-gray-800 dark:text-gray-100">
        Unanticipated developments
        <span className="ml-2 text-xs font-normal text-gray-500 dark:text-gray-400">
          Article clusters none of the {surprises.length === 1 ? 'scenarios' : 'forecast scenarios'} explain
        </span>
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {surprises.map((c, i) => (
          <div key={i} className="p-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-300 dark:border-yellow-700 rounded">
            <div className="flex items-center justify-between">
              <div className="font-medium text-gray-900 dark:text-gray-100">{c.label}</div>
              <div className="text-xs text-gray-600 dark:text-gray-300">{c.size} articles</div>
            </div>
            <ul className="mt-2 text-xs space-y-1">
              {c.sample_articles?.slice(0, 5).map((a) => (
                <li key={a.uri} className="text-gray-700 dark:text-gray-200 line-clamp-1">• {a.title || a.uri}</li>
              ))}
            </ul>
            {c.note && <div className="text-[11px] text-gray-500 dark:text-gray-400 mt-2 italic">{c.note}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

function EmptyHint({ title, body }: { title: string; body: string }) {
  return (
    <div className="p-6 bg-gray-50 dark:bg-gray-900/40 border border-gray-200 dark:border-gray-700 rounded text-center">
      <div className="text-gray-700 dark:text-gray-100 font-medium">{title}</div>
      <div className="text-sm text-gray-600 dark:text-gray-300 mt-2 max-w-xl mx-auto">{body}</div>
    </div>
  );
}
