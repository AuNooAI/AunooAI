import { api } from '../../shell/api';

/*
 * Model Bias Arena on /api/model-bias-arena/* (app/routes/model_bias_arena_routes.py). Every read
 * here only reads the database. Starting a run (POST /runs) has each picked model analyse every
 * article in every round, which costs money; the page asks first.
 */

const BASE = '/api/model-bias-arena';

export interface ArenaModel { name: string; display_name: string }

export interface ArenaRun {
  id: number;
  name: string;
  description: string | null;
  benchmark_model: string;
  selected_models: string[];
  article_count: number;
  rounds: number;
  current_round: number;
  created_at: string;
  completed_at: string | null;
  status: string;
}

export interface ModelStats {
  mean_response_time: number;
  successful_evaluations: number;
  error_count: number;
  total_evaluations: number;
  success_rate: number;
}

export interface MatrixCell { value: string | null; explanation?: string | null; has_error?: boolean }

export interface MatrixRow {
  article_uri: string;
  article_title?: string | null;
  benchmark_value: string | null;
  model_values: Record<string, MatrixCell>;
  // Media bias details for the article's source, when known
  news_source?: string | null;
  bias?: string | null;
  factual_reporting?: string | null;
  mbfc_credibility_rating?: string | null;
  bias_country?: string | null;
  press_freedom?: string | null;
  media_type?: string | null;
}

export interface FieldMatrix { models: string[]; matrix: MatrixRow[] }

export interface OutlierScore { outlier_rate: number; outlier_count: number; total_articles: number; is_outlier: boolean }

export interface ArenaResults {
  run_details: ArenaRun;
  statistics: Record<string, ModelStats>;
  matrix_data?: { models?: string[]; field_matrices?: Record<string, FieldMatrix> };
  outlier_analysis?: {
    model_outlier_scores?: Record<string, OutlierScore>;
    outlier_models?: Record<string, Record<string, { article_uri: string }[]>>;
  };
}

export interface SampleArticle { uri?: string; title: string; news_source?: string; topic?: string; category?: string | null; summary?: string | null }

export interface NewRun {
  name: string;
  description: string;
  benchmark_model: string;
  selected_models: string[];
  article_count: number;
  rounds: number;
  topic: string | null;
}

export const getModels = () => api<{ models?: ArenaModel[] }>(`${BASE}/models`).then((r) => r.models ?? []);
export const getTopics = () => api<{ name: string }[]>('/api/topics').then((r) => r.map((t) => t.name));
export const getRuns = () => api<{ runs?: ArenaRun[] }>(`${BASE}/runs`).then((r) => r.runs ?? []);
/** The results route sends run_details.selected_models as a JSON string (the runs list sends a real list) */
const modelList = (v: unknown): string[] => {
  if (Array.isArray(v)) return v.map(String);
  if (typeof v === 'string') {
    try {
      const parsed = JSON.parse(v);
      if (Array.isArray(parsed)) return parsed.map(String);
    } catch {
      return v.split(',').map((x) => x.trim()).filter(Boolean);
    }
  }
  return [];
};
export const getResults = (id: number) =>
  api<ArenaResults>(`${BASE}/runs/${id}/results`).then((r) => ({ ...r, run_details: { ...r.run_details, selected_models: modelList(r.run_details?.selected_models) } }));
export const deleteRun = (id: number) => api(`${BASE}/runs/${id}`, { method: 'DELETE' });
export const startRun = (body: NewRun) => api<{ run_id: number; status: string }>(`${BASE}/runs`, { method: 'POST', json: body });
// The old page put the topic into the URL unencoded, so a topic with "&" or "#" previewed the wrong articles
export const sampleArticles = (count: number, topic: string | null) =>
  api<{ articles?: SampleArticle[] }>(`${BASE}/sample-articles?count=${count}${topic ? `&topic=${encodeURIComponent(topic)}` : ''}`).then((r) => r.articles ?? []);
export const resultsCsvUrl = (id: number) => `${BASE}/runs/${id}/export-results/csv`;

export interface TopicFields { categories: string[]; sentiments: string[]; future_signals: string[]; driver_types: string[] }

export async function getTopicFields(topic: string): Promise<TopicFields> {
  const enc = encodeURIComponent(topic);
  const [cats, opts] = await Promise.all([
    api<{ categories?: string[] }>(`/api/categories/${enc}`).catch(() => ({ categories: [] as string[] })),
    api<{ sentiments?: string[]; future_signals?: string[]; driver_types?: string[] }>(`/api/topic-options/${enc}`).catch(() => ({})),
  ]);
  const o = opts as { sentiments?: string[]; future_signals?: string[]; driver_types?: string[] };
  return { categories: cats.categories ?? [], sentiments: o.sentiments ?? [], future_signals: o.future_signals ?? [], driver_types: o.driver_types ?? [] };
}

/** The seven fields each model is asked to fill in, in the old page's order */
export const FIELDS = ['sentiment', 'future_signal', 'time_to_impact', 'driver_type', 'category', 'political_bias', 'factuality'] as const;
export const FIELD_LABEL: Record<string, string> = {
  sentiment: 'Sentiment', future_signal: 'Future signal', time_to_impact: 'Time to impact', driver_type: 'Driver type',
  category: 'Category', political_bias: 'Political bias', factuality: 'Factuality',
};

const pct = (n: number) => `${(n * 100).toFixed(1)}%`;
export { pct };

/** Share of a model's answers (errors left out) that match the benchmark, per field, 0–100 */
export function agreementByField(results: ArenaResults): { model: string; values: number[] }[] {
  const fm = results.matrix_data?.field_matrices ?? {};
  const models = results.matrix_data?.models ?? [];
  return models.map((model) => ({
    model,
    values: FIELDS.map((f) => {
      const rows = fm[f]?.matrix ?? [];
      let agree = 0;
      let total = 0;
      for (const r of rows) {
        const c = r.model_values?.[model];
        if (!c || c.has_error) continue;
        total++;
        if (c.value === r.benchmark_value) agree++;
      }
      return total ? (agree / total) * 100 : 0;
    }),
  }));
}

export interface Ranked { rank: number; name: string; responseTime: number; successRate: number; outlierRate: number; evaluations: string; score: number }

/**
 * The old page's ranking: a composite where lower is better, weighting the outlier rate 40%, the
 * failure rate 30% and response time 30% (scaled so 10 seconds counts as 1).
 */
export function rankModels(results: ArenaResults): Ranked[] {
  const scores = results.outlier_analysis?.model_outlier_scores ?? {};
  return Object.entries(results.statistics ?? {})
    .map(([name, s]) => {
      const outlierRate = scores[name]?.outlier_rate ?? 0;
      const successRate = s.success_rate ?? 0;
      const rt = s.mean_response_time ?? 0;
      return {
        rank: 0, name, responseTime: Math.round(rt), successRate, outlierRate,
        evaluations: `${s.successful_evaluations ?? 0} of ${s.total_evaluations ?? 0}`,
        score: (rt / 10000) * 0.3 + outlierRate * 0.4 + (1 - successRate) * 0.3,
      };
    })
    .sort((a, b) => a.score - b.score)
    .map((r, i) => ({ ...r, rank: i + 1 }));
}

/** The whole result as Markdown, for the PDF report */
export function resultsMarkdown(results: ArenaResults): string {
  const run = results.run_details;
  const ranked = rankModels(results);
  const agree = agreementByField(results);
  const scores = results.outlier_analysis?.model_outlier_scores ?? {};
  const lines: string[] = [
    `Benchmark: ${run.benchmark_model}. Compared: ${run.selected_models.join(', ')}.`,
    `${run.article_count} articles, ${run.rounds} round${run.rounds === 1 ? '' : 's'}, started ${new Date(run.created_at).toLocaleString('en-GB')}.`,
    '',
    '## Rankings',
    '',
    'Lower score is better: outlier rate counts 40%, failure rate 30%, response time 30%.',
    '',
    '| Rank | Model | Response time (ms) | Success rate | Outlier rate | Evaluations | Score |',
    '|---|---|---|---|---|---|---|',
    ...ranked.map((r) => `| ${r.rank} | ${r.name} | ${r.responseTime} | ${pct(r.successRate)} | ${pct(r.outlierRate)} | ${r.evaluations} | ${r.score.toFixed(3)} |`),
    '',
    '## Agreement with the benchmark, by field',
    '',
    `| Model | ${FIELDS.map((f) => FIELD_LABEL[f]).join(' | ')} |`,
    `|---|${FIELDS.map(() => '---').join('|')}|`,
    ...agree.map((a) => `| ${a.model} | ${a.values.map((v) => `${v.toFixed(0)}%`).join(' | ')} |`),
    '',
    '## Outliers',
    '',
    'How often each model disagrees with the majority across all fields.',
    '',
    ...Object.entries(scores)
      .sort((a, b) => b[1].outlier_rate - a[1].outlier_rate)
      .map(([m, s]) => `- ${m}${m === run.benchmark_model ? ' (benchmark)' : ''}: ${pct(s.outlier_rate)} outlier, ${s.outlier_count} disagreements over ${s.total_articles} articles${s.is_outlier ? ', flagged as an outlier' : ''}`),
  ];
  return lines.join('\n');
}
