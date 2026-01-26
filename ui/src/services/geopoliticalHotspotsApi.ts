/**
 * Geopolitical Hotspots API Service
 * Handles all API calls for the geopolitical hotspots feature
 */

// Types
export interface Hotspot {
  id: number;
  location_name: string;
  location_type: string;
  country_code: string | null;
  country_name: string | null;
  latitude: number;
  longitude: number;
  intensity_score: number;
  risk_level: RiskLevel;
  trend: Trend | null;
  article_count: number;
  recent_article_count: number;
  primary_category: ThreatCategory | null;
  tags: string[] | null;
  last_article_date: string | null;
  created_at?: string;
  updated_at?: string;
  topic?: string;
}

export type RiskLevel = 'critical' | 'high' | 'medium' | 'low' | 'info';

export type Trend = 'escalating' | 'stable' | 'de-escalating';

export type ThreatCategory =
  | 'conflict'
  | 'protest'
  | 'disaster'
  | 'diplomatic'
  | 'economic'
  | 'terrorism'
  | 'cyber'
  | 'health'
  | 'environmental'
  | 'military'
  | 'crime'
  | 'piracy'
  | 'infrastructure'
  | 'commodities';

export const THREAT_CATEGORIES: ThreatCategory[] = [
  'conflict',
  'protest',
  'disaster',
  'diplomatic',
  'economic',
  'terrorism',
  'cyber',
  'health',
  'environmental',
  'military',
  'crime',
  'piracy',
  'infrastructure',
  'commodities',
];

export const RISK_LEVELS: RiskLevel[] = ['critical', 'high', 'medium', 'low', 'info'];

export const RISK_COLORS: Record<RiskLevel, string> = {
  critical: '#DC2626',
  high: '#F97316',
  medium: '#EAB308',
  low: '#22C55E',
  info: '#3B82F6',
};

export interface OverviewStats {
  total_hotspots: number;
  by_risk_level: Record<RiskLevel, number>;
  total_articles: number;
  recent_articles: number;
  countries_affected: number;
  escalating_count: number;
  de_escalating_count: number;
  by_category: Record<string, number>;
  top_hotspots: HotspotSummary[];
}

export interface HotspotSummary {
  id: number;
  location_name: string;
  country_name: string | null;
  intensity_score: number;
  risk_level: RiskLevel;
  primary_category: ThreatCategory | null;
  article_count: number;
  trend: Trend | null;
}

export interface CountryStats {
  country_code: string;
  country_name: string;
  total_hotspots: number;
  total_articles: number;
  heat_value: number;
  max_risk_level: RiskLevel | null;
  primary_category: ThreatCategory | null;
}

export interface HotspotArticle {
  uri: string;
  title: string | null;
  source: string | null;
  publication_date: string | null;
  summary: string | null;
  category: string | null;
  sentiment: string | null;
  relevance_score: number | null;
  mention_type: string | null;
}

export interface TimelineDataPoint {
  date: string;
  article_count: number;
  avg_intensity: number;
  hotspot_count: number;
}

export interface RegionData {
  region: string;
  hotspot_count: number;
  article_count: number;
}

export interface CategoryData {
  category: string;
  count: number;
  avg_intensity: number;
  total_articles: number;
}

export interface LinkedHotspot {
  id: number;
  name: string;
  risk_level: RiskLevel;
  category: string | null;
  intensity: number;
}

export interface LinkedArticle {
  uri: string;
  title: string | null;
  source: string | null;
  publication_date: string | null;
  summary: string | null;
  category: string | null;
  sentiment: string | null;
  relevance_score: number | null;
  mention_type: string | null;
  // Primary hotspot (highest intensity) for backward compatibility
  hotspot_id: number;
  hotspot_name: string;
  risk_level: RiskLevel;
  hotspot_category: string | null;
  intensity_score: number;
  // All linked hotspots
  hotspots: LinkedHotspot[];
}

export interface DailyCount {
  date: string;
  article_count: number;
  hotspot_count: number;
  avg_intensity: number;
  rolling_avg: number;
}

export interface DayOfWeekData {
  day: string;
  day_num: number;
  article_count: number;
}

export interface CategoryCooccurrence {
  categories: string[];
  pairs: Array<{ category1: string; category2: string; count: number }>;
  matrix: Record<string, Record<string, number>>;
}

export interface CategoryTrendPeriod {
  period: string;
  by_category: Record<string, number>;
}

export interface ActorData {
  actor: string;
  actor_type: 'state' | 'non_state' | 'organization' | 'location';
  mention_count: number;
  percentage: number;
}

export interface EscalationMarker {
  marker_type: string;
  article_count: number;
  percentage: number;
}

export interface EscalationTrend {
  period: string;
  period_date: string | null;
  total_articles: number;
  avg_intensity: number;
  escalating_count: number;
}

export interface EscalationData {
  markers: EscalationMarker[];
  trends: EscalationTrend[];
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// API Base URL
const API_BASE = '/api/geopolitical-hotspots';

// API Functions

export async function getOverviewStats(
  topic?: string,
  daysBack: number = 30
): Promise<OverviewStats> {
  const params = new URLSearchParams();
  if (topic) params.append('topic', topic);
  params.append('days_back', String(daysBack));

  const response = await fetch(`${API_BASE}/overview?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch overview stats: ${response.statusText}`);
  }
  return response.json();
}

export async function getMapData(options: {
  topic?: string;
  categories?: ThreatCategory[];
  riskLevels?: RiskLevel[];
  daysBack?: number;
}): Promise<Hotspot[]> {
  const params = new URLSearchParams();
  if (options.topic) params.append('topic', options.topic);
  if (options.categories?.length) params.append('categories', options.categories.join(','));
  if (options.riskLevels?.length) params.append('risk_levels', options.riskLevels.join(','));
  if (options.daysBack) params.append('days_back', String(options.daysBack));

  const response = await fetch(`${API_BASE}/map-data?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch map data: ${response.statusText}`);
  }
  const data = await response.json();
  return data.hotspots;
}

export async function getCountriesData(topic?: string): Promise<CountryStats[]> {
  const params = new URLSearchParams();
  if (topic) params.append('topic', topic);

  const response = await fetch(`${API_BASE}/countries?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch countries data: ${response.statusText}`);
  }
  const data = await response.json();
  return data.countries;
}

export async function getHotspots(options: {
  topic?: string;
  categories?: ThreatCategory[];
  riskLevels?: RiskLevel[];
  countryCode?: string;
  daysBack?: number;
  page?: number;
  pageSize?: number;
  sortBy?: 'intensity' | 'articles' | 'recent' | 'name' | 'updated';
  sortOrder?: 'asc' | 'desc';
}): Promise<PaginatedResponse<Hotspot>> {
  const params = new URLSearchParams();
  if (options.topic) params.append('topic', options.topic);
  if (options.categories?.length) params.append('categories', options.categories.join(','));
  if (options.riskLevels?.length) params.append('risk_levels', options.riskLevels.join(','));
  if (options.countryCode) params.append('country_code', options.countryCode);
  if (options.daysBack) params.append('days_back', String(options.daysBack));
  if (options.page) params.append('page', String(options.page));
  if (options.pageSize) params.append('page_size', String(options.pageSize));
  if (options.sortBy) params.append('sort_by', options.sortBy);
  if (options.sortOrder) params.append('sort_order', options.sortOrder);

  const response = await fetch(`${API_BASE}/hotspots?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch hotspots: ${response.statusText}`);
  }
  const data = await response.json();
  return {
    data: data.hotspots,
    total: data.total,
    page: data.page,
    page_size: data.page_size,
    total_pages: data.total_pages,
  };
}

export async function getHotspotById(hotspotId: number): Promise<Hotspot> {
  const response = await fetch(`${API_BASE}/hotspot/${hotspotId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch hotspot: ${response.statusText}`);
  }
  return response.json();
}

export async function getHotspotArticles(
  hotspotId: number,
  page: number = 1,
  pageSize: number = 20
): Promise<PaginatedResponse<HotspotArticle>> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });

  const response = await fetch(`${API_BASE}/hotspot/${hotspotId}/articles?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch hotspot articles: ${response.statusText}`);
  }
  const data = await response.json();
  return {
    data: data.articles,
    total: data.total,
    page: data.page,
    page_size: data.page_size,
    total_pages: data.total_pages,
  };
}

export async function getTimelineData(
  topic?: string,
  daysBack: number = 30
): Promise<TimelineDataPoint[]> {
  const params = new URLSearchParams();
  if (topic) params.append('topic', topic);
  params.append('days_back', String(daysBack));

  const response = await fetch(`${API_BASE}/timeline?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch timeline data: ${response.statusText}`);
  }
  const data = await response.json();
  return data.timeline;
}

export async function getRegionsData(topic?: string): Promise<RegionData[]> {
  const params = new URLSearchParams();
  if (topic) params.append('topic', topic);

  const response = await fetch(`${API_BASE}/regions?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch regions data: ${response.statusText}`);
  }
  const data = await response.json();
  return data.regions;
}

export async function getCategoriesData(topic?: string): Promise<CategoryData[]> {
  const params = new URLSearchParams();
  if (topic) params.append('topic', topic);

  const response = await fetch(`${API_BASE}/categories?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch categories data: ${response.statusText}`);
  }
  const data = await response.json();
  return data.categories;
}

export async function getAllArticles(options: {
  page?: number;
  pageSize?: number;
  riskLevel?: RiskLevel;
  category?: ThreatCategory;
  hotspotId?: number;
  search?: string;
  sortBy?: 'date' | 'title' | 'relevance' | 'intensity';
  sortOrder?: 'asc' | 'desc';
}): Promise<PaginatedResponse<LinkedArticle>> {
  const params = new URLSearchParams();
  if (options.page) params.append('page', String(options.page));
  if (options.pageSize) params.append('page_size', String(options.pageSize));
  if (options.riskLevel) params.append('risk_level', options.riskLevel);
  if (options.category) params.append('category', options.category);
  if (options.hotspotId) params.append('hotspot_id', String(options.hotspotId));
  if (options.search) params.append('search', options.search);
  if (options.sortBy) params.append('sort_by', options.sortBy);
  if (options.sortOrder) params.append('sort_order', options.sortOrder);

  const response = await fetch(`${API_BASE}/articles?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch articles: ${response.statusText}`);
  }
  const data = await response.json();
  return {
    data: data.articles,
    total: data.total,
    page: data.page,
    page_size: data.page_size,
    total_pages: data.total_pages,
  };
}

export async function getDailyCounts(
  topic?: string,
  daysBack: number = 30
): Promise<DailyCount[]> {
  const params = new URLSearchParams();
  if (topic) params.append('topic', topic);
  params.append('days_back', String(daysBack));

  const response = await fetch(`${API_BASE}/daily-counts?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch daily counts: ${response.statusText}`);
  }
  const data = await response.json();
  return data.daily_counts;
}

export async function getDayOfWeekDistribution(
  topic?: string,
  daysBack: number = 30
): Promise<DayOfWeekData[]> {
  const params = new URLSearchParams();
  if (topic) params.append('topic', topic);
  params.append('days_back', String(daysBack));

  const response = await fetch(`${API_BASE}/day-of-week?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch day of week distribution: ${response.statusText}`);
  }
  const data = await response.json();
  return data.distribution;
}

export async function getCategoryCooccurrence(
  topic?: string
): Promise<CategoryCooccurrence> {
  const params = new URLSearchParams();
  if (topic) params.append('topic', topic);

  const response = await fetch(`${API_BASE}/category-cooccurrence?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch category co-occurrence: ${response.statusText}`);
  }
  return response.json();
}

export async function getCategoryTrends(
  topic?: string,
  daysBack: number = 90,
  granularity: 'weekly' | 'monthly' = 'weekly'
): Promise<CategoryTrendPeriod[]> {
  const params = new URLSearchParams();
  if (topic) params.append('topic', topic);
  params.append('days_back', String(daysBack));
  params.append('granularity', granularity);

  const response = await fetch(`${API_BASE}/category-trends?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch category trends: ${response.statusText}`);
  }
  const data = await response.json();
  return data.trends;
}

export async function getActors(
  topic?: string,
  daysBack: number = 30
): Promise<ActorData[]> {
  const params = new URLSearchParams();
  if (topic) params.append('topic', topic);
  params.append('days_back', String(daysBack));

  const response = await fetch(`${API_BASE}/actors?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch actors: ${response.statusText}`);
  }
  const data = await response.json();
  return data.actors;
}

export async function getEscalationMarkers(
  topic?: string,
  daysBack: number = 30
): Promise<EscalationData> {
  const params = new URLSearchParams();
  if (topic) params.append('topic', topic);
  params.append('days_back', String(daysBack));

  const response = await fetch(`${API_BASE}/escalation-markers?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch escalation markers: ${response.statusText}`);
  }
  return response.json();
}

// ============================================================================
// Processing & Import Types
// ============================================================================

export interface ProcessingStats {
  total_curated_articles: number;
  processed_articles: number;
  unprocessed_articles: number;
  total_hotspots: number;
  processing_percentage: number;
  topic: string;
}

export interface AvailableTopic {
  topic: string;
  total_articles: number;
  unprocessed_count: number;
}

export interface ProcessArticlesRequest {
  batch_size: number;
  model: string;
  topic?: string;
  process_all?: boolean;
}

export interface ProcessArticlesResponse {
  status: string;
  message: string;
  articles_processed: number;
  hotspots_created: number;
  hotspots_updated: number;
  articles_skipped: number;
  errors: number;
}

// ============================================================================
// Processing & Import API Functions
// ============================================================================

export async function getProcessingStats(topic?: string): Promise<ProcessingStats> {
  const params = new URLSearchParams();
  if (topic) params.append('topic', topic);

  const response = await fetch(`${API_BASE}/processing-stats?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch processing stats: ${response.statusText}`);
  }
  return response.json();
}

export async function getAvailableTopics(): Promise<AvailableTopic[]> {
  const response = await fetch(`${API_BASE}/available-topics`);
  if (!response.ok) {
    throw new Error(`Failed to fetch available topics: ${response.statusText}`);
  }
  const data = await response.json();
  return data.topics;
}

export async function processArticles(
  request: ProcessArticlesRequest
): Promise<ProcessArticlesResponse> {
  const response = await fetch(`${API_BASE}/process-articles`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Failed to process articles: ${response.statusText}`);
  }
  return response.json();
}

// ============================================================================
// Scheduling Types & API Functions
// ============================================================================

export interface GeopoliticalSchedule {
  id: number;
  name: string;
  topic: string | null;
  batch_size: number;
  model: string;
  process_all: boolean;
  schedule_enabled: boolean;
  schedule_type: 'interval' | 'daily' | null;
  schedule_interval: number | null;
  schedule_unit: 'minutes' | 'hours' | 'days' | null;
  schedule_time: string | null;
  notify_on_complete: boolean;
  notify_threshold: number;
  last_run_at: string | null;
  next_run_at: string | null;
  last_run_status: 'success' | 'error' | 'running' | null;
  last_run_error: string | null;
  last_run_articles_processed: number;
  last_run_hotspots_created: number;
  last_run_hotspots_updated: number;
  run_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface CreateScheduleRequest {
  name: string;
  topic?: string;
  batch_size?: number;
  model?: string;
  process_all?: boolean;
  schedule_enabled?: boolean;
  schedule_type?: 'interval' | 'daily';
  schedule_interval?: number;
  schedule_unit?: 'minutes' | 'hours' | 'days';
  schedule_time?: string;
  notify_on_complete?: boolean;
  notify_threshold?: number;
}

export interface UpdateScheduleRequest {
  name?: string;
  topic?: string;
  batch_size?: number;
  model?: string;
  process_all?: boolean;
  schedule_enabled?: boolean;
  schedule_type?: 'interval' | 'daily';
  schedule_interval?: number;
  schedule_unit?: 'minutes' | 'hours' | 'days';
  schedule_time?: string;
  notify_on_complete?: boolean;
  notify_threshold?: number;
}

export async function getSchedules(): Promise<GeopoliticalSchedule[]> {
  const response = await fetch(`${API_BASE}/schedules`);
  if (!response.ok) {
    throw new Error(`Failed to fetch schedules: ${response.statusText}`);
  }
  const data = await response.json();
  return data.schedules;
}

export async function createSchedule(request: CreateScheduleRequest): Promise<{ schedule_id: number; next_run_at: string | null }> {
  const response = await fetch(`${API_BASE}/schedules`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Failed to create schedule: ${response.statusText}`);
  }
  return response.json();
}

export async function updateSchedule(scheduleId: number, request: UpdateScheduleRequest): Promise<void> {
  const response = await fetch(`${API_BASE}/schedules/${scheduleId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Failed to update schedule: ${response.statusText}`);
  }
}

export async function deleteSchedule(scheduleId: number): Promise<void> {
  const response = await fetch(`${API_BASE}/schedules/${scheduleId}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Failed to delete schedule: ${response.statusText}`);
  }
}

export async function runScheduleNow(scheduleId: number): Promise<ProcessArticlesResponse> {
  const response = await fetch(`${API_BASE}/schedules/${scheduleId}/run`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Failed to run schedule: ${response.statusText}`);
  }
  return response.json();
}

export interface MonitorStatus {
  running: boolean;
  last_check_time: string | null;
  last_error: string | null;
  schedules_checked: number;
  schedules_run: number;
  is_checking: boolean;
}

export async function getMonitorStatus(): Promise<MonitorStatus> {
  const response = await fetch(`${API_BASE}/schedules/status`);
  if (!response.ok) {
    throw new Error(`Failed to fetch monitor status: ${response.statusText}`);
  }
  return response.json();
}
