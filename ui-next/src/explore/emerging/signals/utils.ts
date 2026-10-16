import type { EmergingTopic, TopicCategory } from './types';

// Category from the theme's topic_filter field, as the old signal-dashboard utils
export function deriveCategory(topicFilter: string | null): TopicCategory {
  if (!topicFilter) return 'society_other';
  const f = topicFilter.toLowerCase();
  if (f.includes('conflict') || f.includes('crisis') || f.includes('war') || f.includes('military')) return 'conflict_crisis';
  if (f.includes('policy') || f.includes('regulat') || f.includes('law') || f.includes('govern')) return 'policy_regulation';
  if (f.includes('tech') || f.includes('innovat') || f.includes('ai') || f.includes('cyber')) return 'technology_innovation';
  if (f.includes('market') || f.includes('econom') || f.includes('financ') || f.includes('trade')) return 'markets_economy';
  return 'society_other';
}

export const CATEGORY_LABELS: Record<TopicCategory, string> = {
  conflict_crisis: 'Conflict and crisis',
  policy_regulation: 'Policy and regulation',
  technology_innovation: 'Technology and innovation',
  markets_economy: 'Markets and economy',
  society_other: 'Society and other',
};

type ChipTone = 'error' | 'warning' | 'muted' | 'success' | 'neutral';
export const URGENCY: Record<string, { tone: ChipTone; label: string }> = {
  high: { tone: 'error', label: 'High urgency' },
  medium: { tone: 'warning', label: 'Medium urgency' },
  low: { tone: 'muted', label: 'Low urgency' },
};
export const VELOCITY: Record<string, { tone: ChipTone; label: string }> = {
  accelerating: { tone: 'success', label: 'Accelerating' },
  stable: { tone: 'neutral', label: 'Stable' },
  decelerating: { tone: 'error', label: 'Slowing' },
};

/** Meter tone for a 0–100 score: high scores stand out */
export const scoreTone = (score: number): 'error' | 'warning' | 'neutral' => (score >= 75 ? 'error' : score >= 55 ? 'warning' : 'neutral');

export const scoreOf = (t: EmergingTopic) => t.trend_score?.composite ?? t.composite_score ?? 0;

export function allActors(topic: EmergingTopic): string[] {
  if (!topic.actors) return [];
  return [...(topic.actors.companies ?? []), ...(topic.actors.people ?? []), ...(topic.actors.organizations ?? [])].filter(Boolean);
}

export function formatDate(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}
