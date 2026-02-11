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

export interface BWAlert {
  category: string;
  current_count: number;
  average_count: number;
  spike_ratio: number;
  severity: 'high' | 'medium';
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
