export interface EmergingTopic {
  id: number;
  name: string;
  description: string | null;
  topic_id: number | null;
  article_count: number | null;
  composite_score: number | null;
  confidence_score: number | null;
  velocity: "accelerating" | "stable" | "decelerating" | null;
  detection_type: "llm_proposed" | "ongoing_topic" | null;
  keywords: string[];
  topic_filter: string | null;
  first_detected_at: string | null;

  actors: {
    companies: string[];
    people: string[];
    organizations: string[];
  } | null;

  events: {
    trigger_event: string;
    timeline: string[];
    current_status: string;
  } | null;

  implications: {
    industry_impact: string;
    regulatory: string;
    market: string;
  } | null;

  signals: {
    growth_indicators: string[];
    risk_factors: string[];
    watch_for: string[];
  } | null;

  synthesis: {
    key_takeaway: string;
    stakeholders_affected: string[];
    urgency: "low" | "medium" | "high";
  } | null;

  trend_score: {
    volume: number;
    velocity: number;
    diversity: number;
    novelty: number;
    composite: number;
  } | null;

  detection_count: number | null;
  consecutive_detections: number | null;
  missed_runs: number | null;
  first_detection_date: string | null;
  last_detection_date: string | null;
}

// Derived from topic_filter field
export type TopicCategory =
  | "conflict_crisis"
  | "policy_regulation"
  | "technology_innovation"
  | "markets_economy"
  | "society_other";

export type FilterMode = "all" | "accelerating" | "high_urgency";
