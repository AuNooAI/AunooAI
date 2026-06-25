/**
 * Policy Tracker API Service
 * Handles all API calls for the Policy Tracker dashboard
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
export async function getFeedKeywordGroups(): Promise<FeedKeywordGroupsResponse> {
  const response = await fetch('/api/policy-tracker/feed-keyword-groups', {
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
  const response = await fetch('/api/policy-tracker/import-from-feed', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      group_id: request.group_id,
      run_llm_classification: request.run_llm_classification || false,
      regenerate_narrative: request.regenerate_narrative || false,
      topic: request.topic || DEFAULT_TRACKER_TOPIC,
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

// Types matching backend schemas
export interface PolicyStats {
  total_articles: number;
  date_range_start: string | null;
  date_range_end: string | null;
  most_active_category: string | null;
  multi_category_count: number;
  category_breakdown: Record<string, number>;
}

export interface PolicyCategory {
  category: string;
  article_count: number;
  percentage: number;
  recent_trend: 'up' | 'down' | 'stable';
}

export interface PolicyArticle {
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

export interface PolicyArticlesResponse {
  articles: PolicyArticle[];
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
  articles: PolicyArticle[];
  total_count: number;
  query: string;
}

export interface TrackerConfig {
  default_topic: string;
  categories: Record<string, string[]>;
}

// Default topic
export const DEFAULT_TRACKER_TOPIC = 'Trump Administration Tracker';

// API Functions

/**
 * Get overview statistics for the policy tracker
 */
export async function getPolicyStats(
  topic: string = DEFAULT_TRACKER_TOPIC,
  daysBack: number = 365
): Promise<PolicyStats> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/policy-tracker/stats?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch policy stats: ${response.status}`);
  }

  return response.json();
}

/**
 * Get paginated list of articles for the policy tracker
 */
export async function getPolicyArticles(params: {
  topic?: string;
  categories?: string[];
  daysBack?: number;
  sortBy?: 'date' | 'relevance' | 'category_count';
  page?: number;
  perPage?: number;
}): Promise<PolicyArticlesResponse> {
  const queryParams = new URLSearchParams();

  queryParams.append('topic', params.topic || DEFAULT_TRACKER_TOPIC);
  if (params.categories?.length) {
    queryParams.append('categories', params.categories.join(','));
  }
  if (params.daysBack) queryParams.append('days_back', params.daysBack.toString());
  if (params.sortBy) queryParams.append('sort_by', params.sortBy);
  if (params.page) queryParams.append('page', params.page.toString());
  if (params.perPage) queryParams.append('per_page', params.perPage.toString());

  const response = await fetch(`/api/policy-tracker/articles?${queryParams}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch policy articles: ${response.status}`);
  }

  return response.json();
}

/**
 * Get distribution of articles across policy categories
 */
export async function getCategoryDistribution(
  topic: string = DEFAULT_TRACKER_TOPIC,
  daysBack: number = 365
): Promise<PolicyCategory[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/policy-tracker/categories?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch category distribution: ${response.status}`);
  }

  return response.json();
}

/**
 * Get monthly article counts by category for time series charts
 */
export async function getTemporalData(
  topic: string = DEFAULT_TRACKER_TOPIC,
  daysBack: number = 365
): Promise<TemporalData[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/policy-tracker/temporal?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch temporal data: ${response.status}`);
  }

  return response.json();
}

/**
 * Find related articles using vector similarity search
 */
export async function getRelatedArticles(
  uri: string,
  limit: number = 10
): Promise<RelatedArticle[]> {
  const params = new URLSearchParams({
    limit: limit.toString(),
  });

  const response = await fetch(
    `/api/policy-tracker/related/${encodeURIComponent(uri)}?${params}`,
    { credentials: 'include' }
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch related articles: ${response.status}`);
  }

  return response.json();
}

/**
 * Perform semantic search within tracker articles
 */
export async function searchPolicyArticles(
  query: string,
  topic: string = DEFAULT_TRACKER_TOPIC,
  limit: number = 20
): Promise<SearchResult> {
  const params = new URLSearchParams({
    query,
    topic,
    limit: limit.toString(),
  });

  const response = await fetch(`/api/policy-tracker/search?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to search policy articles: ${response.status}`);
  }

  return response.json();
}

/**
 * Get the policy tracker configuration
 */
export async function getTrackerConfig(): Promise<TrackerConfig> {
  const response = await fetch('/api/policy-tracker/config', {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch tracker config: ${response.status}`);
  }

  return response.json();
}

// New types for additional analysis
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

/**
 * Get category co-occurrence analysis
 */
export async function getCooccurrence(
  topic: string = DEFAULT_TRACKER_TOPIC,
  daysBack: number = 365,
  limit: number = 20
): Promise<Cooccurrence[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
    limit: limit.toString(),
  });

  const response = await fetch(`/api/policy-tracker/cooccurrence?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch co-occurrence data: ${response.status}`);
  }

  return response.json();
}

/**
 * Get escalation analysis over time
 */
export async function getEscalationData(
  topic: string = DEFAULT_TRACKER_TOPIC,
  daysBack: number = 365,
  period: 'week' | 'month' | 'quarter' = 'month'
): Promise<EscalationData[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
    period,
  });

  const response = await fetch(`/api/policy-tracker/escalation?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch escalation data: ${response.status}`);
  }

  return response.json();
}

/**
 * Import CSV data into the policy tracker
 */
export async function importCSV(
  csvContent: string,
  topic: string = DEFAULT_TRACKER_TOPIC,
  importArticles: boolean = true
): Promise<CSVImportResult> {
  const response = await fetch('/api/policy-tracker/import-csv', {
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

// Color mapping for categories (for charts) - using short names matching database
export const CATEGORY_COLORS: Record<string, string> = {
  'Democratic Norms': '#3B82F6',          // blue-500
  'Rule of Law': '#1D4ED8',               // blue-700
  'Hollowing State': '#EF4444',           // red-500
  'Suppressing Dissent': '#F97316',       // orange-500
  'Controlling Information': '#EAB308',   // yellow-500
  'Science & Health Control': '#22C55E',  // green-500
  'Attacking Education': '#06B6D4',       // cyan-500
  'Weakening Civil Rights': '#EC4899',    // pink-500
  'Corruption & Enrichment': '#6366F1',   // indigo-500
  'Foreign Policy / Nationalism': '#8B5CF6', // violet-500
};

// Short names for categories (for compact displays) - now identity mapping since we use short names
export const CATEGORY_SHORT_NAMES: Record<string, string> = {
  'Democratic Norms': 'Democratic Norms',
  'Rule of Law': 'Rule of Law',
  'Hollowing State': 'Hollowing State',
  'Suppressing Dissent': 'Suppressing Dissent',
  'Controlling Information': 'Info Control',
  'Science & Health Control': 'Science/Health',
  'Attacking Education': 'Education',
  'Weakening Civil Rights': 'Civil Rights',
  'Corruption & Enrichment': 'Corruption',
  'Foreign Policy / Nationalism': 'Foreign Policy',
};

// Category descriptions for tooltips and inline documentation
export const CATEGORY_DESCRIPTIONS: Record<string, string> = {
  'Democratic Norms': 'Undermining democracy, electoral integrity, constitutional processes',
  'Rule of Law': 'Undermining judicial independence, defying courts, politicizing DOJ/FBI',
  'Hollowing State': 'Systematic weakening of federal agencies, mass firings, DOGE',
  'Suppressing Dissent': 'Targeting opponents, protesters, activists, journalists',
  'Controlling Information': 'Misinformation, propaganda, attacking media, censoring data',
  'Science & Health Control': 'Politicizing CDC/FDA/NIH/EPA, suppressing science',
  'Attacking Education': 'Targeting universities, DEI programs, academic freedom',
  'Weakening Civil Rights': 'Rolling back LGBTQ+, reproductive, voting rights protections',
  'Corruption & Enrichment': 'Self-dealing, conflicts of interest, nepotism',
  'Foreign Policy / Nationalism': 'Aggressive foreign policy, immigration crackdowns, deportations',
};

// ============================================================================
// New EDA Analysis Types
// ============================================================================

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

// Theme colors
export const THEME_COLORS: Record<string, string> = {
  'Immigration': '#EF4444',       // red-500
  'Press/Media': '#F97316',       // orange-500
  'Courts/Judges': '#EAB308',     // yellow-500
  'Federal Workforce': '#22C55E', // green-500
  'Science/Health': '#06B6D4',    // cyan-500
  'Universities': '#3B82F6',      // blue-500
  'Military': '#8B5CF6',          // violet-500
  'Venezuela': '#EC4899',         // pink-500
  'Greenland': '#14B8A6',         // teal-500
};

// Escalation marker colors
export const ESCALATION_COLORS: Record<string, string> = {
  'Threats': '#EF4444',           // red-500
  'Military': '#8B5CF6',          // violet-500
  'Emergency Powers': '#F97316',  // orange-500
  'Defiance': '#EAB308',          // yellow-500
  'Violent Imagery': '#DC2626',   // red-600
};

// ============================================================================
// New EDA Analysis API Functions
// ============================================================================

/**
 * Get theme frequency analysis
 */
export async function getThemes(
  topic: string = DEFAULT_TRACKER_TOPIC,
  daysBack: number = 365
): Promise<ThemeData[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/policy-tracker/themes?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch themes: ${response.status}`);
  }

  return response.json();
}

/**
 * Get theme evolution over time
 */
export async function getThemesEvolution(
  topic: string = DEFAULT_TRACKER_TOPIC,
  daysBack: number = 365
): Promise<ThemeEvolution[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/policy-tracker/themes/evolution?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch theme evolution: ${response.status}`);
  }

  return response.json();
}

/**
 * Get entity mention counts
 */
export async function getEntities(
  topic: string = DEFAULT_TRACKER_TOPIC,
  daysBack: number = 365
): Promise<EntityData[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/policy-tracker/entities?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch entities: ${response.status}`);
  }

  return response.json();
}

/**
 * Get geographic focus analysis
 */
export async function getGeography(
  topic: string = DEFAULT_TRACKER_TOPIC,
  daysBack: number = 365
): Promise<GeographyData[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/policy-tracker/geography?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch geography: ${response.status}`);
  }

  return response.json();
}

/**
 * Get escalation marker analysis
 */
export async function getEscalationMarkers(
  topic: string = DEFAULT_TRACKER_TOPIC,
  daysBack: number = 365
): Promise<EscalationMarkerData[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/policy-tracker/escalation-markers?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch escalation markers: ${response.status}`);
  }

  return response.json();
}

/**
 * Get escalation marker trends over time
 */
export async function getEscalationTrends(
  topic: string = DEFAULT_TRACKER_TOPIC,
  daysBack: number = 365
): Promise<EscalationTrend[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/policy-tracker/escalation-markers/trends?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch escalation trends: ${response.status}`);
  }

  return response.json();
}

/**
 * Get day of week distribution
 */
export async function getDayOfWeek(
  topic: string = DEFAULT_TRACKER_TOPIC,
  daysBack: number = 365
): Promise<DayOfWeekData[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/policy-tracker/day-of-week?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch day of week data: ${response.status}`);
  }

  return response.json();
}

/**
 * Get daily intensity with rolling average
 */
export async function getDailyIntensity(
  topic: string = DEFAULT_TRACKER_TOPIC,
  daysBack: number = 365
): Promise<DailyIntensityData[]> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/policy-tracker/daily-intensity?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch daily intensity: ${response.status}`);
  }

  return response.json();
}

/**
 * Get full co-occurrence matrix for heatmap
 */
export async function getCooccurrenceMatrix(
  topic: string = DEFAULT_TRACKER_TOPIC,
  daysBack: number = 365
): Promise<CooccurrenceMatrix> {
  const params = new URLSearchParams({
    topic,
    days_back: daysBack.toString(),
  });

  const response = await fetch(`/api/policy-tracker/cooccurrence-matrix?${params}`, {
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

export interface SemanticClassifyRequest {
  article_uri: string;
  title: string;
  summary: string;
  model?: string;
}

export interface SemanticClassifyResponse {
  article_uri: string;
  categories: string[];
  confidence: number;
  reasoning: string;
  method: string;
}

export interface SemanticBatchRequest {
  topic?: string;
  days_back?: number;
  limit?: number;
  model?: string;
  reprocess?: boolean;
}

export interface SemanticBatchResponse {
  run_id?: number;
  articles_processed: number;
  articles_categorized: number;
  articles_skipped: number;
  errors: number;
  message: string;
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

// ============================================================================
// Semantic Analysis API Functions
// ============================================================================

/**
 * Classify a single article using LLM semantic analysis
 */
export async function semanticClassifyArticle(
  request: SemanticClassifyRequest
): Promise<SemanticClassifyResponse> {
  const response = await fetch('/api/policy-tracker/semantic-classify', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`Failed to classify article: ${response.status}`);
  }

  return response.json();
}

/**
 * Start batch semantic classification in background
 */
export async function semanticClassifyBatch(
  request: SemanticBatchRequest = {}
): Promise<SemanticBatchResponse> {
  const response = await fetch('/api/policy-tracker/semantic-classify/batch', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`Failed to start batch classification: ${response.status}`);
  }

  return response.json();
}

/**
 * Get recent classification runs
 */
export async function getClassificationRuns(
  limit: number = 10
): Promise<ClassificationRunsResponse> {
  const params = new URLSearchParams({
    limit: limit.toString(),
  });

  const response = await fetch(`/api/policy-tracker/classify/runs?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch classification runs: ${response.status}`);
  }

  return response.json();
}

/**
 * Get status of a specific classification run
 */
export async function getClassificationStatus(
  runId: number
): Promise<ClassificationRun> {
  const response = await fetch(`/api/policy-tracker/classify/status/${runId}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch classification status: ${response.status}`);
  }

  return response.json();
}

/**
 * Generate a narrative analysis report using LLM
 */
export async function generateNarrative(
  request: NarrativeRequest = {}
): Promise<NarrativeResponse> {
  const response = await fetch('/api/policy-tracker/generate-narrative', {
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

/**
 * Generate an LLM-powered insight for a specific category
 */
export async function generateCategoryInsight(
  request: CategoryInsightRequest
): Promise<CategoryInsightResponse> {
  const response = await fetch('/api/policy-tracker/category-insight', {
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

// ============================================================================
// Import and Narrative Persistence Types & Functions
// ============================================================================

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

/**
 * Upload a CSV file for import
 */
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
  formData.append('topic', options.topic || DEFAULT_TRACKER_TOPIC);
  formData.append('run_llm_classification', String(options.runLlmClassification || false));
  formData.append('regenerate_narrative', String(options.regenerateNarrative || false));

  const response = await fetch('/api/policy-tracker/upload-csv', {
    method: 'POST',
    credentials: 'include',
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Failed to upload CSV: ${response.status}`);
  }

  return response.json();
}

/**
 * Import data from a URL (or fetch from Trump Action Tracker)
 */
export async function importFromURL(
  request: URLImportRequest
): Promise<ImportStartResponse> {
  const response = await fetch('/api/policy-tracker/import-url', {
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

/**
 * Get the status of an import operation
 */
export async function getImportStatus(importId: number): Promise<ImportStatus> {
  const response = await fetch(`/api/policy-tracker/import/${importId}/status`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to get import status: ${response.status}`);
  }

  return response.json();
}

/**
 * Get the most recently saved narrative
 */
export async function getLatestNarrative(
  topic: string = DEFAULT_TRACKER_TOPIC
): Promise<SavedNarrative | null> {
  const params = new URLSearchParams({ topic });

  const response = await fetch(`/api/policy-tracker/narrative/latest?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to get latest narrative: ${response.status}`);
  }

  const data = await response.json();
  return data || null;
}

/**
 * List historical narratives
 */
export async function listNarratives(
  topic: string = DEFAULT_TRACKER_TOPIC,
  limit: number = 10
): Promise<NarrativeListResponse> {
  const params = new URLSearchParams({
    topic,
    limit: limit.toString(),
  });

  const response = await fetch(`/api/policy-tracker/narratives?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to list narratives: ${response.status}`);
  }

  return response.json();
}
