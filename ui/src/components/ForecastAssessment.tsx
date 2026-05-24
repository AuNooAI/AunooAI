/**
 * Forecast Assessment tab — back-tests a stored Three Horizons forecast
 * against articles that arrived after the forecast was generated.
 *
 * Two render paths:
 *   - no assessment yet → CTA + "Run assessment" button
 *   - assessment present → per-scenario verdict cards + surprises panel
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, Play, Sparkles, AlertTriangle, CheckCircle2, MinusCircle, TrendingDown, TrendingUp, Download, Plus, X, Check, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type {
  ForecastAssessment,
  ForecastAssessmentResponse,
  ScenarioVerdict,
  SurpriseCluster,
  VerdictLabel,
  AssessmentSnapshot,
  SnapshotsResponse,
  AddendumScenario,
  ScenarioDraft,
  ScenarioStatusesResponse,
} from '@/types/forecastAssessment';
import { WileyDeliverablesPanel } from './WileyDeliverablesPanel';

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
const BASELINE_STYLES: Record<BaselineLabel, { chip: string; icon: JSX.Element; display: string }> = {
  'Above baseline': {
    chip: 'bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-900/40 dark:text-emerald-200',
    icon: <TrendingUp className="w-4 h-4" />,
    display: 'Strengthening',
  },
  'At baseline': {
    chip: 'bg-gray-100 text-gray-700 border-gray-300 dark:bg-gray-800 dark:text-gray-300',
    icon: <MinusCircle className="w-4 h-4" />,
    display: 'Stable',
  },
  'Below baseline': {
    chip: 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-900/40 dark:text-amber-200',
    icon: <TrendingDown className="w-4 h-4" />,
    display: 'Cooling',
  },
};

// Internal label → customer-facing label (matches CUSTOMER_LABEL in the PPTX builder).
const CUSTOMER_LABEL: Record<string, string> = {
  'Above baseline': 'Strengthening',
  'At baseline':    'Stable',
  'Below baseline': 'Cooling',
};
function customerLabel(label: string | undefined | null): string {
  if (!label) return '—';
  return CUSTOMER_LABEL[label] || label;
}

export function ForecastAssessmentTab({ runId, topic, forecastGeneratedAt }: ForecastAssessmentTabProps) {
  const [assessment, setAssessment] = useState<ForecastAssessment | null>(null);
  const [addendumScenarios, setAddendumScenarios] = useState<AddendumScenario[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [running, setRunning] = useState<boolean>(false);
  const [progress, setProgress] = useState<{ pct: number; msg: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [topicFallback, setTopicFallback] = useState<boolean>(false);
  const [mode, setMode] = useState<'live' | 'placebo' | 'paired'>('live');
  const [windowWeeks, setWindowWeeks] = useState<number>(8);
  // Surprise cluster currently being promoted to a scenario. When set, the
  // PromoteScenarioModal is rendered.
  const [promotingCluster, setPromotingCluster] = useState<{ cluster: SurpriseCluster; index: number } | null>(null);
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

  const [scenarioStatuses, setScenarioStatuses] = useState<ScenarioStatusesResponse>({
    originals: {}, addendums: {},
  });

  const fetchAddendumScenarios = useCallback(async () => {
    if (!runId) return;
    try {
      const r = await fetch(`/api/forecast/${runId}/scenarios`);
      if (!r.ok) return;
      const data = await r.json();
      setAddendumScenarios(data.addendum_scenarios || []);
      setScenarioStatuses(data.scenario_statuses || { originals: {}, addendums: {} });
    } catch (e) {
      console.warn('Failed to load addendum scenarios', e);
    }
  }, [runId]);

  useEffect(() => { fetchAddendumScenarios(); }, [fetchAddendumScenarios]);

  const updateScenarioStatus = useCallback(async (
    payload: { scenario_idx?: number; user_scenario_id?: string; status: 'active' | 'done'; note?: string }
  ) => {
    if (!runId) return;
    const r = await fetch(`/api/forecast/${runId}/scenarios/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    await fetchAddendumScenarios();
  }, [runId, fetchAddendumScenarios]);

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

      {assessment && (
        <SnapshotHistoryPanel topic={topic} />
      )}

      {assessment ? (
        <>
          <VerdictDistribution assessment={assessment} />
          <ScenarioGrid
            verdicts={assessment.scenario_verdicts || []}
            baseline={assessment.summary?.baseline_correction}
            addendumByIdx={mapAddendumScenariosByIdx(assessment.scenario_verdicts || [], addendumScenarios)}
            onMarkDone={async (verdict) => {
              const idx = verdict.scenario_idx;
              const addendum = mapAddendumScenariosByIdx(assessment.scenario_verdicts || [], addendumScenarios)[idx];
              if (addendum) {
                await updateScenarioStatus({ user_scenario_id: addendum.id, status: 'done' });
              } else {
                await updateScenarioStatus({ scenario_idx: idx, status: 'done' });
              }
            }}
          />
          <AddedScenariosPanel scenarios={addendumScenarios.filter(s => scenarioStatuses.addendums[s.id]?.status !== 'done')} />
          <ResolvedScenariosPanel
            verdicts={assessment.scenario_verdicts || []}
            addendums={addendumScenarios}
            statuses={scenarioStatuses}
            onUnmark={async ({ scenario_idx, user_scenario_id }) => {
              await updateScenarioStatus({ scenario_idx, user_scenario_id, status: 'active' });
            }}
          />
          <SurprisesPanel
            surprises={assessment.surprises || []}
            onPromote={(cluster, index) => setPromotingCluster({ cluster, index })}
          />
          <TopicCadenceInline topic={topic} />
          <WileyDeliverablesPanel />
        </>
      ) : !running && (
        <EmptyHint
          title="No assessment has been run yet for this forecast"
          body="Click 'Run assessment' above to score each scenario against articles that have arrived since the forecast was generated. This typically takes 5–15 minutes."
        />
      )}

      {promotingCluster && runId && assessment && (
        <PromoteScenarioModal
          runId={runId}
          assessmentId={assessment.id}
          cluster={promotingCluster.cluster}
          surpriseIndex={promotingCluster.index}
          windowWeeks={windowWeeks}
          onClose={() => setPromotingCluster(null)}
          onScenarioCreated={async () => {
            setPromotingCluster(null);
            await fetchAddendumScenarios();
            // Surface that the new paired assessment is running so the user
            // doesn't think nothing happened.
            setRunning(true);
            setProgress({ pct: 0, msg: 'Reassessing with new scenario…' });
          }}
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
              <option value="paired">Paired (recommended — adjusts for pre-existing trend)</option>
              <option value="live">Post-forecast only</option>
              <option value="placebo">Pre-forecast comparison</option>
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
              <>
                <a
                  href={`/api/forecast/${assessment.run_id}/assessment/${assessment.id}/export.pptx`}
                  className="inline-flex items-center text-xs px-3 py-2 border border-indigo-300 text-indigo-700 dark:text-indigo-200 dark:border-indigo-700 rounded hover:bg-indigo-50 dark:hover:bg-indigo-900/40"
                  download
                  title="Full deck with every scenario and every surprise cluster"
                >
                  <Download className="w-3.5 h-3.5 mr-1" /> Export .pptx
                </a>
                <a
                  href={`/api/forecast/${assessment.run_id}/assessment/${assessment.id}/export.pptx?updates_only=true`}
                  className="inline-flex items-center text-xs px-3 py-2 border border-pink-300 text-pink-700 dark:text-pink-200 dark:border-pink-700 rounded hover:bg-pink-50 dark:hover:bg-pink-900/40"
                  download
                  title="Slimmer deck: only scenarios where the status changed since the prior snapshot, plus newly-emerged themes"
                >
                  <Download className="w-3.5 h-3.5 mr-1" /> Updates only
                </a>
              </>
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

function ScenarioGrid({ verdicts, baseline, addendumByIdx, onMarkDone }: {
  verdicts: ScenarioVerdict[];
  baseline?: import('@/types/forecastAssessment').BaselineCorrection;
  addendumByIdx?: Record<number, AddendumScenario>;
  onMarkDone?: (verdict: ScenarioVerdict) => Promise<void>;
}) {
  // Drop already-done scenarios from the grid — they appear in
  // ResolvedScenariosPanel instead.
  const active = verdicts.filter(v => v.verdict_label !== 'Done');
  if (!active.length) return null;
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
        {active.map((v) => (
          <ScenarioCard
            key={v.scenario_idx}
            verdict={v}
            baseline={baseline?.per_scenario?.[String(v.scenario_idx)]}
            addendum={addendumByIdx?.[v.scenario_idx]}
            onMarkDone={onMarkDone ? () => onMarkDone(v) : undefined}
          />
        ))}
      </div>
    </div>
  );
}

function mapAddendumScenariosByIdx(
  verdicts: ScenarioVerdict[],
  addendums: AddendumScenario[],
): Record<number, AddendumScenario> {
  // Addendum scenarios are appended after the originals, so they occupy the
  // tail of the scenario_verdicts list. We match them by ordering — the
  // i-th addendum corresponds to the (N-K+i)-th verdict where K = addendums.length
  // and N = total verdicts. This mirrors the order assess_run produces.
  const out: Record<number, AddendumScenario> = {};
  if (!addendums.length || !verdicts.length) return out;
  const start = verdicts.length - addendums.length;
  if (start < 0) return out;
  for (let i = 0; i < addendums.length; i++) {
    const v = verdicts[start + i];
    if (v) out[v.scenario_idx] = addendums[i];
  }
  return out;
}

function ScenarioCard({ verdict, baseline, addendum, onMarkDone }: {
  verdict: ScenarioVerdict;
  baseline?: import('@/types/forecastAssessment').BaselineCorrection['per_scenario'][string];
  addendum?: AddendumScenario;
  onMarkDone?: () => Promise<void>;
}) {
  const rawStyle = VERDICT_STYLES[verdict.verdict_label] || VERDICT_STYLES.Inconclusive;
  const baselineStyle = baseline ? BASELINE_STYLES[baseline.label as BaselineLabel] : undefined;
  // Headline chip shows the customer-friendly status (Strengthening / Stable /
  // Cooling) when a paired-mode baseline correction is available; otherwise
  // falls back to the raw verdict label.
  const headline = baselineStyle
    ? { label: baselineStyle.display, chip: baselineStyle.chip, icon: baselineStyle.icon }
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
        <div className="flex-shrink-0 flex items-center gap-2">
          <span className={`text-xs font-medium px-2 py-1 rounded border ${headline.chip} flex items-center gap-1`}>
            {headline.icon} {headline.label}
          </span>
          {onMarkDone && (
            <button
              type="button"
              onClick={async () => {
                if (window.confirm(`Mark "${deckInfo?.deck_scenario_name || verdict.scenario_title}" as done? It will be skipped from future assessments and moved to the Resolved section.`)) {
                  await onMarkDone();
                }
              }}
              className="text-[11px] px-2 py-1 border border-gray-300 dark:border-gray-600 rounded text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
              title="Mark this scenario as done — stops tracking + moves to Resolved"
            >
              <Check className="w-3 h-3 inline mr-0.5" /> Done
            </button>
          )}
        </div>
      </div>
      {addendum && (
        <div className="text-[10px] uppercase tracking-wide text-pink-600 dark:text-pink-300 -mt-0.5 mb-1">
          Added from an emerging theme
        </div>
      )}

      <div className="mt-3 text-xs text-gray-600 dark:text-gray-300">
        <span className="font-medium text-emerald-700 dark:text-emerald-300">{verdict.supports} confirming</span>
        {' · '}
        <span className="font-medium text-red-700 dark:text-red-300">{verdict.contradicts} contradicting</span>
        {' · '}
        <span>{verdict.neutral} neutral</span>
      </div>

      {baseline && (
        <div className="mt-3 p-2 bg-slate-50 dark:bg-slate-900/40 border border-slate-200 dark:border-slate-700 rounded text-xs">
          <div className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1">
            Confirmation strength vs. pre-forecast
          </div>
          <div className="flex items-baseline justify-between gap-3">
            <div className="text-gray-600 dark:text-gray-300">
              {customerLabel(baseline.label)}
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
              <span className="ml-2 text-[11px] text-gray-500 dark:text-gray-400">Δ</span>
            </div>
          </div>
        </div>
      )}

      {verdict.top_articles?.supports?.length ? (
        <div className="mt-3">
          <div className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1">Top confirming evidence</div>
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
          <div className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1">Strongest contradicting evidence</div>
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

function SurprisesPanel({
  surprises,
  onPromote,
}: {
  surprises: SurpriseCluster[];
  onPromote?: (cluster: SurpriseCluster, index: number) => void;
}) {
  if (!surprises?.length) return null;
  return (
    <div className="space-y-3">
      <h3 className="text-base font-semibold text-gray-800 dark:text-gray-100">
        Emerging themes
        <span className="ml-2 text-xs font-normal text-gray-500 dark:text-gray-400">
          Story lines in recent coverage that none of the original scenarios anticipated
        </span>
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {surprises.map((c, i) => (
          <div key={i} className="p-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-300 dark:border-yellow-700 rounded">
            <div className="flex items-start justify-between gap-2">
              <div className="font-medium text-gray-900 dark:text-gray-100">{c.label}</div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <div className="text-xs text-gray-600 dark:text-gray-300">{c.size} articles</div>
                {onPromote && (
                  <button
                    type="button"
                    onClick={() => onPromote(c, i)}
                    className="inline-flex items-center text-[11px] px-2 py-1 border border-pink-400 text-pink-700 dark:text-pink-200 dark:border-pink-600 rounded hover:bg-pink-50 dark:hover:bg-pink-900/30"
                    title="Promote this cluster into a tracked scenario alongside the original Three Horizons forecast"
                  >
                    <Plus className="w-3 h-3 mr-1" /> Track as scenario
                  </button>
                )}
              </div>
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

function AddedScenariosPanel({ scenarios }: { scenarios: AddendumScenario[] }) {
  if (!scenarios?.length) return null;
  return (
    <div className="space-y-3">
      <h3 className="text-base font-semibold text-gray-800 dark:text-gray-100">
        Added scenarios
        <span className="ml-2 text-xs font-normal text-gray-500 dark:text-gray-400">
          Promoted from emerging themes — tracked alongside the original forecast
        </span>
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {scenarios.map((s) => (
          <div key={s.id} className="p-3 bg-pink-50 dark:bg-pink-900/20 border border-pink-300 dark:border-pink-800 rounded">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="text-[10px] uppercase tracking-wide text-pink-700 dark:text-pink-300">
                  {HORIZON_LABEL[s.horizon_type] || s.horizon_type.toUpperCase()}
                  {s.timeframe && <span className="ml-2 text-gray-500 dark:text-gray-400">{s.timeframe}</span>}
                </div>
                <div className="font-medium text-gray-900 dark:text-gray-100 leading-snug">{s.title}</div>
              </div>
              <div className="text-[10px] text-gray-500 dark:text-gray-400 flex-shrink-0">
                {new Date(s.created_at).toLocaleDateString()}
              </div>
            </div>
            <div className="text-xs text-gray-700 dark:text-gray-200 mt-2 line-clamp-3">{s.description}</div>
            {s.source_surprise_label && (
              <div className="text-[11px] text-pink-700 dark:text-pink-300 mt-2 italic">
                From cluster: {s.source_surprise_label}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function ResolvedScenariosPanel({
  verdicts, addendums, statuses, onUnmark,
}: {
  verdicts: ScenarioVerdict[];
  addendums: AddendumScenario[];
  statuses: ScenarioStatusesResponse;
  onUnmark: (key: { scenario_idx?: number; user_scenario_id?: string }) => Promise<void>;
}) {
  const addendumByIdx = mapAddendumScenariosByIdx(verdicts, addendums);
  const done = verdicts.filter(v => v.verdict_label === 'Done');
  if (!done.length) return null;
  return (
    <div className="space-y-3">
      <h3 className="text-base font-semibold text-gray-800 dark:text-gray-100">
        Resolved scenarios
        <span className="ml-2 text-xs font-normal text-gray-500 dark:text-gray-400">
          Marked done — skipped from future assessments. Historical verdict rows preserved.
        </span>
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {done.map((v) => {
          const addendum = addendumByIdx[v.scenario_idx];
          const statusRow = addendum
            ? statuses.addendums[addendum.id]
            : statuses.originals[String(v.scenario_idx)];
          return (
            <div key={v.scenario_idx} className="p-3 bg-gray-50 dark:bg-gray-800/40 border border-gray-200 dark:border-gray-700 rounded">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
                    {HORIZON_LABEL[v.horizon_type] || v.horizon_type.toUpperCase()}
                    {addendum && <span className="ml-2 text-pink-600 dark:text-pink-300">addendum</span>}
                  </div>
                  <div className="font-medium text-gray-800 dark:text-gray-100 leading-snug line-through opacity-80">
                    {v.scenario_title}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={async () => {
                    await onUnmark(addendum
                      ? { user_scenario_id: addendum.id }
                      : { scenario_idx: v.scenario_idx });
                  }}
                  className="text-[11px] px-2 py-1 border border-gray-300 dark:border-gray-600 rounded text-gray-600 dark:text-gray-300 hover:bg-white dark:hover:bg-gray-700"
                  title="Restore to active tracking"
                >
                  <RotateCcw className="w-3 h-3 inline mr-0.5" /> Un-mark
                </button>
              </div>
              {(statusRow?.marked_done_at || statusRow?.note) && (
                <div className="text-[11px] text-gray-500 dark:text-gray-400 mt-2">
                  {statusRow?.marked_done_at && (
                    <>Marked done {new Date(statusRow.marked_done_at).toLocaleDateString()}</>
                  )}
                  {statusRow?.note && <> · {statusRow.note}</>}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TopicCadenceInline({ topic }: { topic: string }) {
  // Lightweight inline editor so the user can set this topic's cadence and
  // recipient without navigating to the global Wiley Deliverables panel.
  const [cadence, setCadence] = useState<'monthly' | 'quarterly' | 'none'>('none');
  const [email, setEmail] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [dirty, setDirty] = useState<boolean>(false);
  const [savedHint, setSavedHint] = useState<boolean>(false);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/forecast/topics/delivery')
      .then(r => r.ok ? r.json() : Promise.reject())
      .then((data) => {
        if (cancelled) return;
        const cfg = (data.configs || []).find((c: any) => c.topic === topic);
        if (cfg) {
          setCadence(cfg.cadence);
          setEmail(cfg.recipient_email || '');
        }
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [topic]);

  const save = async () => {
    setSaving(true);
    try {
      const r = await fetch(`/api/forecast/topics/${encodeURIComponent(topic)}/delivery`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cadence, recipient_email: email.trim() || null }),
      });
      if (!r.ok) throw new Error(await r.text());
      setDirty(false);
      setSavedHint(true);
      setTimeout(() => setSavedHint(false), 2500);
    } catch (e) {
      console.warn('Failed to save topic cadence', e);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return null;

  return (
    <div className="p-3 bg-white dark:bg-gray-800/40 border border-gray-200 dark:border-gray-700 rounded text-sm flex flex-col md:flex-row md:items-center gap-2">
      <div className="font-medium text-gray-800 dark:text-gray-100 text-xs uppercase tracking-wide">Wiley cadence for this topic:</div>
      <select
        value={cadence}
        onChange={(e) => { setCadence(e.target.value as any); setDirty(true); }}
        className="border rounded px-2 py-1 text-xs bg-white dark:bg-gray-800 dark:text-gray-100"
      >
        <option value="none">None</option>
        <option value="monthly">Monthly</option>
        <option value="quarterly">Quarterly</option>
      </select>
      <input
        type="text"
        value={email}
        onChange={(e) => { setEmail(e.target.value); setDirty(true); }}
        placeholder="recipient@wiley.com"
        className="border rounded px-2 py-1 text-xs bg-white dark:bg-gray-800 dark:text-gray-100 flex-1 max-w-md"
      />
      {dirty && (
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="text-xs px-3 py-1 bg-pink-600 hover:bg-pink-700 text-white rounded disabled:opacity-60"
        >
          {saving ? <Loader2 className="w-3 h-3 animate-spin inline" /> : 'Save'}
        </button>
      )}
      {savedHint && <span className="text-xs text-emerald-700 dark:text-emerald-300">Saved</span>}
    </div>
  );
}

function PromoteScenarioModal({
  runId,
  assessmentId,
  cluster,
  surpriseIndex,
  windowWeeks,
  onClose,
  onScenarioCreated,
}: {
  runId: string;
  assessmentId: string;
  cluster: SurpriseCluster;
  surpriseIndex: number;
  windowWeeks: number;
  onClose: () => void;
  onScenarioCreated: () => void;
}) {
  const [drafting, setDrafting] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<ScenarioDraft | null>(null);

  useEffect(() => {
    let cancelled = false;
    setDrafting(true);
    setError(null);
    fetch(`/api/forecast/${runId}/scenarios/draft-from-surprise`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ assessment_id: assessmentId, surprise_index: surpriseIndex }),
    })
      .then(async (r) => {
        if (!r.ok) {
          const body = await r.text();
          throw new Error(`${r.status} ${body || r.statusText}`);
        }
        return r.json();
      })
      .then((d: ScenarioDraft) => { if (!cancelled) setDraft(d); })
      .catch((e) => { if (!cancelled) setError(e?.message || 'Draft failed'); })
      .finally(() => { if (!cancelled) setDrafting(false); });
    return () => { cancelled = true; };
  }, [runId, assessmentId, surpriseIndex]);

  const handleSave = async () => {
    if (!draft) return;
    setSaving(true);
    setError(null);
    try {
      const r = await fetch(`/api/forecast/${runId}/scenarios`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: draft.title,
          description: draft.description,
          horizon_type: draft.horizon_type,
          timeframe: draft.timeframe || null,
          source_assessment_id: draft.source_assessment_id,
          source_surprise_label: draft.source_surprise_label,
          source_article_uris: draft.source_article_uris,
          window_weeks: windowWeeks,
        }),
      });
      if (!r.ok) {
        const body = await r.text();
        throw new Error(`${r.status} ${body || r.statusText}`);
      }
      onScenarioCreated();
    } catch (e: any) {
      setError(e?.message || 'Save failed');
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white dark:bg-gray-900 rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="flex items-start justify-between p-5 border-b border-gray-200 dark:border-gray-700">
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Track as scenario</h3>
            <p className="text-xs text-gray-600 dark:text-gray-300 mt-1">
              Promote the cluster <span className="font-medium">"{cluster.label}"</span> ({cluster.size} articles) into a tracked scenario alongside the original forecast.
            </p>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700 dark:text-gray-300 dark:hover:text-gray-100">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {drafting && (
            <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
              <Loader2 className="w-4 h-4 animate-spin" /> Drafting scenario with LLM…
            </div>
          )}
          {error && (
            <div className="p-3 bg-red-50 dark:bg-red-900/30 border border-red-300 rounded text-red-800 dark:text-red-200 text-sm">
              {error}
            </div>
          )}
          {draft && (
            <>
              <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-200 mb-1">Title</label>
                <input
                  type="text"
                  value={draft.title}
                  onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                  className="w-full border rounded px-3 py-2 text-sm bg-white dark:bg-gray-800 dark:text-gray-100"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-200 mb-1">Description</label>
                <textarea
                  value={draft.description}
                  onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                  rows={5}
                  className="w-full border rounded px-3 py-2 text-sm bg-white dark:bg-gray-800 dark:text-gray-100 leading-relaxed"
                />
              </div>
              <div className="flex gap-4">
                <div className="flex-1">
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-200 mb-1">Horizon</label>
                  <div className="flex gap-2">
                    {(['h1', 'h2', 'h3'] as const).map((h) => (
                      <label
                        key={h}
                        className={`flex-1 cursor-pointer border rounded px-3 py-2 text-xs text-center ${
                          draft.horizon_type === h
                            ? 'border-pink-500 bg-pink-50 dark:bg-pink-900/30 text-pink-700 dark:text-pink-200'
                            : 'border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-200'
                        }`}
                      >
                        <input
                          type="radio"
                          name="horizon_type"
                          value={h}
                          checked={draft.horizon_type === h}
                          onChange={() => setDraft({ ...draft, horizon_type: h })}
                          className="sr-only"
                        />
                        {HORIZON_LABEL[h] || h.toUpperCase()}
                      </label>
                    ))}
                  </div>
                </div>
                <div className="w-32">
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-200 mb-1">Timeframe</label>
                  <input
                    type="text"
                    value={draft.timeframe}
                    onChange={(e) => setDraft({ ...draft, timeframe: e.target.value })}
                    placeholder="2026-2030"
                    className="w-full border rounded px-3 py-2 text-sm bg-white dark:bg-gray-800 dark:text-gray-100"
                  />
                </div>
              </div>
              <div className="text-[11px] text-gray-500 dark:text-gray-400">
                Saving will kick off a fresh paired assessment so the new scenario is classified against the post-forecast articles. This takes a few minutes.
              </div>
            </>
          )}
        </div>

        <div className="flex justify-end gap-2 p-4 border-t border-gray-200 dark:border-gray-700">
          <Button
            type="button"
            onClick={onClose}
            disabled={saving}
            variant="outline"
            className="text-gray-700 dark:text-gray-200"
          >
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleSave}
            disabled={!draft || saving || drafting}
            className="bg-pink-600 hover:bg-pink-700 text-white"
          >
            {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
            {saving ? 'Saving…' : 'Save & reassess'}
          </Button>
        </div>
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

/**
 * Per-scenario net_rate trajectory across all stored paired-mode assessments
 * for this topic. Each row is one scenario; horizontal bars/sparkline shows
 * how the baseline-corrected net rate has moved between reruns. Useful for
 * spotting a scenario drifting from "Below baseline" → "Above baseline" as
 * the trajectory actually materialises.
 */
function SnapshotHistoryPanel({ topic }: { topic: string }) {
  const [snaps, setSnaps] = useState<AssessmentSnapshot[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<boolean>(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`/api/forecast/snapshots/by-topic?topic=${encodeURIComponent(topic)}`)
      .then(r => r.ok ? r.json() : Promise.reject(new Error(`${r.status}`)))
      .then((data: SnapshotsResponse) => {
        if (cancelled) return;
        setSnaps(data.snapshots || []);
      })
      .catch(e => { if (!cancelled) setError(String(e?.message || e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [topic]);

  if (loading) return null;
  if (error || snaps.length < 2) return null;  // history needs ≥2 snapshots

  // Build a per-scenario timeseries from the snapshots.
  const scenarioIdxs = Array.from(new Set(
    snaps.flatMap(s => s.per_scenario.map(p => p.scenario_idx))
  )).sort((a, b) => a - b);

  const cellW = 14;
  const cellGap = 2;
  const seriesWidth = snaps.length * (cellW + cellGap);

  return (
    <div className="p-4 bg-white dark:bg-gray-800/40 border border-gray-200 dark:border-gray-700 rounded">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          Snapshot history — {snaps.length} paired assessments over time
        </h3>
        <button
          className="text-xs text-indigo-600 dark:text-indigo-300 hover:underline"
          onClick={() => setExpanded(e => !e)}
        >
          {expanded ? 'Collapse' : 'Expand details'}
        </button>
      </div>
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
        Each cell is one re-assessment. Color shows the status at that snapshot.
        Watch for a scenario shifting <span className="text-emerald-700 dark:text-emerald-300">green</span> (Strengthening) over time
        — that's a trajectory materialising.
      </p>

      {/* Date header strip */}
      <div className="flex items-center gap-1 mb-1 pl-48">
        <div className="flex" style={{ gap: `${cellGap}px` }}>
          {snaps.map((s, i) => (
            <div
              key={s.assessment_id}
              className="text-[9px] text-gray-500 dark:text-gray-400 text-center"
              style={{ width: `${cellW}px` }}
              title={new Date(s.assessed_at).toLocaleString()}
            >
              {i === 0 || i === snaps.length - 1 ? new Date(s.assessed_at).toLocaleDateString().slice(0, 5) : ''}
            </div>
          ))}
        </div>
      </div>

      {/* Per-scenario rows */}
      <div className="space-y-1.5">
        {scenarioIdxs.map(idx => {
          // Use most recent snapshot for the row label
          const latest = [...snaps].reverse().find(s => s.per_scenario.some(p => p.scenario_idx === idx));
          const label = `Scenario ${idx}`;
          return (
            <div key={idx} className="flex items-center gap-2 text-xs">
              <div className="w-48 truncate text-gray-700 dark:text-gray-200">
                {label}
              </div>
              <div className="flex" style={{ gap: `${cellGap}px` }}>
                {snaps.map(s => {
                  const cell = s.per_scenario.find(p => p.scenario_idx === idx);
                  const color = baselineFill(cell?.label);
                  const tooltip = cell
                    ? `${new Date(s.assessed_at).toLocaleDateString()}\n${cell.label}\nnet ${((cell.net_rate ?? 0) * 100).toFixed(2)}%\nlive ${cell.live_supports}/${(cell as any).live_pool ?? '?'}  placebo ${cell.placebo_supports}/${(cell as any).placebo_pool ?? '?'}`
                    : 'no data';
                  return (
                    <div
                      key={s.assessment_id}
                      title={tooltip}
                      className="h-5 rounded-sm"
                      style={{ width: `${cellW}px`, background: color }}
                    />
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      {expanded && (
        <div className="mt-3 max-h-64 overflow-y-auto border-t border-gray-200 dark:border-gray-700 pt-2 text-xs">
          <table className="w-full">
            <thead className="text-[10px] uppercase text-gray-500 dark:text-gray-400">
              <tr>
                <th className="text-left py-1">Assessed</th>
                <th className="text-left">Run</th>
                <th className="text-right">Pool</th>
                <th className="text-right">Window</th>
                <th className="text-right">Surprises</th>
              </tr>
            </thead>
            <tbody>
              {[...snaps].reverse().map(s => (
                <tr key={s.assessment_id} className="border-t border-gray-100 dark:border-gray-800">
                  <td className="py-1">{new Date(s.assessed_at).toLocaleString()}</td>
                  <td className="font-mono text-[10px] text-gray-500">{s.run_id.slice(0, 8)}…</td>
                  <td className="text-right">{s.evidence_count ?? '—'}</td>
                  <td className="text-right">{s.window_weeks ? `±${s.window_weeks}w` : 'full'}</td>
                  <td className="text-right">{s.surprises_count ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function baselineFill(label?: string | null): string {
  if (!label) return '#e5e7eb';
  if (label.includes('Above')) return '#10b981';
  if (label.includes('Below')) return '#ef4444';
  if (label.includes('At')) return '#9ca3af';
  return '#e5e7eb';
}
