/**
 * Science Funding Tracker API Service
 * Handles all API calls for the ScienceWatch dashboard
 */

// ============================================================================
// Feed Keyword Groups Types & Functions (for importing from Gather pipeline)
// ============================================================================

export interface FeedKeywordGroup {
  id: number;
  name: string;
  total_feed_items: number;
  already_imported: number;
}

export interface FeedKeywordGroupsResponse {
  groups: FeedKeywordGroup[];
}

export interface ImportFromFeedRequest {
  group_id: number;
  run_llm_classification?: boolean;
  regenerate_narrative?: boolean;
  topic?: string;
}

export interface ImportFromFeedResponse {
  import_id: number;
  status: string;
  message: string;
  articles_imported: number;
  articles_skipped: number;
}

/**
 * Get feed keyword groups with article counts
 */
export async function getFeedKeywordGroups(daysBack: number = 365): Promise<FeedKeywordGroupsResponse> {
  const params = new URLSearchParams({ days_back: daysBack.toString() });
  const response = await fetch(`/api/science-funding/feed-keyword-groups?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to get feed keyword groups: ${response.status}`);
  }

  return response.json();
}

/**
 * Import articles from feed_items into articles table
 */
export async function importFromFeed(
  request: ImportFromFeedRequest
): Promise<ImportFromFeedResponse> {
  const response = await fetch('/api/science-funding/import-from-feed', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      group_id: request.group_id,
      run_llm_classification: request.run_llm_classification || false,
      regenerate_narrative: request.regenerate_narrative || false,
      topic: request.topic || DEFAULT_SCIENCE_TOPIC,
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to import from feed: ${response.status}`);
  }

  return response.json();
}

// ============================================================================
// Core Types
// ============================================================================

export interface ScienceStats {
  total_articles: number;
  date_range_start: string | null;
  date_range_end: string | null;
  most_active_category: string | null;
  multi_category_count: number;
  category_breakdown: Record<string, number>;
}

export interface ScienceCategory {
  category: string;
  article_count: number;
  percentage: number;
  recent_trend: 'up' | 'down' | 'stable';
}

export interface ScienceArticle {
  uri: string;
  title: string;
  summary: string | null;
  news_source: string | null;
  publication_date: string | null;
  categories: string[];
  sentiment: string | null;
  bias: string | null;
  factual_reporting: string | null;
}

export interface ScienceArticlesResponse {
  articles: ScienceArticle[];
  total_count: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface TemporalData {
  month: string;
  total: number;
  by_category: Record<string, number>;
}

export interface RelatedArticle {
  uri: string;
  title: string;
  summary: string | null;
  news_source: string | null;
  publication_date: string | null;
  topic: string | null;
  similarity_score: number;
}

export interface SearchResult {
  articles: ScienceArticle[];
  total_count: number;
  query: string;
}

export interface TrackerConfig {
  default_topic: string;
  categories: Record<string, string[]>;
}

// Default topic
export const DEFAULT_SCIENCE_TOPIC = 'University Grants & Science Infrastructure Impact';

// ============================================================================
// API Functions
// ============================================================================

export async function getScienceStats(
  topic: string = DEFAULT_SCIENCE_TOPIC,
  daysBack: number = 365
): Promise<ScienceStats> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/science-funding/stats?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch science stats: ${response.status}`);
  }

  return response.json();
}

export async function getScienceArticles(params: {
  topic?: string;
  categories?: string[];
  daysBack?: number;
  sortBy?: 'date' | 'relevance' | 'category_count';
  page?: number;
  perPage?: number;
}): Promise<ScienceArticlesResponse> {
  const queryParams = new URLSearchParams();

  queryParams.append('topic', params.topic || DEFAULT_SCIENCE_TOPIC);
  if (params.categories?.length) {
    queryParams.append('categories', params.categories.join(','));
  }
  if (params.daysBack) queryParams.append('days_back', params.daysBack.toString());
  if (params.sortBy) queryParams.append('sort_by', params.sortBy);
  if (params.page) queryParams.append('page', params.page.toString());
  if (params.perPage) queryParams.append('per_page', params.perPage.toString());

  const response = await fetch(`/api/science-funding/articles?${queryParams}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch science articles: ${response.status}`);
  }

  return response.json();
}

export async function getCategoryDistribution(
  topic: string = DEFAULT_SCIENCE_TOPIC,
  daysBack: number = 365
): Promise<ScienceCategory[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/science-funding/categories?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch category distribution: ${response.status}`);
  }

  return response.json();
}

export async function getTemporalData(
  topic: string = DEFAULT_SCIENCE_TOPIC,
  daysBack: number = 365
): Promise<TemporalData[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/science-funding/temporal?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch temporal data: ${response.status}`);
  }

  return response.json();
}

export async function getRelatedArticles(
  uri: string,
  limit: number = 10
): Promise<RelatedArticle[]> {
  const params = new URLSearchParams({
    limit: limit.toString(),
  });

  const response = await fetch(
    `/api/science-funding/related/${encodeURIComponent(uri)}?${params}`,
    { credentials: 'include' }
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch related articles: ${response.status}`);
  }

  return response.json();
}

export async function searchScienceArticles(
  query: string,
  topic: string = DEFAULT_SCIENCE_TOPIC,
  limit: number = 20
): Promise<SearchResult> {
  const params = new URLSearchParams({
    query,
    topic,
    limit: limit.toString(),
  });

  const response = await fetch(`/api/science-funding/search?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to search science articles: ${response.status}`);
  }

  return response.json();
}

export async function getTrackerConfig(): Promise<TrackerConfig> {
  const response = await fetch('/api/science-funding/config', {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch tracker config: ${response.status}`);
  }

  return response.json();
}

// ============================================================================
// Analysis Types
// ============================================================================

export interface Cooccurrence {
  category1: string;
  category2: string;
  count: number;
  percentage: number;
}

export interface EscalationData {
  period: string;
  total_actions: number;
  multi_category_count: number;
  avg_categories: number;
  top_categories: string[];
}

export interface CSVImportResult {
  rows_processed: number;
  articles_found: number;
  articles_created: number;
  categories_added: number;
  errors: number;
  message: string;
}

export interface ThemeData {
  theme: string;
  article_count: number;
  percentage: number;
  keywords_matched: string[];
}

export interface ThemeEvolution {
  month: string;
  by_theme: Record<string, number>;
}

export interface EntityData {
  entity: string;
  mention_count: number;
  percentage: number;
}

export interface GeographyData {
  location: string;
  mention_count: number;
  location_type: 'domestic' | 'international';
}

export interface EscalationMarkerData {
  marker_type: string;
  article_count: number;
  percentage: number;
  keywords_matched: string[];
}

export interface EscalationTrend {
  period: string;
  by_marker: Record<string, number>;
  total_escalation_articles: number;
}

export interface DayOfWeekData {
  day: string;
  day_number: number;
  article_count: number;
  percentage: number;
}

export interface DailyIntensityData {
  date: string;
  count: number;
  rolling_avg_7day: number;
}

export interface CooccurrenceMatrix {
  categories: string[];
  matrix: number[][];
}

// ============================================================================
// Analysis API Functions
// ============================================================================

export async function getCooccurrence(
  topic: string = DEFAULT_SCIENCE_TOPIC,
  daysBack: number = 365,
  limit: number = 20
): Promise<Cooccurrence[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
    limit: limit.toString(),
  });

  const response = await fetch(`/api/science-funding/cooccurrence?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch co-occurrence data: ${response.status}`);
  }

  return response.json();
}

export async function getEscalationData(
  topic: string = DEFAULT_SCIENCE_TOPIC,
  daysBack: number = 365,
  period: 'week' | 'month' | 'quarter' = 'month'
): Promise<EscalationData[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
    period,
  });

  const response = await fetch(`/api/science-funding/escalation?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch escalation data: ${response.status}`);
  }

  return response.json();
}

export async function importCSV(
  csvContent: string,
  topic: string = DEFAULT_SCIENCE_TOPIC,
  importArticles: boolean = true
): Promise<CSVImportResult> {
  const response = await fetch('/api/science-funding/import-csv', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      csv_content: csvContent,
      topic,
      import_articles: importArticles,
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to import CSV: ${response.status}`);
  }

  return response.json();
}

export async function getThemes(
  topic: string = DEFAULT_SCIENCE_TOPIC,
  daysBack: number = 365
): Promise<ThemeData[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/science-funding/themes?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch themes: ${response.status}`);
  }

  return response.json();
}

export async function getThemesEvolution(
  topic: string = DEFAULT_SCIENCE_TOPIC,
  daysBack: number = 365
): Promise<ThemeEvolution[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/science-funding/themes/evolution?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch theme evolution: ${response.status}`);
  }

  return response.json();
}

export async function getEntities(
  topic: string = DEFAULT_SCIENCE_TOPIC,
  daysBack: number = 365
): Promise<EntityData[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/science-funding/entities?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch entities: ${response.status}`);
  }

  return response.json();
}

export async function getGeography(
  topic: string = DEFAULT_SCIENCE_TOPIC,
  daysBack: number = 365
): Promise<GeographyData[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/science-funding/geography?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch geography: ${response.status}`);
  }

  return response.json();
}

export async function getEscalationMarkers(
  topic: string = DEFAULT_SCIENCE_TOPIC,
  daysBack: number = 365
): Promise<EscalationMarkerData[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/science-funding/escalation-markers?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch escalation markers: ${response.status}`);
  }

  return response.json();
}

export async function getEscalationTrends(
  topic: string = DEFAULT_SCIENCE_TOPIC,
  daysBack: number = 365
): Promise<EscalationTrend[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/science-funding/escalation-markers/trends?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch escalation trends: ${response.status}`);
  }

  return response.json();
}

export async function getDayOfWeek(
  topic: string = DEFAULT_SCIENCE_TOPIC,
  daysBack: number = 365
): Promise<DayOfWeekData[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/science-funding/day-of-week?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch day of week data: ${response.status}`);
  }

  return response.json();
}

export async function getDailyIntensity(
  topic: string = DEFAULT_SCIENCE_TOPIC,
  daysBack: number = 365
): Promise<DailyIntensityData[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/science-funding/daily-intensity?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch daily intensity: ${response.status}`);
  }

  return response.json();
}

export async function getCooccurrenceMatrix(
  topic: string = DEFAULT_SCIENCE_TOPIC,
  daysBack: number = 365
): Promise<CooccurrenceMatrix> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/science-funding/cooccurrence-matrix?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch co-occurrence matrix: ${response.status}`);
  }

  return response.json();
}

// ============================================================================
// Semantic Analysis Types
// ============================================================================

export interface NarrativeRequest {
  topic?: string;
  days_back?: number;
  model?: string;
}

export interface NarrativeResponse {
  narrative: string;
  generated_at: string;
  data_summary: {
    total_articles: number;
    total_categorized: number;
    date_range: { start: string; end: string };
    categories: Record<string, number>;
    top_themes: Record<string, number>;
    escalation: Record<string, number>;
    top_entities: Record<string, number>;
  };
}

export interface CategoryInsightRequest {
  category: string;
  topic?: string;
  days_back?: number;
  model?: string;
}

export interface CategoryInsightResponse {
  category: string;
  insight: string;
  article_count: number;
  percentage: number;
  trend: string;
}

export interface ClassificationRun {
  run_id: number;
  topic: string;
  started_at: string | null;
  completed_at: string | null;
  articles_processed: number;
  articles_categorized: number;
  status: 'running' | 'completed' | 'failed';
  error_message: string | null;
  run_type: string;
}

export interface ClassificationRunsResponse {
  runs: ClassificationRun[];
}

export interface SavedNarrative {
  id: number;
  topic: string;
  narrative: string;
  data_summary: {
    total_articles: number;
    total_categorized: number;
    date_range: { start: string; end: string };
    categories: Record<string, number>;
    top_themes: Record<string, number>;
    escalation: Record<string, number>;
    top_entities: Record<string, number>;
  };
  days_back: number | null;
  date_range_start: string | null;
  date_range_end: string | null;
  generated_at: string;
}

export interface NarrativeListResponse {
  narratives: SavedNarrative[];
  total_count: number;
}

export interface URLImportRequest {
  url?: string;
  start_date?: string;
  end_date?: string;
  topic?: string;
  run_llm_classification?: boolean;
  regenerate_narrative?: boolean;
}

export interface ImportStartResponse {
  import_id: number;
  status: string;
  source_url?: string;
  message: string;
}

export interface ImportStatus {
  id: number;
  topic: string;
  import_type: 'file_upload' | 'url_import';
  source_url: string | null;
  filename: string | null;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  started_at: string;
  completed_at: string | null;
  rows_processed: number;
  articles_created: number;
  articles_updated: number;
  categories_added: number;
  errors: number;
  error_message: string | null;
  run_llm_classification: boolean;
  narrative_id: number | null;
}

// ============================================================================
// Semantic Analysis API Functions
// ============================================================================

export async function generateNarrative(
  request: NarrativeRequest = {}
): Promise<NarrativeResponse> {
  const response = await fetch('/api/science-funding/generate-narrative', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`Failed to generate narrative: ${response.status}`);
  }

  return response.json();
}

export async function generateCategoryInsight(
  request: CategoryInsightRequest
): Promise<CategoryInsightResponse> {
  const response = await fetch('/api/science-funding/category-insight', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`Failed to generate category insight: ${response.status}`);
  }

  return response.json();
}

export async function getClassificationRuns(
  limit: number = 10
): Promise<ClassificationRunsResponse> {
  const params = new URLSearchParams({
    limit: limit.toString(),
  });

  const response = await fetch(`/api/science-funding/classify/runs?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch classification runs: ${response.status}`);
  }

  return response.json();
}

export async function getLatestNarrative(
  topic: string = DEFAULT_SCIENCE_TOPIC
): Promise<SavedNarrative | null> {
  const params = new URLSearchParams({ topic });

  const response = await fetch(`/api/science-funding/narrative/latest?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to get latest narrative: ${response.status}`);
  }

  const data = await response.json();
  return data || null;
}

export async function listNarratives(
  topic: string = DEFAULT_SCIENCE_TOPIC,
  limit: number = 10
): Promise<NarrativeListResponse> {
  const params = new URLSearchParams({
    topic,
    limit: limit.toString(),
  });

  const response = await fetch(`/api/science-funding/narratives?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to list narratives: ${response.status}`);
  }

  return response.json();
}

export async function uploadCSVFile(
  file: File,
  options: {
    topic?: string;
    runLlmClassification?: boolean;
    regenerateNarrative?: boolean;
  } = {}
): Promise<ImportStartResponse> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('topic', options.topic || DEFAULT_SCIENCE_TOPIC);
  formData.append('run_llm_classification', String(options.runLlmClassification || false));
  formData.append('regenerate_narrative', String(options.regenerateNarrative || false));

  const response = await fetch('/api/science-funding/upload-csv', {
    method: 'POST',
    credentials: 'include',
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Failed to upload CSV: ${response.status}`);
  }

  return response.json();
}

export async function importFromURL(
  request: URLImportRequest
): Promise<ImportStartResponse> {
  const response = await fetch('/api/science-funding/import-url', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`Failed to start import: ${response.status}`);
  }

  return response.json();
}

export async function getImportStatus(importId: number): Promise<ImportStatus> {
  const response = await fetch(`/api/science-funding/import/${importId}/status`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to get import status: ${response.status}`);
  }

  return response.json();
}

// ============================================================================
// Classification API Functions
// ============================================================================

export async function runClassification(params: {
  topic?: string;
  run_type?: string;
  days_back?: number;
} = {}): Promise<{ run_id: number; status: string; message: string }> {
  const response = await fetch('/api/science-funding/classify', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      topic: params.topic || DEFAULT_SCIENCE_TOPIC,
      run_type: params.run_type || 'incremental',
      days_back: params.days_back || 30,
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to start classification: ${response.status}`);
  }

  return response.json();
}

// ============================================================================
// Scheduling Types & API Functions
// ============================================================================

export interface ScienceSchedule {
  id: number;
  name: string;
  topic: string | null;
  run_type: string;
  days_back: number;
  schedule_enabled: boolean;
  schedule_type: string | null;
  schedule_interval: number | null;
  schedule_unit: string | null;
  schedule_time: string | null;
  notify_on_complete: boolean;
  notify_threshold: number;
  last_run_at: string | null;
  next_run_at: string | null;
  last_run_status: string | null;
  last_run_articles_processed: number;
  last_run_articles_categorized: number;
  run_count: number;
}

export interface ScienceScheduleCreate {
  name: string;
  topic?: string;
  run_type?: string;
  days_back?: number;
  schedule_enabled?: boolean;
  schedule_type?: string;
  schedule_interval?: number;
  schedule_unit?: string;
  schedule_time?: string;
  notify_on_complete?: boolean;
  notify_threshold?: number;
}

export interface ScienceScheduleUpdate {
  name?: string;
  topic?: string;
  run_type?: string;
  days_back?: number;
  schedule_enabled?: boolean;
  schedule_type?: string;
  schedule_interval?: number;
  schedule_unit?: string;
  schedule_time?: string;
  notify_on_complete?: boolean;
  notify_threshold?: number;
}

export async function getSchedules(): Promise<ScienceSchedule[]> {
  const response = await fetch('/api/science-funding/schedules', {
    credentials: 'include',
  });
  if (!response.ok) throw new Error(`Failed to fetch schedules: ${response.status}`);
  const data = await response.json();
  return data.schedules;
}

export async function createSchedule(
  schedule: ScienceScheduleCreate
): Promise<{ schedule_id: number; next_run_at: string | null }> {
  const response = await fetch('/api/science-funding/schedules', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(schedule),
  });
  if (!response.ok) throw new Error(`Failed to create schedule: ${response.status}`);
  return response.json();
}

export async function updateSchedule(
  scheduleId: number,
  updates: ScienceScheduleUpdate
): Promise<void> {
  const response = await fetch(`/api/science-funding/schedules/${scheduleId}`, {
    method: 'PUT',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  if (!response.ok) throw new Error(`Failed to update schedule: ${response.status}`);
}

export async function deleteSchedule(scheduleId: number): Promise<void> {
  const response = await fetch(`/api/science-funding/schedules/${scheduleId}`, {
    method: 'DELETE',
    credentials: 'include',
  });
  if (!response.ok) throw new Error(`Failed to delete schedule: ${response.status}`);
}

export async function runScheduleNow(
  scheduleId: number
): Promise<{ articles_processed: number; articles_categorized: number }> {
  const response = await fetch(`/api/science-funding/schedules/${scheduleId}/run`, {
    method: 'POST',
    credentials: 'include',
  });
  if (!response.ok) throw new Error(`Failed to run schedule: ${response.status}`);
  return response.json();
}

export async function getSchedulesStatus(): Promise<{
  running: boolean;
  last_check_time: string | null;
  last_error: string | null;
  schedules_checked: number;
  schedules_run: number;
}> {
  const response = await fetch('/api/science-funding/schedules/status', {
    credentials: 'include',
  });
  if (!response.ok) throw new Error(`Failed to fetch schedule status: ${response.status}`);
  return response.json();
}

// ============================================================================
// Color Constants
// ============================================================================

export const CATEGORY_COLORS: Record<string, string> = {
  'Grant Freezes & Cuts': '#dc2626',          // red-600
  'NIH & Biomedical': '#2563eb',              // blue-600
  'NSF & Basic Science': '#7c3aed',           // violet-600
  'DOE & Energy Research': '#d97706',         // amber-600
  'University Impact': '#059669',              // emerald-600
  'Brain Drain & Workforce': '#db2777',       // pink-600
  'Climate & Environmental': '#16a34a',       // green-600
  'DEI & Ideological Targeting': '#9333ea',   // purple-600
  'Public Health & Medical': '#0891b2',       // cyan-600
  'International Collaboration': '#4f46e5',   // indigo-600
};

export const CATEGORY_SHORT_NAMES: Record<string, string> = {
  'Grant Freezes & Cuts': 'Grant Freezes',
  'NIH & Biomedical': 'NIH/Biomedical',
  'NSF & Basic Science': 'NSF/Basic Science',
  'DOE & Energy Research': 'DOE/Energy',
  'University Impact': 'Universities',
  'Brain Drain & Workforce': 'Brain Drain',
  'Climate & Environmental': 'Climate/Env',
  'DEI & Ideological Targeting': 'DEI Targeting',
  'Public Health & Medical': 'Public Health',
  'International Collaboration': 'Intl Collab',
};

export const CATEGORY_DESCRIPTIONS: Record<string, string> = {
  'Grant Freezes & Cuts': 'Federal funding freezes, budget cuts, grant suspensions, appropriations changes',
  'NIH & Biomedical': 'National Institutes of Health, biomedical research, clinical trials, cancer/disease research',
  'NSF & Basic Science': 'National Science Foundation, basic research, STEM, physics, chemistry, mathematics',
  'DOE & Energy Research': 'Department of Energy, national laboratories, fusion, nuclear, clean energy research',
  'University Impact': 'Higher education, research universities, academic freedom, tenure, campus impacts',
  'Brain Drain & Workforce': 'Researcher exodus, talent loss, visa issues, international students, STEM pipeline',
  'Climate & Environmental': 'Climate science, EPA, NOAA, environmental research, sustainability, biodiversity',
  'DEI & Ideological Targeting': 'Diversity mandates, ideological targeting, viewpoint diversity, equity requirements',
  'Public Health & Medical': 'CDC, FDA, public health research, pandemic preparedness, drug approval, epidemiology',
  'International Collaboration': 'Research partnerships, scientific cooperation, academic exchange, foreign collaboration',
};

// Theme colors
export const THEME_COLORS: Record<string, string> = {
  'Federal Agencies': '#2563eb',       // blue-600
  'National Labs': '#d97706',          // amber-600
  'Elite Universities': '#059669',     // emerald-600
  'Research Fields': '#7c3aed',        // violet-600
  'Policy Mechanisms': '#dc2626',      // red-600
  'Workforce': '#db2777',              // pink-600
};

// Escalation marker colors
export const ESCALATION_COLORS: Record<string, string> = {
  'Funding Actions': '#dc2626',        // red-600
  'Institutional Threats': '#d97706',  // amber-600
  'Personnel Actions': '#db2777',      // pink-600
  'Policy Escalation': '#7c3aed',      // violet-600
  'Rhetoric': '#9333ea',              // purple-600
};
