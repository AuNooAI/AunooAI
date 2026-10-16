import type { ChipProps } from '@aunoo/ui';

/* Shapes returned by /api/emerging-topics, as the old EmergingTopicsTab.tsx read them. */

export interface TrendScore {
  volume: number;
  velocity: number;
  diversity: number;
  novelty: number;
  composite: number;
  urgency?: 'low' | 'medium' | 'high';
}

export interface Actors {
  companies?: string[];
  people?: string[];
  organizations?: string[];
}

export type TimelineItem = string | { date?: string; event?: string };

export interface Events {
  trigger_event?: string;
  timeline?: TimelineItem[];
  current_status?: string;
}

export interface Implications {
  industry_impact?: string;
  regulatory?: string;
  market?: string;
}

export interface Signals {
  growth_indicators?: unknown[];
  risk_factors?: unknown[];
  watch_for?: unknown[];
}

export interface Synthesis {
  key_takeaway?: string;
  stakeholders_affected?: string[];
  urgency?: 'low' | 'medium' | 'high';
}

export interface OrganizationImplications {
  strategic_relevance?: string;
  stakeholder_impact?: string;
  risk_assessment?: string;
  recommended_response?: string;
}

export interface Scenario {
  type?: string;
  title?: string;
  description?: string;
  timeframe?: string;
}

export interface HorizonsResult {
  scenarios?: Scenario[];
  key_signals?: string[];
  metadata?: { model_used?: string };
  [k: string]: unknown;
}

export interface EmergingTopic {
  id: number;
  topic_label: string;
  topic_description: string;
  detection_date: string;
  detection_type: string;
  article_count: number;
  growth_rate: number;
  velocity: 'accelerating' | 'stable' | 'decelerating';
  confidence_score: number;
  key_themes: string[];
  key_entities?: string[];
  why_emerging?: string;
  representative_keywords: string[];
  status: string;
  /** The scope this theme belongs to; null for the all-topics scope */
  topic_filter?: string | null;
  topic_id?: number | null;
  trend_score?: TrendScore;
  actors?: Actors;
  events?: Events;
  implications?: Implications;
  signals?: Signals;
  synthesis?: Synthesis;
  source_count?: number;
  organization_implications?: OrganizationImplications;
  future_horizons?: HorizonsResult | null;
  first_detection_date?: string;
  last_detection_date?: string;
  detection_count?: number;
  consecutive_detections?: number;
  missed_runs?: number;
  trajectory?: string;
}

export interface TopicArticle {
  uri: string;
  title?: string;
  news_source?: string;
  publication_date?: string;
  summary?: string;
  novelty_score?: number;
  knn_distance_score?: number | null;
}

export interface TopicDetail {
  articles?: TopicArticle[];
  model_used?: string;
  error?: string;
}

export interface HighNoveltyArticle {
  article_uri: string;
  article_title?: string;
  title?: string;
  composite_novelty_score: number;
  is_outlier: boolean;
  publication_date?: string;
  topic?: string;
}

export interface HistoryPoint {
  run_date: string;
  composite_score: number;
}

export interface DetectionProgress {
  step?: number;
  progress?: number;
  message: string;
  proposed_count?: number;
  validated_count?: number;
  emerging_topics?: EmergingTopic[];
  status?: string;
  current_topic?: string | null;
  topic_index?: number;
  topic_total?: number;
  topic_progress?: number;
  topic_step?: number;
  job_id?: string;
  seq?: number;
  elapsed_seconds?: number;
}

export function formatElapsed(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const m = Math.floor(s / 60);
  return m ? `${m}m ${String(s % 60).padStart(2, '0')}s` : `${s}s`;
}

export function stepLabel(step?: number): string {
  switch (step) {
    case 1: return 'Sampling articles';
    case 2: return 'Proposing themes';
    case 3: return 'Checking articles against each theme';
    case 4: return 'Merging themes';
    case 5: return 'Deep analysis';
    case 6: return 'Saving';
    case 7: return 'Done';
    default: return '';
  }
}

type Tone = NonNullable<ChipProps['tone']>;

export const TYPE_LABEL: Record<string, { label: string; tone: Tone }> = {
  new_cluster: { label: 'New topic', tone: 'info' },
  accelerating: { label: 'Growing', tone: 'success' },
  llm_proposed: { label: 'Detected', tone: 'accent' },
};
export const typeOf = (t: string) => TYPE_LABEL[t] ?? TYPE_LABEL.llm_proposed;

export const VELOCITY_LABEL: Record<string, { label: string; tone: Tone }> = {
  accelerating: { label: 'Accelerating', tone: 'success' },
  stable: { label: 'Stable', tone: 'neutral' },
  decelerating: { label: 'Slowing', tone: 'warning' },
};

export const URGENCY_LABEL: Record<string, { label: string; tone: Tone }> = {
  low: { label: 'Low urgency', tone: 'muted' },
  medium: { label: 'Medium urgency', tone: 'warning' },
  high: { label: 'High urgency', tone: 'error' },
};

export const urgencyOf = (t: EmergingTopic) => t.synthesis?.urgency || t.trend_score?.urgency || '';
export const scoreOf = (t: EmergingTopic) => t.trend_score?.composite ?? Math.round((t.confidence_score || 0) * 100);

export const SCENARIO_LABEL: Record<string, { label: string; tone: Tone }> = {
  probable: { label: 'Probable', tone: 'success' },
  plausible: { label: 'Plausible', tone: 'info' },
  possible: { label: 'Possible', tone: 'warning' },
  wildcard: { label: 'Wild card', tone: 'accent' },
  preferable: { label: 'Preferable', tone: 'neutral' },
};

/** Signal lists can hold strings or objects; show either as text */
export const asStrings = (arr: unknown): string[] =>
  Array.isArray(arr) ? arr.map((x) => (typeof x === 'string' ? x : x && typeof x === 'object' ? JSON.stringify(x) : String(x))).filter(Boolean) : [];

/** "Date - event" strings or {date, event} objects, as one shape */
export function parseTimelineItem(item: TimelineItem): { date: string; event: string } {
  if (typeof item === 'object' && item !== null) return { date: item.date || '', event: item.event || '' };
  const str = String(item);
  const m = str.match(/^([A-Za-z]+\s+\d{1,2},?\s*\d{0,4}|\d{4}-\d{2}-\d{2}|[A-Za-z]+\s+\d{4}|Prior to [^-:]+)\s*[-:]\s*/i);
  return m ? { date: m[1].trim(), event: str.substring(m[0].length).trim() } : { date: '', event: str };
}

/** Text only when the field really is text (the model sometimes returns objects) */
export const text = (v: unknown): string | null => (typeof v === 'string' && v.trim() ? v : null);
