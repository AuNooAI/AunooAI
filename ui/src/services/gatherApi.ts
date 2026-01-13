/**
 * API client for Gather (Keyword Monitor) endpoints
 */

export interface KeywordGroup {
  id: number;
  name: string;
  topic: string;
  created_at: string;
  provider?: string;
  source?: string;
}

export interface MonitoredKeyword {
  id: number;
  group_id: number;
  keyword: string;
  created_at: string;
  last_checked?: string;
}

export interface KeywordMonitorSettings {
  check_interval: number;
  interval_unit: number;
  search_fields: string;
  language: string;
  sort_by: string;
  page_size: number;
  daily_request_limit: number;
  provider: string;
  providers?: string;
  auto_ingest_enabled: boolean;
  min_relevance_threshold: number;
  quality_control_enabled: boolean;
  auto_save_approved_only: boolean;
  default_llm_model?: string;
  llm_temperature: number;
  llm_max_tokens: number;
  auto_regenerate_reports: boolean;
  is_enabled?: boolean;
  search_date_range?: number;
}

export interface KeywordStats {
  keyword_id: number;
  keyword: string;
  group_id: number;
  group_name: string;
  topic: string;
  total_matches: number;
  avg_relevance: number;
  avg_topic_alignment: number;
  avg_confidence: number;
  high_relevance_count: number;
  high_relevance_pct: number;
  low_relevance_count: number;
  low_relevance_pct: number;
}

export interface MonitorStatus {
  running: boolean;
  last_check_time?: string;
  next_check_time?: string;
  last_error?: string;
  requests_today: number;
  daily_limit: number;
  is_enabled: boolean;
}

export interface KeywordGroupSummary {
  id: number;
  name: string;
  topic: string;
  keyword_count: number;
  total_articles: number;
  avg_relevance: number;
  high_relevance_pct: number;
  recent_articles_24h: number;
  last_checked?: string;
  last_error?: string;
  status: 'success' | 'error' | 'pending' | 'never_run';
  relevance_pct: number;       // % of scored articles that are relevant
  // Relevance-based article counts
  relevant_count: number;      // Articles that passed relevance scoring (enriched)
  irrelevant_count: number;    // Articles that didn't pass relevance scoring
  unscored_count: number;      // Articles without any relevance score (for troubleshooting)
  // Time-based counts
  articles_past_24h: number;
  articles_past_week: number;
  articles_past_month: number;
  daily_counts: [string, number][]; // [date, count] tuples for sparkline
}

export interface ArticleMatch {
  id: number;
  uri: string;
  title: string;
  source?: string;
  publication_date?: string;
  detected_at: string;
  // Scores
  keyword_relevance_score?: number;
  topic_alignment_score?: number;
  overall_match_explanation?: string;
  // Content
  category?: string;
  summary?: string;
  // Enrichment fields with explanations
  sentiment?: string;
  sentiment_explanation?: string;
  time_to_impact?: string;
  time_to_impact_explanation?: string;
  driver_type?: string;
  driver_type_explanation?: string;
}

export interface AvailableProvider {
  id: string;
  name: string;
  description: string;
  configured: boolean;
}

const API_BASE = '/api/keyword-monitor';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    credentials: 'include',
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || `HTTP ${response.status}`);
  }

  // Check content type to ensure we're getting JSON
  const contentType = response.headers.get('content-type');
  if (!contentType || !contentType.includes('application/json')) {
    console.error('API returned non-JSON response:', contentType);
    throw new Error('API returned non-JSON response - you may need to log in again');
  }

  return response.json();
}

// Settings
export async function getSettings(): Promise<KeywordMonitorSettings> {
  return fetchJson<KeywordMonitorSettings>(`${API_BASE}/settings`);
}

export async function updateSettings(settings: Partial<KeywordMonitorSettings>): Promise<{ success: boolean }> {
  return fetchJson(`${API_BASE}/settings`, {
    method: 'POST',
    body: JSON.stringify(settings),
  });
}

// Groups
export async function getKeywordGroups(): Promise<KeywordGroup[]> {
  return fetchJson<KeywordGroup[]>(`${API_BASE}/groups`);
}

export async function createKeywordGroup(name: string, topic: string): Promise<KeywordGroup> {
  return fetchJson(`${API_BASE}/groups`, {
    method: 'POST',
    body: JSON.stringify({ name, topic }),
  });
}

export async function deleteKeywordGroup(groupId: number): Promise<{ success: boolean }> {
  return fetchJson(`${API_BASE}/groups/${groupId}`, {
    method: 'DELETE',
  });
}

// Keywords
export async function getKeywords(groupId?: number): Promise<MonitoredKeyword[]> {
  const url = groupId ? `${API_BASE}/keywords?group_id=${groupId}` : `${API_BASE}/keywords`;
  return fetchJson<MonitoredKeyword[]>(url);
}

export async function addKeyword(groupId: number, keyword: string): Promise<MonitoredKeyword> {
  return fetchJson(`${API_BASE}/keywords`, {
    method: 'POST',
    body: JSON.stringify({ group_id: groupId, keyword }),
  });
}

export async function updateKeyword(keywordId: number, keyword: string): Promise<{ success: boolean }> {
  return fetchJson(`${API_BASE}/keywords/${keywordId}`, {
    method: 'PUT',
    body: JSON.stringify({ keyword }),
  });
}

export async function deleteKeyword(keywordId: number): Promise<{ success: boolean }> {
  return fetchJson(`${API_BASE}/keywords/${keywordId}`, {
    method: 'DELETE',
  });
}

// Delete unscored articles for a group
export async function deleteUnscoredArticles(groupId: number): Promise<{ success: boolean; deleted_count: number; message: string }> {
  return fetchJson(`${API_BASE}/group/${groupId}/unscored-articles`, {
    method: 'DELETE',
  });
}

// Status & Stats
export async function getMonitorStatus(): Promise<MonitorStatus> {
  interface StatusResponse {
    background_task?: { running?: boolean; last_check_time?: string; next_check_time?: string; last_error?: string };
    settings?: { is_enabled?: boolean; daily_request_limit?: number };
    api_usage?: { requests_today?: number; limit?: number };
  }
  const response = await fetchJson<StatusResponse>(`${API_BASE}/status`);
  return {
    running: response?.background_task?.running || false,
    last_check_time: response?.background_task?.last_check_time,
    next_check_time: response?.background_task?.next_check_time,
    last_error: response?.background_task?.last_error,
    requests_today: response?.api_usage?.requests_today || 0,
    daily_limit: response?.api_usage?.limit || response?.settings?.daily_request_limit || 100,
    is_enabled: response?.settings?.is_enabled ?? true,
  };
}

export async function getRelevanceStats(): Promise<KeywordStats[]> {
  const response = await fetchJson<{ keywords: KeywordStats[], summary: unknown }>(`${API_BASE}/relevance-stats`);
  return response?.keywords || [];
}

// Group summary (aggregated stats per group)
export async function getGroupSummaries(): Promise<KeywordGroupSummary[]> {
  return fetchJson<KeywordGroupSummary[]>(`${API_BASE}/group-summary`);
}

// Articles for a keyword
export async function getArticlesForKeyword(
  keywordId: number,
  groupId: number,
  filter?: 'all' | 'high' | 'low',
  limit?: number
): Promise<ArticleMatch[]> {
  const params = new URLSearchParams();
  params.set('group_id', groupId.toString());
  if (filter) params.set('filter', filter);
  if (limit) params.set('limit', limit.toString());

  return fetchJson<ArticleMatch[]>(`${API_BASE}/keyword/${keywordId}/articles?${params}`);
}

// Recent articles for a group
export async function getRecentArticlesForGroup(
  groupId: number,
  limit: number = 20
): Promise<ArticleMatch[]> {
  return fetchJson<ArticleMatch[]>(`${API_BASE}/group/${groupId}/articles?limit=${limit}`);
}

// Trigger keyword check
export async function triggerKeywordCheck(
  groupId?: number,
  topic?: string
): Promise<{ success: boolean; message?: string; new_articles?: number }> {
  return fetchJson(`${API_BASE}/check-now`, {
    method: 'POST',
    body: JSON.stringify({ group_id: groupId, topic }),
  });
}

// Toggle scheduled collection (is_enabled)
export async function toggleScheduledCollection(
  enabled: boolean
): Promise<{ status: string; enabled: boolean }> {
  return fetchJson(`${API_BASE}/toggle-polling`, {
    method: 'POST',
    body: JSON.stringify({ enabled }),
  });
}

// Test process a single article through enrichment workflow
export interface TestProcessStep {
  name: string;
  status: 'success' | 'error' | 'warning' | 'info';
  message: string;
  details: Record<string, unknown>;
}

export interface TestProcessResult {
  success: boolean;
  steps: TestProcessStep[];
  enrichment_fields: Record<string, string>;
  message: string;
}

export async function testProcessArticle(
  articleUri: string,
  groupId: number
): Promise<TestProcessResult> {
  return fetchJson(`${API_BASE}/test-process-article`, {
    method: 'POST',
    body: JSON.stringify({ article_uri: articleUri, group_id: groupId }),
  });
}

// Available providers
export async function getAvailableProviders(): Promise<AvailableProvider[]> {
  const response = await fetchJson<{ providers: AvailableProvider[] }>(`${API_BASE}/available-providers`);
  return response?.providers || [];
}

// Available LLM models
export interface AvailableModel {
  name: string;
  description?: string;
}

export async function getAvailableModels(): Promise<AvailableModel[]> {
  const response = await fetchJson<{ success: boolean; models: AvailableModel[] }>('/api/auto-ingest/models');
  return response?.models || [];
}

// Topics (for dropdowns)
export async function getTopics(): Promise<string[]> {
  // API returns array directly: [{ name: "...", ... }, ...]
  const response = await fetchJson<Array<{ name: string }>>('/api/topics');
  return (response || []).map(t => t.name);
}

// ============================================================================
// Keyword Suggestion / Optimization
// ============================================================================

export interface KeywordSuggestion {
  keyword: string;
  reason: string;
}

export interface LowRelevanceArticle {
  title: string;
  url: string;
  relevance_score: number;
}

export interface KeywordSuggestionResult {
  keyword_id: number;
  keyword: string;
  group_id: number;
  topic: string;
  current_performance: {
    keyword_id: number;
    keyword: string;
    total_matches: number;
    avg_relevance: number;
    high_relevance_count: number;
    high_relevance_pct: number;
    low_relevance_count: number;
    low_relevance_pct: number;
    status: string;
  };
  analysis: string;
  suggestions: {
    replacements: KeywordSuggestion[];
    additions: KeywordSuggestion[];
    exclusions: KeywordSuggestion[];
  };
  confidence: number;
  sample_low_relevance_articles?: LowRelevanceArticle[];
  sample_low_relevance_titles: string[];
  analyzed_at: string;
  // Error case
  error?: string;
  status?: string;
  message?: string;
}

export async function getKeywordSuggestions(
  keywordId: number,
  groupId: number,
  model: string = 'gpt-4o-mini'
): Promise<KeywordSuggestionResult> {
  return fetchJson(`${API_BASE}/keyword/${keywordId}/suggest-improvements?group_id=${groupId}&model=${model}`);
}

export interface ApplySuggestionRequest {
  suggestion_type: 'replace' | 'add' | 'exclude';
  suggested_keyword: string;
  reason?: string;
}

export interface ApplySuggestionResult {
  success: boolean;
  message: string;
  applied_keyword?: string;
  error?: string;
}

export async function applyKeywordSuggestion(
  keywordId: number,
  groupId: number,
  suggestion: ApplySuggestionRequest
): Promise<ApplySuggestionResult> {
  return fetchJson(`${API_BASE}/keyword/${keywordId}/apply-suggestion?group_id=${groupId}`, {
    method: 'POST',
    body: JSON.stringify(suggestion),
  });
}

// ============================================================================
// Job Status / Processing Status
// ============================================================================

export interface ActiveJob {
  job_id: string;
  job_type: string;
  topic_id: string;
  status: string;
  progress: number;
  started_at: string | null;
  completed_at: string | null;
  article_count?: number;
}

export interface ActiveJobsStatus {
  success: boolean;
  total_active: number;
  total_jobs: number;
  active_jobs: ActiveJob[];
}

export async function getActiveJobsStatus(): Promise<ActiveJobsStatus> {
  return fetchJson(`${API_BASE}/active-jobs-status`);
}

// ============================================================================
// Notifications
// ============================================================================

export interface Notification {
  id: number;
  type: string;
  title: string;
  message: string;
  link?: string;
  created_at: string;
  read: boolean;
}

export interface NotificationsResponse {
  notifications: Notification[];
  count: number;
}

export interface UnreadCountResponse {
  count: number;
}

export async function getNotifications(limit: number = 20): Promise<NotificationsResponse> {
  const response = await fetch(`/api/notifications?limit=${limit}`, {
    credentials: 'same-origin',
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

export async function getUnreadNotificationCount(): Promise<UnreadCountResponse> {
  const response = await fetch('/api/notifications/unread-count', {
    credentials: 'same-origin',
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

export async function markNotificationRead(notificationId: number): Promise<{ success: boolean }> {
  const response = await fetch(`/api/notifications/${notificationId}/mark-read`, {
    method: 'POST',
    credentials: 'same-origin',
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

export async function markAllNotificationsRead(): Promise<{ success: boolean }> {
  const response = await fetch('/api/notifications/mark-all-read', {
    method: 'POST',
    credentials: 'same-origin',
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

// ============================================================================
// RSS Feeds
// ============================================================================

const RSS_API_BASE = '/api/rss-feeds';

export interface RSSFeed {
  id: number;
  name: string;
  url: string;
  topic: string;
  description?: string;
  is_active: boolean;
  check_interval: number;
  interval_unit: string;
  relevance_threshold: number;  // 0 = skip filtering, 1-100 = threshold %
  default_factual_reporting?: string;  // 'very high', 'high', 'mostly factual', 'mixed', 'low', 'very low'
  last_checked_at?: string;
  last_article_date?: string;
  articles_fetched: number;
  articles_enriched: number;
  last_error?: string;
  created_at: string;
  updated_at: string;
}

export interface RSSFeedCreate {
  name: string;
  url: string;
  topic: string;
  description?: string;
  is_active?: boolean;
  check_interval?: number;
  interval_unit?: string;
  relevance_threshold?: number;
  default_factual_reporting?: string;
}

export interface RSSFeedUpdate {
  name?: string;
  url?: string;
  topic?: string;
  description?: string;
  is_active?: boolean;
  check_interval?: number;
  interval_unit?: string;
  relevance_threshold?: number;
  default_factual_reporting?: string;
}

export interface RSSFeedTestResult {
  valid: boolean;
  title?: string;
  description?: string;
  entry_count?: number;
  feed_type?: string;
  error?: string;
}

export interface RSSMonitorStatus {
  is_running: boolean;
  last_check_time?: string;
  next_check_time?: string;
  feeds_checked: number;
  articles_fetched: number;
  last_error?: string;
  active_feeds: number;
  total_feeds: number;
}

// List all RSS feeds
export async function getRSSFeeds(topic?: string, isActive?: boolean): Promise<RSSFeed[]> {
  const params = new URLSearchParams();
  if (topic) params.set('topic', topic);
  if (isActive !== undefined) params.set('is_active', String(isActive));

  const url = params.toString() ? `${RSS_API_BASE}?${params}` : RSS_API_BASE;
  const response = await fetchJson<{ success: boolean; feeds: RSSFeed[] }>(url);
  return response?.feeds || [];
}

// Get a single RSS feed
export async function getRSSFeed(feedId: number): Promise<RSSFeed> {
  const response = await fetchJson<{ success: boolean; feed: RSSFeed }>(`${RSS_API_BASE}/${feedId}`);
  return response.feed;
}

// Create a new RSS feed
export async function createRSSFeed(feed: RSSFeedCreate): Promise<{ success: boolean; feed_id: number; feed_info: RSSFeedTestResult }> {
  return fetchJson(`${RSS_API_BASE}`, {
    method: 'POST',
    body: JSON.stringify(feed),
  });
}

// Update an RSS feed
export async function updateRSSFeed(feedId: number, updates: RSSFeedUpdate): Promise<{ success: boolean }> {
  return fetchJson(`${RSS_API_BASE}/${feedId}`, {
    method: 'PUT',
    body: JSON.stringify(updates),
  });
}

// Delete an RSS feed
export async function deleteRSSFeed(feedId: number): Promise<{ success: boolean }> {
  return fetchJson(`${RSS_API_BASE}/${feedId}`, {
    method: 'DELETE',
  });
}

// Test a feed URL
export async function testRSSFeedUrl(url: string): Promise<RSSFeedTestResult> {
  const response = await fetchJson<{ success: boolean; test_result: RSSFeedTestResult }>(`${RSS_API_BASE}/test-url`, {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
  return response.test_result;
}

// Trigger fetch for a specific feed
export async function fetchRSSFeed(feedId: number): Promise<{ success: boolean; message: string }> {
  return fetchJson(`${RSS_API_BASE}/${feedId}/fetch`, {
    method: 'POST',
  });
}

// Get RSS monitor status
export async function getRSSMonitorStatus(): Promise<RSSMonitorStatus> {
  const response = await fetchJson<{ success: boolean; status: RSSMonitorStatus }>(`${RSS_API_BASE}/status/monitor`);
  return response.status;
}
