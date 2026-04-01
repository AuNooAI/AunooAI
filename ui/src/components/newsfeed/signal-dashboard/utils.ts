import type { EmergingTopic, TopicCategory } from "./types";

// Derive UI category from topic_filter string
export function deriveCategory(topicFilter: string | null): TopicCategory {
  if (!topicFilter) return "society_other";
  const f = topicFilter.toLowerCase();
  if (f.includes("conflict") || f.includes("crisis") || f.includes("war") || f.includes("military"))
    return "conflict_crisis";
  if (f.includes("policy") || f.includes("regulat") || f.includes("law") || f.includes("govern"))
    return "policy_regulation";
  if (f.includes("tech") || f.includes("innovat") || f.includes("ai") || f.includes("cyber"))
    return "technology_innovation";
  if (f.includes("market") || f.includes("econom") || f.includes("financ") || f.includes("trade"))
    return "markets_economy";
  return "society_other";
}

export const CATEGORY_LABELS: Record<TopicCategory, string> = {
  conflict_crisis: "Conflict & Crisis",
  policy_regulation: "Policy & Regulation",
  technology_innovation: "Technology & Innovation",
  markets_economy: "Markets & Economy",
  society_other: "Society & Other",
};

// Left-border accent colour per urgency
export const URGENCY_ACCENT: Record<string, string> = {
  high: "var(--aunoo-red)",
  medium: "var(--aunoo-amber)",
  low: "var(--aunoo-border)",
};

export const URGENCY_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  high:   { bg: "var(--aunoo-red-subtle)",   text: "var(--aunoo-red-text)",   label: "High" },
  medium: { bg: "var(--aunoo-amber-subtle)", text: "var(--aunoo-amber-text)", label: "Medium" },
  low:    { bg: "var(--aunoo-muted-bg)",      text: "var(--aunoo-muted-text)", label: "Low" },
};

export const VELOCITY_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  accelerating: { bg: "var(--aunoo-green-subtle)", text: "var(--aunoo-green-text)", label: "\u2191 Accelerating" },
  stable:       { bg: "var(--aunoo-muted-bg)",      text: "var(--aunoo-muted-text)", label: "\u2192 Stable" },
  decelerating: { bg: "var(--aunoo-red-subtle)",    text: "var(--aunoo-red-text)",   label: "\u2193 Decelerating" },
};

export function scoreColour(score: number): string {
  if (score >= 75) return "var(--aunoo-red)";
  if (score >= 55) return "var(--aunoo-amber)";
  return "var(--aunoo-muted-text)";
}

export function allActors(topic: EmergingTopic): string[] {
  if (!topic.actors) return [];
  return [
    ...topic.actors.companies,
    ...topic.actors.people,
    ...topic.actors.organizations,
  ].filter(Boolean);
}

export function formatDate(iso: string | null): string {
  if (!iso) return "\u2014";
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}
