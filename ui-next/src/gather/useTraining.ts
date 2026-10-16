import { useCallback, useEffect, useRef, useState } from 'react';
import * as t from '@monolith/trainingApi';
import type {
  ConfidenceStatsResponse, CostSavingsStats, InferenceMode, LocalModelsStatus, ModelConfig, PipelineStats, PreclassifierInfo,
  RelevanceConfidenceStatsResponse, RelevanceFeedbackStats, TopicTrainingStatus, TrainingRun,
} from '@monolith/trainingApi';

/** Samples per field before DeBERTa takes over a topic (as in the old tab and TopicTrainingCard). */
export const DEBERTA_THRESHOLD = 500;
/** Relevance feedback needed before the relevance model can be trained. */
export const FEEDBACK_GOAL = 500;
const POLL_MS = 5000;
const ACTIVE_RUN = ['pending', 'running', 'exporting', 'training'];

export interface TrainingData {
  topics: TopicTrainingStatus[];
  runs: TrainingRun[];
  confidence: ConfidenceStatsResponse | null;
  relevance: RelevanceConfidenceStatsResponse | null;
  feedback: RelevanceFeedbackStats | null;
  system: { hybrid_enrichment?: { deberta_available?: boolean }; finetuning?: { current_model_exists?: boolean } } | null;
  pipeline: PipelineStats | null;
  models: ModelConfig | null;
  savings: CostSavingsStats | null;
  mode: InferenceMode;
  local: LocalModelsStatus | null;
  preclassifiers: PreclassifierInfo[];
}

const EMPTY: TrainingData = {
  topics: [], runs: [], confidence: null, relevance: null, feedback: null, system: null, pipeline: null, models: null, savings: null,
  mode: 'hybrid', local: null, preclassifiers: [],
};

const isActive = (d: Pick<TrainingData, 'runs' | 'preclassifiers'>) =>
  d.runs.some((r) => ACTIVE_RUN.includes(r.status)) || d.preclassifiers.some((p) => p.training_status === 'training');

/** Everything the AI Pipeline tab shows; loads when the tab is first opened. */
export function useTraining(enabled: boolean) {
  const [data, setData] = useState<TrainingData>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  const load = useCallback(async () => {
    // Probing the local models takes seconds (it pings each one), so it fills in after the rest
    void t.getLocalModelsStatus().then(
      (local) => setData((d) => ({ ...d, local })),
      () => undefined,
    );
    try {
      const [topics, runs, confidence, relevance, feedback, system, pipeline, models, savings, mode, pcs] = await Promise.all([
        t.getTopicsTrainingStatus(),
        t.getTrainingRuns(undefined, 10),
        t.getConfidenceStats().catch(() => null),
        t.getRelevanceConfidenceStats().catch(() => null),
        t.getRelevanceFeedbackStats().catch(() => null),
        t.getTrainingSystemStatus().catch(() => null),
        t.getPipelineStats().catch(() => null),
        t.getModelConfig().catch(() => null),
        t.getCostSavings().catch(() => null),
        t.getInferenceMode().catch(() => ({ mode: 'hybrid' as InferenceMode })),
        t.getPreclassifiers().catch(() => ({ preclassifiers: [] })),
      ]);
      setData((d) => ({
        topics, runs, confidence, relevance, feedback, system: system as TrainingData['system'], pipeline, models, savings,
        mode: mode.mode, local: d.local, preclassifiers: pcs.preclassifiers,
      }));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (enabled && !started.current) {
      started.current = true;
      void load();
    }
  }, [enabled, load]);

  // While a run or a preclassifier trains, re-read just those; reload everything when they finish
  const active = isActive(data);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(async () => {
      const [runs, pcs] = await Promise.all([
        t.getTrainingRuns(undefined, 10).catch(() => null),
        t.getPreclassifiers().catch(() => null),
      ]);
      if (!runs || !pcs) return;
      const next = { runs, preclassifiers: pcs.preclassifiers };
      setData((d) => ({ ...d, ...next }));
      if (!isActive(next)) void load();
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [active, load]);

  /** Runs an action and reloads; the error lands in the tab's banner. */
  const run = useCallback(
    async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
      try {
        const r = await fn();
        await load();
        return r;
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        return undefined;
      }
    },
    [load],
  );

  return { ...data, loading, error, clearError: () => setError(null), reload: load, run, setData };
}

export type Training = ReturnType<typeof useTraining>;

/** Topics with 4+ fields, each at the DeBERTa threshold. */
export const fullyReady = (topic: TopicTrainingStatus) => {
  const counts = Object.values(topic.field_counts);
  return counts.length >= 4 && counts.every((c) => c >= DEBERTA_THRESHOLD);
};
/** Topics where no field has reached the threshold yet (still on the LLM). */
export const collecting = (topic: TopicTrainingStatus) => Object.values(topic.field_counts).every((c) => c < DEBERTA_THRESHOLD);

/** Average progress of a topic's fields toward the threshold, 0–100. */
export function topicProgress(topic: TopicTrainingStatus) {
  const counts = Object.values(topic.field_counts);
  if (counts.length === 0) return 0;
  return Math.round(counts.reduce((s, c) => s + Math.min(c / DEBERTA_THRESHOLD, 1), 0) / counts.length * 100);
}
