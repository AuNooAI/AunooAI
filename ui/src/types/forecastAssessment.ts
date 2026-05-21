/**
 * Types for the Forecast Assessment feature.
 *
 * A "Forecast Assessment" scores a previously-stored Three Horizons forecast
 * (future_horizons_runs row) against articles that arrived after the forecast
 * was generated. Each scenario receives a verdict label and supporting/
 * contradicting article snippets. Articles that no scenario explains are
 * surfaced as "surprises".
 */

export type VerdictLabel =
  | 'Accelerating'
  | 'On-track'
  | 'Stalled'
  | 'Off-track'
  | 'Inconclusive';

export type ArticleVerdictKind =
  | 'supports_trajectory'
  | 'supports_state_contradicts_trajectory'
  | 'contradicts'
  | 'better_fits_other_scenario'
  | 'neutral_context'
  | 'unrelated';

export type EvidenceType = 'milestone' | 'leading_indicator' | 'commentary' | 'anecdote';

export interface ForecastArticleSnippet {
  article_uri: string;
  title?: string;
  verdict: ArticleVerdictKind;
  evidence_type?: EvidenceType;
  confidence?: number;
  rationale?: string;
  article_date?: string;
}

export interface DeckInfo {
  deck_key: string;
  deck_scenario_name: string;
  consensus_pct?: number;
  primary_signal?: string;
  minority_view?: string;
  decision_fork?: { favorable?: string; adverse?: string };
  action_windows?: { '0_6_months'?: string; '6_18_months'?: string };
  constituent_db_titles?: string[];
}

export interface ScenarioVerdict {
  scenario_idx: number;
  horizon_type: 'h1' | 'h2' | 'h3';
  scenario_title: string;
  verdict_label: VerdictLabel;
  directional_rate: number;
  velocity: number;
  milestone_density: number;
  coverage: number;
  supports: number;
  contradicts: number;
  neutral: number;
  summary_md: string;
  top_articles?: {
    supports?: ForecastArticleSnippet[];
    contradicts?: ForecastArticleSnippet[];
    /** Deck-overlay enrichment (deck-granularity assessments only). */
    deck_info?: DeckInfo;
  };
}

export interface SurpriseCluster {
  size: number;
  label: string;
  sample_articles: Array<{
    uri: string;
    title?: string;
    date?: string;
  }>;
  note?: string;
}

export interface BaselineCorrection {
  method: string;
  live_assessment_id: string;
  placebo_assessment_id: string;
  live_pool: number;
  placebo_pool: number;
  per_scenario: Record<string, {
    live_supports: number;
    placebo_supports: number;
    live_pool: number;
    placebo_pool: number;
    live_rate: number;
    placebo_rate: number;
    net_rate: number;
    label: 'Above baseline' | 'At baseline' | 'Below baseline';
  }>;
}

export interface AssessmentSummary {
  topic: string;
  forecast_generated_at: string;
  assessed_at: string;
  elapsed_days: number;
  evidence_pool: number;
  assigned: number;
  classified: number;
  ambiguous: number;
  unrelated: number;
  verdict_distribution: Record<VerdictLabel, number>;
  deck_overlay_loaded: boolean;
  scenario_level?: 'deck' | 'db';
  window_weeks?: number | null;
  baseline_correction?: BaselineCorrection;
}

export interface ForecastAssessment {
  id: string;
  run_id: string;
  topic: string;
  assessed_at: string;
  evidence_count: number;
  scenarios_count: number;
  ambiguous_count: number;
  unrelated_count: number;
  surprises: SurpriseCluster[];
  summary: AssessmentSummary;
  status: string;
  mode: 'live' | 'placebo';
  model_used: string;
  runtime_seconds: number;
  scenario_verdicts: ScenarioVerdict[];
}

export interface ForecastAssessmentResponse {
  run_id: string;
  assessment: ForecastAssessment | null;
  scenarios?: Array<{
    type: 'h1' | 'h2' | 'h3';
    title: string;
    description: string;
    timeframe: string;
    sentiment?: string;
  }>;
  forecast_generated_at?: string | null;
  /** True if the assessment is tied to a different horizons run for the same topic. */
  topic_fallback?: boolean;
}

export interface AssessmentJobStatus {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  current_item?: string | null;
  result?: { assessment_id?: string; topic?: string; evidence_count?: number };
  error?: string | null;
}
