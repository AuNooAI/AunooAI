/**
 * Brand Watcher API Service
 * Handles all API calls for the Brand Watcher module
 */

// ============================================================================
// Types
// ============================================================================

export interface Brand {
  id: number;
  name: string;
  display_name: string;
  description: string | null;
  brand_keywords: string[];
  product_keywords: string[] | null;
  people_keywords: string[] | null;
  competitor_keywords: string[] | null;
  enabled: boolean;
  color: string | null;
  is_primary: boolean;
  config?: Record<string, any>;
  created_at: string | null;
  updated_at: string | null;
}

export interface BWSentimentTrend {
  week: string;
  category: string;
  sentiments: Record<string, number>;
  total: number;
}

export interface BWAlertArticle {
  uri: string;
  title: string;
  publication_date: string | null;
  sentiment: string | null;
  news_source: string | null;
}

export interface BWAlert {
  category: string;
  current_count: number;
  average_count: number;
  spike_ratio: number;
  severity: 'high' | 'medium';
  articles?: BWAlertArticle[];
}

export interface BrandCreate {
  name: string;
  display_name: string;
  description?: string;
  brand_keywords: string[];
  product_keywords?: string[];
  people_keywords?: string[];
  competitor_keywords?: string[];
  color?: string;
}

export interface BrandUpdate {
  display_name?: string;
  description?: string;
  brand_keywords?: string[];
  product_keywords?: string[];
  people_keywords?: string[];
  competitor_keywords?: string[];
  color?: string;
}

export interface BWStats {
  total_articles: number;
  total_brands: number;
  date_range_start: string | null;
  date_range_end: string | null;
  most_active_category: string | null;
  multi_category_count: number;
  category_breakdown: Record<string, number>;
}

export interface BWCategory {
  category: string;
  article_count: number;
  percentage: number;
  recent_trend: 'up' | 'down' | 'stable';
}

export interface BWArticle {
  uri: string;
  title: string;
  summary: string | null;
  news_source: string | null;
  publication_date: string | null;
  categories: string[];
  brand_id: number | null;
  brand_name: string | null;
  sentiment: string | null;
  matched_keywords: string[];
  // Opoint entity verification (Wikidata-ID match), present when available.
  entity_match?: { brands: string[]; relevance: number | null; verified: boolean } | null;
  // Story clustering: republication count ("×N sources") + cluster key for dedup.
  story_size?: number | null;
  story_group_id?: string | null;
  story_neg?: number | null;
  story_pos?: number | null;
  story_scored?: number | null;
  // MBFC source authority (when the source is in the mediabias dataset).
  factual_reporting?: string | null;
  // Adverse risk findings [{risk_type, severity, confidence}] + case state.
  risks?: { risk_type: string; severity: string; confidence?: number | null }[];
  review_status?: string | null;
}

// ---- Adverse alerting ----
export interface BWAlertConfig {
  id: number;
  enabled: boolean;
  rules: Record<string, any>;
  channels: { in_app?: boolean; email?: boolean; webhook?: boolean; digest?: { enabled?: boolean; frequency?: 'daily' | 'weekly'; hour_utc?: number } };
  email_recipients: string[];
  webhook_url: string | null;
  cooldown_hours: number;
}

export interface BWAlertEvent {
  id: number;
  brand_id: number | null;
  brand_name: string | null;
  rule: string;
  severity: string;
  title: string;
  body: string | null;
  payload: any;
  delivered: Record<string, boolean> | null;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  created_at: string | null;
}

export interface BWOpointCoverage {
  brand: string;
  articles_matched: number;
  avg_relevance: number;
  high_confidence: number;
  reach_weight: number;
  article_sov_pct: number;
  reach_sov_pct: number;
}

export interface BWOpointCoverageResponse {
  window_days: number;
  min_relevance: number;
  opoint_articles_scanned: number;
  exclude_scholarly?: boolean;
  scholarly_excluded?: number;
  reach_metric?: string;
  brand_wikidata: Record<string, string[]>;
  coverage: BWOpointCoverage[];
  samples: any[];
}

export interface BWOpointPoV {
  brand: string;
  topic: string;
  window_days: number;
  volume: { opoint_articles: number; existing_articles: number };
  source_domains: { opoint: number; existing: number; opoint_only: number; shared: number; existing_only: number; opoint_only_sample: string[] };
  enrichment_exclusive: Record<string, { opoint: number; existing: number }>;
  precision: { opoint_entity_verified: number; keyword_classified: number; wikidata_ids: string[] };
  chargeable_value: { min_relevance: number; opoint_total: number; on_brand: number; non_scholarly: number; chargeable: number; chargeable_with_reach: number; chargeable_rate_pct: number };
  relevance_histogram: { bucket: string; count: number }[];
  top_opoint_only_domains: { domain: string; articles: number; scholarly: boolean }[];
  monthly: { month: string; opoint: number; existing: number }[];
  by_country: { country: string; count: number }[];
  chargeable_samples: { title: string; url: string; source: string; relevance: number; rank_global: number | null }[];
  cost: { annual_eur: number; chargeable: number; cost_per_chargeable_eur: number | null };
}

export async function getOpointPoV(brandId: number, daysBack: number = 90): Promise<BWOpointPoV> {
  const params = new URLSearchParams({ brand_id: String(brandId), days_back: String(daysBack) });
  const res = await fetch(`${BASE}/opoint-pov?${params}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to get Opoint proof-of-value: ${res.status}`);
  return res.json();
}

export interface BWSocialMeta {
  platform?: string;
  external_id?: string;
  author?: string;
  thumbnail?: string | null;
  likes?: number | null;
  reposts?: number | null;
  comments?: number | null;
  plays?: number | null;
  subreddit?: string | null;
}

export interface BWSocialPost {
  uri: string;
  title: string;
  summary: string | null;
  news_source: string | null;
  platform: string;
  publication_date: string | null;
  relevance: number | null;
  sentiment: string | null;
  topic: string | null;
  matched_keywords?: string[];
  social_meta?: BWSocialMeta | null;
}

export interface BWSocialResponse {
  window_days: number;
  min_relevance: number;
  include_unevaluated?: boolean;
  keyword?: string | null;
  total: number;
  evaluated: number;
  by_platform: Record<string, number>;
  by_sentiment: Record<string, number>;
  by_keyword?: Record<string, number>;
  posts: BWSocialPost[];
}

export interface BWArticlesResponse {
  articles: BWArticle[];
  total_count: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface BWTemporalData {
  month: string;
  total: number;
  by_category: Record<string, number>;
}

export interface BWComparison {
  brand_id: number;
  brand_name: string;
  total_articles: number;
  category_breakdown: Record<string, number>;
  sentiment_breakdown: Record<string, number>;
  color: string | null;
}

export interface BWShareOfVoice {
  brand_id: number;
  brand_name: string;
  mention_count: number;
  percentage: number;
  color: string | null;
}

export interface BWNarrativeRequest {
  brand_id: number;
  days_back?: number;
  model?: string;
}

export interface BWNarrativeResponse {
  narrative: string;
  generated_at: string;
  data_summary: {
    total_articles: number;
    date_range: { start: string; end: string };
    categories: Record<string, number>;
    competitors: Record<string, number>;
  };
}

export interface BWCategoryInsightRequest {
  brand_id: number;
  category: string;
  days_back?: number;
  model?: string;
}

export interface BWCategoryInsightResponse {
  category: string;
  insight: string;
  article_count: number;
  percentage: number;
  trend: string;
}

export interface BWSavedNarrative {
  id: number;
  brand_id: number;
  brand_name: string | null;
  narrative: string;
  data_summary: {
    total_articles: number;
    date_range: { start: string; end: string };
    categories: Record<string, number>;
    competitors: Record<string, number>;
  };
  days_back: number | null;
  date_range_start: string | null;
  date_range_end: string | null;
  generated_at: string | null;
}

export interface BWClassificationRun {
  run_id: number;
  brand_id: number | null;
  brand_name: string | null;
  started_at: string | null;
  completed_at: string | null;
  articles_processed: number;
  articles_categorized: number;
  status: 'running' | 'completed' | 'failed';
  error_message: string | null;
  run_type: string;
}

export interface BWConfig {
  categories: Record<string, string[]>;
  category_colors: Record<string, string>;
}

export interface BWSchedule {
  id: number;
  name: string;
  brand_id: number | null;
  brand_name: string | null;
  run_type: string;
  days_back: number;
  topics: string[] | null;
  schedule_enabled: boolean;
  schedule_type: string;
  schedule_interval: number | null;
  schedule_unit: string;
  schedule_time: string | null;
  notify_on_complete: boolean;
  notify_threshold: number;
  last_run_at: string | null;
  next_run_at: string | null;
  last_run_status: string | null;
  last_run_articles_processed: number;
  last_run_articles_categorized: number;
  run_count: number;
  created_at: string | null;
}

export interface BWScheduleCreate {
  name: string;
  brand_id?: number | null;
  topics?: string[];
  run_type?: string;
  days_back?: number;
  schedule_enabled?: boolean;
  schedule_type?: string;
  schedule_interval?: number;
  schedule_unit?: string;
  schedule_time?: string;
}

// ============================================================================
// API Functions
// ============================================================================

const BASE = '/api/brand-watcher';

// --- Brands ---

export async function getBrands(): Promise<Brand[]> {
  const res = await fetch(`${BASE}/brands`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to get brands: ${res.status}`);
  return res.json();
}

export async function createBrand(brand: BrandCreate): Promise<Brand> {
  const res = await fetch(`${BASE}/brands`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(brand),
  });
  if (!res.ok) throw new Error(`Failed to create brand: ${res.status}`);
  return res.json();
}

export async function updateBrand(id: number, updates: BrandUpdate): Promise<Brand> {
  const res = await fetch(`${BASE}/brands/${id}`, {
    method: 'PUT', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error(`Failed to update brand: ${res.status}`);
  return res.json();
}

export async function deleteBrand(id: number, cleanupMonitoring?: boolean): Promise<void> {
  const params = cleanupMonitoring ? '?cleanup_monitoring=true' : '';
  const res = await fetch(`${BASE}/brands/${id}${params}`, {
    method: 'DELETE', credentials: 'include',
  });
  if (!res.ok) throw new Error(`Failed to delete brand: ${res.status}`);
}

export async function toggleBrand(id: number): Promise<{ id: number; enabled: boolean }> {
  const res = await fetch(`${BASE}/brands/${id}/toggle`, {
    method: 'PUT', credentials: 'include',
  });
  if (!res.ok) throw new Error(`Failed to toggle brand: ${res.status}`);
  return res.json();
}

export async function setPrimaryBrand(brandId: number): Promise<{ id: number; is_primary: boolean }> {
  const res = await fetch(`${BASE}/brands/${brandId}/set-primary`, {
    method: 'PUT', credentials: 'include',
  });
  if (!res.ok) throw new Error(`Failed to set primary brand: ${res.status}`);
  return res.json();
}

export async function setupBrandMonitoring(brandId: number): Promise<{
  brand_id: number;
  topic_name: string;
  topic_created: boolean;
  group_name: string;
  group_created: boolean;
  keywords_added: number;
}> {
  const res = await fetch(`${BASE}/brands/${brandId}/setup-monitoring`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error(`Failed to setup monitoring: ${res.status}`);
  return res.json();
}

// --- Keyword Suggestions ---

export async function suggestKeywords(brandName: string, description?: string): Promise<{
  brand_keywords: string[];
  product_keywords: string[];
  people_keywords: string[];
  competitor_keywords: string[];
}> {
  const res = await fetch(`${BASE}/suggest-keywords`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ brand_name: brandName, description }),
  });
  if (!res.ok) throw new Error(`Failed to suggest keywords: ${res.status}`);
  return res.json();
}

// --- Classification ---

export async function classifyArticles(params: {
  brand_id?: number; topics?: string[]; run_type?: string; days_back?: number;
} = {}): Promise<{ run_id: number; status: string; message: string }> {
  const res = await fetch(`${BASE}/classify`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      brand_id: params.brand_id || null,
      topics: params.topics?.length ? params.topics : null,
      run_type: params.run_type || 'incremental',
      days_back: params.days_back || 30,
    }),
  });
  if (!res.ok) throw new Error(`Failed to start classification: ${res.status}`);
  return res.json();
}

export async function getTopics(): Promise<{ topic: string; article_count: number }[]> {
  const res = await fetch(`${BASE}/topics`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to get topics: ${res.status}`);
  return res.json();
}

export async function getClassifyStatus(runId: number): Promise<BWClassificationRun> {
  const res = await fetch(`${BASE}/classify/status/${runId}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to get run status: ${res.status}`);
  return res.json();
}

export async function getClassifyRuns(limit: number = 10): Promise<{ runs: BWClassificationRun[] }> {
  const params = new URLSearchParams({ limit: limit.toString() });
  const res = await fetch(`${BASE}/classify/runs?${params}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to get runs: ${res.status}`);
  return res.json();
}

// --- Stats & Analytics ---

export async function getStats(brandIds?: number[], daysBack: number = 365, topics?: string[]): Promise<BWStats> {
  const params = new URLSearchParams({ days_back: daysBack.toString() });
  if (brandIds?.length) params.append('brand_ids', brandIds.join(','));
  if (topics?.length) params.append('topics', topics.join(','));
  const res = await fetch(`${BASE}/stats?${params}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to get stats: ${res.status}`);
  return res.json();
}

export async function getCategories(brandIds?: number[], daysBack: number = 365, topics?: string[]): Promise<BWCategory[]> {
  const params = new URLSearchParams({ days_back: daysBack.toString() });
  if (brandIds?.length) params.append('brand_ids', brandIds.join(','));
  if (topics?.length) params.append('topics', topics.join(','));
  const res = await fetch(`${BASE}/categories?${params}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to get categories: ${res.status}`);
  return res.json();
}

export async function getOpointCoverage(daysBack: number = 90, minRelevance: number = 0, excludeScholarly: boolean = false): Promise<BWOpointCoverageResponse> {
  const params = new URLSearchParams({ days: Math.min(daysBack, 365).toString(), min_relevance: minRelevance.toString(), samples: '8', exclude_scholarly: String(excludeScholarly) });
  const res = await fetch(`${BASE}/opoint-coverage?${params}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to get Opoint coverage: ${res.status}`);
  return res.json();
}

export async function setupSocialMonitoring(brandId: number, intervalHours: number = 24, model?: string): Promise<any> {
  const res = await fetch(`${BASE}/brands/${brandId}/social-monitoring`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ interval_hours: intervalHours, model: model || null }),
  });
  if (!res.ok) throw new Error(`Failed to set up social monitoring: ${res.status}`);
  return res.json();
}

export async function getSocialPosts(
  topics?: string[], daysBack: number = 30, minRelevance: number = 0, source?: string, includeUnevaluated: boolean = true,
  opts?: { startDate?: string; endDate?: string; limit?: number; keyword?: string },
): Promise<BWSocialResponse> {
  const params = new URLSearchParams({ days_back: daysBack.toString(), min_relevance: minRelevance.toString(), include_unevaluated: includeUnevaluated.toString(), limit: (opts?.limit ?? 200).toString() });
  if (topics?.length) params.append('topics', topics.join(','));
  if (source) params.append('source', source);
  if (opts?.startDate) params.append('start_date', opts.startDate);
  if (opts?.endDate) params.append('end_date', opts.endDate);
  if (opts?.keyword) params.append('keyword', opts.keyword);
  const res = await fetch(`${BASE}/social?${params}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to get social posts: ${res.status}`);
  return res.json();
}

export async function getTemporal(brandIds?: number[], daysBack: number = 365, topics?: string[]): Promise<BWTemporalData[]> {
  const params = new URLSearchParams({ days_back: daysBack.toString() });
  if (brandIds?.length) params.append('brand_ids', brandIds.join(','));
  if (topics?.length) params.append('topics', topics.join(','));
  const res = await fetch(`${BASE}/temporal?${params}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to get temporal data: ${res.status}`);
  return res.json();
}

export async function getComparison(daysBack: number = 365, topics?: string[]): Promise<BWComparison[]> {
  const params = new URLSearchParams({ days_back: daysBack.toString() });
  if (topics?.length) params.append('topics', topics.join(','));
  const res = await fetch(`${BASE}/comparison?${params}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to get comparison: ${res.status}`);
  return res.json();
}

export async function getShareOfVoice(daysBack: number = 365, topics?: string[]): Promise<BWShareOfVoice[]> {
  const params = new URLSearchParams({ days_back: daysBack.toString() });
  if (topics?.length) params.append('topics', topics.join(','));
  const res = await fetch(`${BASE}/share-of-voice?${params}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to get share of voice: ${res.status}`);
  return res.json();
}

// --- Articles ---

export async function getArticles(params: {
  brand_ids?: number[];
  topics?: string[];
  categories?: string[];
  days_back?: number;
  sort_by?: string;
  page?: number;
  per_page?: number;
}): Promise<BWArticlesResponse> {
  const q = new URLSearchParams();
  if (params.brand_ids?.length) q.append('brand_ids', params.brand_ids.join(','));
  if (params.topics?.length) q.append('topics', params.topics.join(','));
  if (params.categories?.length) q.append('categories', params.categories.join(','));
  if (params.days_back) q.append('days_back', params.days_back.toString());
  if (params.sort_by) q.append('sort_by', params.sort_by);
  if (params.page) q.append('page', params.page.toString());
  if (params.per_page) q.append('per_page', params.per_page.toString());

  const res = await fetch(`${BASE}/articles?${q}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to get articles: ${res.status}`);
  return res.json();
}

// --- Narrative / Insights ---

export async function generateNarrative(request: BWNarrativeRequest): Promise<BWNarrativeResponse> {
  const res = await fetch(`${BASE}/generate-narrative`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!res.ok) throw new Error(`Failed to generate narrative: ${res.status}`);
  return res.json();
}

export async function getLatestNarrative(brandId: number): Promise<BWSavedNarrative | null> {
  const params = new URLSearchParams({ brand_id: brandId.toString() });
  const res = await fetch(`${BASE}/narrative/latest?${params}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to get latest narrative: ${res.status}`);
  const data = await res.json();
  return data || null;
}

export async function generateCategoryInsight(
  request: BWCategoryInsightRequest
): Promise<BWCategoryInsightResponse> {
  const res = await fetch(`${BASE}/category-insight`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!res.ok) throw new Error(`Failed to generate category insight: ${res.status}`);
  return res.json();
}

// --- SLM ---

export async function getSlmStatus(): Promise<{ available: boolean; error?: string }> {
  const res = await fetch(`${BASE}/slm/status`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to get SLM status: ${res.status}`);
  return res.json();
}

export async function classifyWithSlm(text: string, threshold?: number): Promise<any> {
  const res = await fetch(`${BASE}/slm/classify`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, threshold }),
  });
  if (!res.ok) throw new Error(`Failed to classify with SLM: ${res.status}`);
  return res.json();
}

// --- Config ---

export async function getConfig(): Promise<BWConfig> {
  const res = await fetch(`${BASE}/config`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to get config: ${res.status}`);
  return res.json();
}

// --- Schedules ---

export async function getSchedules(): Promise<{ schedules: BWSchedule[] }> {
  const res = await fetch(`${BASE}/schedules`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to get schedules: ${res.status}`);
  return res.json();
}

export async function createSchedule(schedule: BWScheduleCreate): Promise<{ schedule_id: number; next_run_at: string | null }> {
  const res = await fetch(`${BASE}/schedules`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(schedule),
  });
  if (!res.ok) throw new Error(`Failed to create schedule: ${res.status}`);
  return res.json();
}

export async function updateSchedule(id: number, updates: Partial<BWScheduleCreate & { schedule_enabled: boolean }>): Promise<void> {
  const res = await fetch(`${BASE}/schedules/${id}`, {
    method: 'PUT', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error(`Failed to update schedule: ${res.status}`);
}

export async function deleteSchedule(id: number): Promise<void> {
  const res = await fetch(`${BASE}/schedules/${id}`, {
    method: 'DELETE', credentials: 'include',
  });
  if (!res.ok) throw new Error(`Failed to delete schedule: ${res.status}`);
}

export async function runScheduleNow(id: number): Promise<{ run_id: number }> {
  const res = await fetch(`${BASE}/schedules/${id}/run`, {
    method: 'POST', credentials: 'include',
  });
  if (!res.ok) throw new Error(`Failed to run schedule: ${res.status}`);
  return res.json();
}

// --- Sentiment Trends ---

export async function getSentimentTrends(brandId: number, daysBack: number = 365, topics?: string[]): Promise<{ trends: BWSentimentTrend[] }> {
  const params = new URLSearchParams({ days_back: daysBack.toString() });
  if (topics?.length) params.append('topics', topics.join(','));
  const res = await fetch(`${BASE}/brands/${brandId}/sentiment-trends?${params}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to get sentiment trends: ${res.status}`);
  return res.json();
}

// --- Alerts ---

export async function getBrandAlerts(brandId: number, daysBack: number = 30): Promise<{ alerts: BWAlert[] }> {
  const params = new URLSearchParams({ days_back: daysBack.toString() });
  const res = await fetch(`${BASE}/brands/${brandId}/alerts?${params}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to get alerts: ${res.status}`);
  return res.json();
}

// --- Export ---

export async function exportBrandData(brandId: number, format: 'csv' | 'json' = 'csv', daysBack: number = 365): Promise<any> {
  const params = new URLSearchParams({ format, days_back: daysBack.toString() });
  const res = await fetch(`${BASE}/brands/${brandId}/export?${params}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to export: ${res.status}`);
  if (format === 'csv') {
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `brand_watcher_export.csv`;
    a.click();
    URL.revokeObjectURL(url);
    return null;
  }
  return res.json();
}

// --- Brand Config ---

export async function updateBrandConfig(brandId: number, config: Record<string, any>): Promise<{ config: Record<string, any> }> {
  const res = await fetch(`${BASE}/brands/${brandId}/config`, {
    method: 'PUT', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!res.ok) throw new Error(`Failed to update brand config: ${res.status}`);
  return res.json();
}

// --- Retrain ---

export async function retrainClassifier(): Promise<{ status: string; message: string }> {
  const res = await fetch(`${BASE}/classifier/retrain`, {
    method: 'POST', credentials: 'include',
  });
  if (!res.ok) throw new Error(`Failed to trigger retrain: ${res.status}`);
  return res.json();
}

// ============================================================================
// Color Constants
// ============================================================================

export const CATEGORY_COLORS: Record<string, string> = {
  'Product & Innovation': '#2563eb',
  'Financial Performance': '#16a34a',
  'Leadership & Governance': '#7c3aed',
  'Brand Sentiment & Perception': '#db2777',
  'Competitive Landscape': '#d97706',
  'Legal & Regulatory': '#dc2626',
  'Partnerships & Alliances': '#0891b2',
  'ESG & Social Responsibility': '#059669',
  'Customer & Product Issues': '#e11d48',
  'Market Strategy & Expansion': '#4f46e5',
  'Media & Advertising': '#9333ea',
};

export const CATEGORY_SHORT_NAMES: Record<string, string> = {
  'Product & Innovation': 'Product',
  'Financial Performance': 'Financial',
  'Leadership & Governance': 'Leadership',
  'Brand Sentiment & Perception': 'Perception',
  'Competitive Landscape': 'Competition',
  'Legal & Regulatory': 'Legal',
  'Partnerships & Alliances': 'Partnerships',
  'ESG & Social Responsibility': 'ESG',
  'Customer & Product Issues': 'Issues',
  'Market Strategy & Expansion': 'Strategy',
  'Media & Advertising': 'Media',
};


// ---- Adverse alerting API ----
export async function getAlertConfig(): Promise<BWAlertConfig> {
  const res = await fetch(`${BASE}/alert-config`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to get alert config: ${res.status}`);
  return res.json();
}

export async function updateAlertConfig(cfg: Partial<BWAlertConfig>): Promise<BWAlertConfig> {
  const res = await fetch(`${BASE}/alert-config`, {
    method: 'PUT', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg),
  });
  if (!res.ok) throw new Error(`Failed to update alert config: ${res.status}`);
  return res.json();
}

export async function listAlertEvents(unackedOnly = false, limit = 50): Promise<BWAlertEvent[]> {
  const res = await fetch(`${BASE}/alert-events?unacked_only=${unackedOnly}&limit=${limit}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to list alert events: ${res.status}`);
  return (await res.json()).events || [];
}

export async function ackAlertEvent(id: number): Promise<void> {
  await fetch(`${BASE}/alert-events/${id}/ack`, { method: 'POST', credentials: 'include' });
}

export async function evaluateAlertsNow(): Promise<{ created: number }> {
  const res = await fetch(`${BASE}/alert-events/evaluate-now`, { method: 'POST', credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to evaluate alerts: ${res.status}`);
  return res.json();
}

// ---- Finding case states ----
export async function setFindingState(articleUri: string, brandId: number, status: 'new' | 'reviewed' | 'escalated' | 'dismissed', note?: string): Promise<void> {
  const res = await fetch(`${BASE}/findings/state`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ article_uri: articleUri, brand_id: brandId, status, note: note || null }),
  });
  if (!res.ok) throw new Error(`Failed to set finding state: ${res.status}`);
}

// ---- Official / scholarly sources (SEC EDGAR, CourtListener, regulations.gov, Crossref, OpenAlex) ----
export interface BWOfficialSource {
  key: string;
  label: string;
  description: string;
  enabled: boolean;
  available: boolean;          // false when a required API key is not configured server-side
  requires_key: string | null;
  last_polled_at: string | null;
  article_count: number;
}

export interface BWBrandSources {
  brand_id: number;
  display_name: string;
  sources: BWOfficialSource[];
}

export async function getOfficialSourcesStatus(): Promise<BWBrandSources[]> {
  const res = await fetch(`${BASE}/official-sources/status`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to load official sources status: ${res.status}`);
  return (await res.json()).brands || [];
}

export async function pollOfficialSourcesNow(brandId?: number): Promise<{
  polled: number; new_articles: number; risk_flagged: number; errors: number;
}> {
  const qs = brandId ? `?brand_id=${brandId}` : '';
  const res = await fetch(`${BASE}/official-sources/poll-now${qs}`, { method: 'POST', credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to poll official sources: ${res.status}`);
  return res.json();
}

export interface BWStorySibling {
  uri: string;
  title: string;
  summary?: string | null;
  news_source?: string | null;
  publication_date?: string | null;
  bias?: string | null;
  factual_reporting?: string | null;
  sentiment?: string | null;
}

export async function getStorySiblings(groupId: string, brandId?: number | null): Promise<BWStorySibling[]> {
  const q = new URLSearchParams({ group_id: groupId });
  if (brandId) q.append('brand_id', String(brandId));
  const res = await fetch(`${BASE}/story-siblings?${q}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to load story siblings: ${res.status}`);
  return (await res.json()).articles || [];
}

// ---- Incident management + evidence locker ----
export interface BWIncident {
  id: number;
  brand_id: number;
  brand_name: string;
  title: string;
  description?: string | null;
  severity: 'low' | 'medium' | 'high' | 'critical';
  status: 'open' | 'investigating' | 'contained' | 'resolved' | 'closed';
  owner?: string | null;
  created_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  resolved_at?: string | null;
  evidence_count?: number;
  event_count?: number;
}

export interface BWIncidentEvent {
  kind: string;
  actor?: string | null;
  old_value?: string | null;
  new_value?: string | null;
  note?: string | null;
  at?: string | null;
}

export interface BWIncidentEvidence {
  id: number;
  evidence_type: string;
  source_ref?: string | null;
  title?: string | null;
  content: string;
  meta?: Record<string, any> | null;
  content_sha256: string;
  chain_sha256: string;
  captured_by?: string | null;
  captured_at?: string | null;
}

export interface BWIncidentDetail extends BWIncident {
  timeline: BWIncidentEvent[];
  evidence: BWIncidentEvidence[];
}

export async function listIncidents(status?: string, brandId?: number): Promise<BWIncident[]> {
  const q = new URLSearchParams();
  if (status) q.append('status', status);
  if (brandId) q.append('brand_id', String(brandId));
  const res = await fetch(`${BASE}/incidents?${q}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to list incidents: ${res.status}`);
  return (await res.json()).incidents || [];
}

export async function createIncident(brandId: number, title: string, description?: string, severity: string = 'medium'): Promise<{ id: number }> {
  const res = await fetch(`${BASE}/incidents`, {
    method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ brand_id: brandId, title, description: description || null, severity }),
  });
  if (!res.ok) throw new Error(`Failed to create incident: ${res.status}`);
  return res.json();
}

export async function getIncident(id: number): Promise<BWIncidentDetail> {
  const res = await fetch(`${BASE}/incidents/${id}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to load incident: ${res.status}`);
  return res.json();
}

export async function updateIncident(id: number, updates: { title?: string; description?: string; severity?: string; status?: string; owner?: string; note?: string }): Promise<void> {
  const res = await fetch(`${BASE}/incidents/${id}`, {
    method: 'PUT', credentials: 'include', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error(`Failed to update incident: ${res.status}`);
}

export async function addIncidentNote(id: number, note: string): Promise<void> {
  const res = await fetch(`${BASE}/incidents/${id}/note`, {
    method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note }),
  });
  if (!res.ok) throw new Error(`Failed to add note: ${res.status}`);
}

export async function attachIncidentEvidence(id: number, evidence: { evidence_type: string; source_ref?: string; title?: string; content?: string }): Promise<{ id: number; content_sha256: string; chain_sha256: string }> {
  const res = await fetch(`${BASE}/incidents/${id}/evidence`, {
    method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(evidence),
  });
  if (!res.ok) throw new Error(`Failed to attach evidence: ${res.status}`);
  return res.json();
}

export async function verifyIncidentChain(id: number): Promise<{ items: number; intact: boolean; broken_ids: number[] }> {
  const res = await fetch(`${BASE}/incidents/${id}/verify-chain`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to verify chain: ${res.status}`);
  return res.json();
}
