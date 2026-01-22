/**
 * News Feed API Service
 * Handles all API calls for the news feed functionality
 */

import { extractErrorMessage } from './api';

// Types matching backend schemas
export type BiasRating = 'left' | 'left-center' | 'center' | 'right-center' | 'right' | 'mixed';
export type FactualityRating = 'very-high' | 'high' | 'mostly-factual' | 'mixed' | 'low' | 'very-low';
export type DateRange = '24h' | '7d' | '30d' | '3m' | '1y' | 'all';
export type Persona = 'CEO' | 'CMO' | 'CTO' | 'CISO';

export interface ArticleSource {
  name: string;
  bias?: BiasRating;
  factuality?: FactualityRating;
  credibility_rating?: string;
  country?: string;
}

export interface NewsArticle {
  uri: string;
  title: string;
  summary: string;
  url?: string;
  publication_date?: string;
  source: ArticleSource;
  sentiment?: string;
  category?: string;
  topic?: string;
  time_to_impact?: string;
  future_signal?: string;
  tags: string[];
}

export interface RelatedArticle {
  title: string;
  source: string;
  url?: string;
  bias?: BiasRating;
  summary: string;
  similarity_score?: number;
}

// Clustered article types
export interface ClusteredArticle {
  uri: string;
  title: string;
  summary: string;
  news_source: string;
  publication_date?: string;
  category?: string;
  topic?: string;
  sentiment?: string;
  time_to_impact?: string;
  tags?: string[];
  bias?: string;
  factual_reporting?: string;
  mbfc_credibility_rating?: string;
}

export interface ClusterRelatedArticle {
  uri: string;
  title: string;
  summary?: string;
  news_source: string;
  publication_date?: string;
  similarity_score: number;
  bias?: string;
  factual_reporting?: string;
}

export interface ArticleCluster {
  primary: ClusteredArticle;
  related: ClusterRelatedArticle[];
  article_count: number;
}

export interface ClusteredArticlesResponse {
  clusters: ArticleCluster[];
  total_articles: number;
  total_clusters: number;
}

export interface TopStory {
  headline: string;
  title: string;
  summary: string;
  primary_article: NewsArticle;
  related_articles: RelatedArticle[];
  topic_description: string;
  bias_analysis: Record<string, any>;
  factuality_assessment: string;
  perspective_breakdown: Record<string, string[]>;
  // Executive briefing fields
  executive_takeaway?: string;
  strategic_relevance?: string;
  time_horizon?: 'Immediate' | 'Medium' | 'Long-term' | string;
  risk_opportunity?: 'risk' | 'opportunity' | 'mixed' | string;
  signal_strength?: 'weak' | 'moderate' | 'strong' | string;
  executive_action?: string[];
  category?: string;
  date?: string;
  url?: string;
  uri?: string;  // Article URL (may be returned as uri from API)
  source?: string;
  scores?: {
    overall?: number;
    relevance?: number;
    impact?: number;
    actionability?: number;
    timeliness?: number;
    credibility?: number;
  };
}

export interface SixArticlesReport {
  date: string;
  title: string;
  articles: TopStory[];
  generated_at: string;
  executive_summary: string;
  key_themes: string[];
  bias_distribution: Record<string, number>;
  factuality_overview: Record<string, number>;
}

export interface AvailableDate {
  date: string;
  article_count: number;
}

// Backend article format (flat structure)
interface BackendArticle {
  uri: string;
  title: string;
  summary: string;
  news_source?: string;
  publication_date?: string;
  category?: string;
  topic?: string;
  sentiment?: string;
  time_to_impact?: string;
  future_signal?: string;
  tags?: string | string[];
  url?: string;
  bias?: string;
  factual_reporting?: string;
  mbfc_credibility_rating?: string;
  bias_country?: string;
}

// Backend returns: { "articles": { "items": [...], "total_items": N, ... } }
export interface ArticlesApiResponse {
  articles: {
    items: BackendArticle[];
    total_items: number;
    total_articles: number;
    page: number;
    per_page: number;
    total_pages: number;
    date: string;
  };
}

/**
 * Transform backend article to frontend format
 */
function transformArticle(backendArticle: BackendArticle): NewsArticle {
  // Parse tags if it's a string
  let tags: string[] = [];
  if (backendArticle.tags) {
    if (Array.isArray(backendArticle.tags)) {
      tags = backendArticle.tags;
    } else if (typeof backendArticle.tags === 'string') {
      tags = backendArticle.tags.split(',').map(t => t.trim()).filter(Boolean);
    }
  }

  return {
    uri: backendArticle.uri,
    title: backendArticle.title,
    summary: backendArticle.summary,
    url: backendArticle.url,
    publication_date: backendArticle.publication_date,
    source: {
      name: backendArticle.news_source || 'Unknown Source',
      bias: backendArticle.bias as BiasRating | undefined,
      factuality: backendArticle.factual_reporting as FactualityRating | undefined,
      credibility_rating: backendArticle.mbfc_credibility_rating,
      country: backendArticle.bias_country,
    },
    sentiment: backendArticle.sentiment,
    category: backendArticle.category,
    topic: backendArticle.topic,
    time_to_impact: backendArticle.time_to_impact,
    future_signal: backendArticle.future_signal,
    tags,
  };
}

export interface ArticlesResponse {
  articles: NewsArticle[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface SixArticlesConfig {
  systemPrompt?: string;
  personas?: Record<string, {
    priorities: string;
    riskAppetite: string;
    focus: string;
  }>;
  formatSpec?: string;
}

export interface ArticleParams {
  dateRange?: DateRange;
  customDateStart?: string;
  customDateEnd?: string;
  topic?: string;
  maxArticles?: number;
  page?: number;
  perPage?: number;
  profileId?: number;
  biasFilter?: string;
  starredArticles?: string[];
}

export interface SixArticlesParams {
  dateRange?: DateRange;
  topic?: string;
  maxArticles?: number;
  profileId?: number;
  persona?: Persona;
  articleCount?: number;
  forceRegenerate?: boolean;
  starredArticles?: string[];
  model?: string;
}

// Utility Functions

/**
 * Extract URL from article data, checking multiple possible field names
 * API may return url or uri depending on the endpoint
 */
export function extractArticleUrl(data: Record<string, unknown> | null | undefined): string {
  if (!data) return '';
  return (
    (data.url as string) ||
    (data.uri as string) ||
    ((data.primary_article as Record<string, unknown>)?.url as string) ||
    ((data.primary_article as Record<string, unknown>)?.uri as string) ||
    ''
  );
}

/**
 * Convert a value to an array, handling undefined/null and single values
 */
export function toArray<T>(value: T | T[] | undefined | null): T[] {
  if (!value) return [];
  return Array.isArray(value) ? value : [value];
}

// API Functions

/**
 * Get available dates with article counts
 * Backend returns: { "success": true, "dates": [...] }
 */
export async function getAvailableDates(): Promise<AvailableDate[]> {
  const response = await fetch('/api/news-feed/available-dates', {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch available dates: ${response.status}`);
  }

  const data = await response.json();
  // Handle wrapped response format
  if (data.dates && Array.isArray(data.dates)) {
    return data.dates.map((d: any) => ({
      date: d.date,
      article_count: d.count || d.article_count || 0
    }));
  }
  // If it's already an array, return as-is
  if (Array.isArray(data)) {
    return data;
  }
  return [];
}

/**
 * Get paginated articles with filtering
 * Backend returns: { "articles": { "items": [...], "total_items": N, ... } }
 */
export async function getNewsFeedArticles(params: ArticleParams): Promise<ArticlesResponse> {
  const queryParams = new URLSearchParams();

  if (params.dateRange) queryParams.append('date_range', params.dateRange);
  if (params.customDateStart) queryParams.append('date', params.customDateStart);
  if (params.topic) queryParams.append('topic', params.topic);
  if (params.maxArticles) queryParams.append('max_articles', params.maxArticles.toString());
  if (params.page) queryParams.append('page', params.page.toString());
  if (params.perPage) queryParams.append('per_page', params.perPage.toString());
  if (params.profileId) queryParams.append('profile_id', params.profileId.toString());
  if (params.biasFilter) queryParams.append('bias_filter', params.biasFilter);
  if (params.starredArticles?.length) {
    queryParams.append('starred_articles', params.starredArticles.join(','));
  }

  const response = await fetch(`/api/news-feed/articles?${queryParams}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch articles: ${response.status}`);
  }

  const data: ArticlesApiResponse = await response.json();

  // Transform from backend format to our format
  const articlesData = data.articles || { items: [], total_items: 0, page: 1, per_page: 20, total_pages: 0 };

  // Transform each article to the frontend format
  const transformedArticles = (articlesData.items || []).map(transformArticle);

  return {
    articles: transformedArticles,
    total: articlesData.total_items || articlesData.total_articles || 0,
    page: articlesData.page || 1,
    per_page: articlesData.per_page || 20,
    total_pages: articlesData.total_pages || 0,
  };
}

/**
 * Get AI-generated six articles briefing
 */
export async function getSixArticles(params: SixArticlesParams): Promise<SixArticlesReport> {
  const queryParams = new URLSearchParams();

  if (params.dateRange) queryParams.append('date_range', params.dateRange);
  if (params.topic) queryParams.append('topic', params.topic);
  if (params.maxArticles) queryParams.append('max_articles', params.maxArticles.toString());
  if (params.profileId) queryParams.append('profile_id', params.profileId.toString());
  if (params.persona) queryParams.append('persona', params.persona);
  if (params.articleCount) queryParams.append('article_count', params.articleCount.toString());
  if (params.forceRegenerate) queryParams.append('force_regenerate', 'true');
  if (params.starredArticles?.length) {
    queryParams.append('starred_articles', params.starredArticles.join(','));
  }
  if (params.model) queryParams.append('model', params.model);

  const response = await fetch(`/api/news-feed/six-articles?${queryParams}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch six articles: ${response.status}`);
  }

  const data = await response.json();

  // API returns {six_articles: [...]} but we expect {articles: [...]}
  // Map the response to match our SixArticlesReport interface
  return {
    date: data.date || new Date().toISOString().split('T')[0],
    title: data.title || 'Executive Briefing',
    articles: data.six_articles || data.articles || [],
    generated_at: data.generated_at || new Date().toISOString(),
    executive_summary: data.executive_summary || '',
    key_themes: data.key_themes || [],
    bias_distribution: data.bias_distribution || {},
    factuality_overview: data.factuality_overview || {},
  };
}

/**
 * Get user's six articles configuration
 */
export async function getSixArticlesConfig(): Promise<SixArticlesConfig> {
  const response = await fetch('/api/news-feed/six-articles/config', {
    credentials: 'include',
  });

  if (!response.ok) {
    // Return empty config if not found
    if (response.status === 404) {
      return {};
    }
    throw new Error(`Failed to fetch config: ${response.status}`);
  }

  return response.json();
}

/**
 * Save user's six articles configuration
 */
export async function saveSixArticlesConfig(config: SixArticlesConfig): Promise<void> {
  const response = await fetch('/api/news-feed/six-articles/config', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
    body: JSON.stringify(config),
  });

  if (!response.ok) {
    throw new Error(`Failed to save config: ${response.status}`);
  }
}

/**
 * Dashboard snapshot response from auto-generation
 */
export interface DashboardSnapshot {
  id: number;
  topic: string | null;
  generated_at: string;
  persona: string;
  model: string;
  briefing_articles: SixArticlesReport['articles'] | null;
  briefing_generated: boolean;
  highlights_data: unknown | null;
  highlights_generated: boolean;
  narratives_data: unknown | null;
  narratives_generated: boolean;
  articles_analyzed: number | null;
  generation_duration_seconds: number | null;
}

export interface DashboardSnapshotResponse {
  success: boolean;
  has_snapshot: boolean;
  snapshot: DashboardSnapshot | null;
  message?: string;
}

/**
 * Get the latest auto-generated dashboard snapshot
 * Returns the most recent snapshot created by the scheduler
 */
export async function getLatestDashboardSnapshot(topic?: string): Promise<DashboardSnapshotResponse> {
  const queryParams = new URLSearchParams();
  if (topic) queryParams.append('topic', topic);

  const response = await fetch(`/api/news-feed/dashboard/snapshot/latest?${queryParams}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch dashboard snapshot: ${response.status}`);
  }

  return response.json();
}

/**
 * Get category icons mapping
 */
export async function getCategoryIcons(categories?: string[]): Promise<Record<string, string>> {
  const queryParams = new URLSearchParams();
  if (categories?.length) {
    queryParams.append('categories', categories.join(','));
  }

  const response = await fetch(`/api/news-feed/category-icons?${queryParams}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch category icons: ${response.status}`);
  }

  return response.json();
}

/**
 * Get available topics
 * Backend returns: Array<{ name: string, ... }>
 */
export async function getTopics(): Promise<Array<{ name: string; description?: string }>> {
  const response = await fetch('/api/topics', {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch topics: ${response.status}`);
  }

  const data = await response.json();
  // Handle wrapped format or direct array
  if (data.topics && Array.isArray(data.topics)) {
    return data.topics;
  }
  if (Array.isArray(data)) {
    return data;
  }
  return [];
}

/**
 * Get organizational profiles
 * Backend returns: { "success": true, "profiles": [...] }
 */
export async function getOrganizationalProfiles(): Promise<Array<{
  id: number;
  name: string;
  description?: string;
  is_default?: boolean;
}>> {
  const response = await fetch('/api/organizational-profiles', {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch profiles: ${response.status}`);
  }

  const data = await response.json();
  // Handle wrapped format
  if (data.profiles && Array.isArray(data.profiles)) {
    return data.profiles;
  }
  if (Array.isArray(data)) {
    return data;
  }
  return [];
}

/**
 * Get available AI models
 */
export async function getAvailableModels(): Promise<Array<{
  id: string;
  name: string;
  provider: string;
}>> {
  const response = await fetch('/api/available_models', {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch models: ${response.status}`);
  }

  // API returns {name, provider} - add id field for Select component
  const models = await response.json() as Array<{name: string; provider: string}>;
  return models.map(m => ({ id: m.name, name: m.name, provider: m.provider }));
}

/**
 * Group articles by category
 */
export function groupArticlesByCategory(articles: NewsArticle[]): Record<string, NewsArticle[]> {
  return articles.reduce((acc, article) => {
    const category = article.category || 'General';
    if (!acc[category]) {
      acc[category] = [];
    }
    acc[category].push(article);
    return acc;
  }, {} as Record<string, NewsArticle[]>);
}

/**
 * Get unique categories from articles
 */
export function getUniqueCategories(articles: NewsArticle[]): string[] {
  const categories = new Set<string>();
  articles.forEach(article => {
    if (article.category) {
      categories.add(article.category);
    }
  });
  return Array.from(categories).sort();
}

/**
 * Get articles clustered by semantic similarity
 * Groups related articles together based on vector embedding similarity
 */
export async function getClusteredArticles(params: {
  dateRange?: DateRange;
  topic?: string;
  category?: string;
  maxArticles?: number;
  similarityThreshold?: number;
  maxClusterSize?: number;
}): Promise<ClusteredArticlesResponse> {
  const queryParams = new URLSearchParams();

  if (params.dateRange) queryParams.append('date_range', params.dateRange);
  if (params.topic) queryParams.append('topic', params.topic);
  if (params.category) queryParams.append('category', params.category);
  if (params.maxArticles) queryParams.append('max_articles', params.maxArticles.toString());
  if (params.similarityThreshold) queryParams.append('similarity_threshold', params.similarityThreshold.toString());
  if (params.maxClusterSize) queryParams.append('max_cluster_size', params.maxClusterSize.toString());

  const response = await fetch(`/api/news-feed/articles/clustered?${queryParams}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch clustered articles: ${response.status}`);
  }

  return response.json();
}

/**
 * Transform a clustered article to NewsArticle format
 */
export function clusterArticleToNewsArticle(article: ClusteredArticle): NewsArticle {
  return {
    uri: article.uri,
    title: article.title,
    summary: article.summary,
    publication_date: article.publication_date,
    source: {
      name: article.news_source,
      bias: article.bias as BiasRating | undefined,
      factuality: article.factual_reporting as FactualityRating | undefined,
      credibility_rating: article.mbfc_credibility_rating,
    },
    sentiment: article.sentiment,
    category: article.category,
    topic: article.topic,
    time_to_impact: article.time_to_impact,
    tags: article.tags || [],
  };
}

/**
 * Get full article details by URI
 * Fetches complete article data from the database
 */
export async function getArticleByUri(uri: string): Promise<NewsArticle | null> {
  try {
    const response = await fetch(`/api/article?uri=${encodeURIComponent(uri)}`, {
      credentials: 'include',
    });

    if (!response.ok) {
      console.warn(`Failed to fetch article ${uri}: ${response.status}`);
      return null;
    }

    const data = await response.json();

    // Handle case where article was found
    if (data && data.uri) {
      return transformArticle(data as BackendArticle);
    }

    // Handle raw_only or scraped status
    if (data.status === 'raw_only' || data.status === 'scraped') {
      console.warn(`Article ${uri} is not fully analyzed`);
      return null;
    }

    return null;
  } catch (error) {
    console.error(`Error fetching article ${uri}:`, error);
    return null;
  }
}

/**
 * Get true category counts from database
 * Returns total article counts per category for the given filters
 */
export async function getCategoryCounts(
  dateRange: string = '7d',
  topic?: string
): Promise<Record<string, number>> {
  try {
    const params = new URLSearchParams({ date_range: dateRange });
    if (topic) {
      params.append('topic', topic);
    }

    const response = await fetch(`/api/news-feed/category-counts?${params}`, {
      credentials: 'include',
    });

    if (!response.ok) {
      console.warn(`Failed to fetch category counts: ${response.status}`);
      return {};
    }

    const data = await response.json();
    return data.category_counts || {};
  } catch (error) {
    console.error('Error fetching category counts:', error);
    return {};
  }
}

/**
 * Get all articles for a specific category with pagination
 */
export interface CategoryArticlesResponse {
  articles: NewsArticle[];
  total_count: number;
  page: number;
  per_page: number;
  total_pages: number;
  category: string;
}

export async function getCategoryArticles(
  category: string,
  dateRange: string = '7d',
  topic?: string,
  page: number = 1,
  perPage: number = 50
): Promise<CategoryArticlesResponse> {
  try {
    const params = new URLSearchParams({
      date_range: dateRange,
      page: page.toString(),
      per_page: perPage.toString(),
    });
    if (topic) {
      params.append('topic', topic);
    }

    const response = await fetch(
      `/api/news-feed/category/${encodeURIComponent(category)}/articles?${params}`,
      { credentials: 'include' }
    );

    if (!response.ok) {
      console.warn(`Failed to fetch category articles: ${response.status}`);
      return {
        articles: [],
        total_count: 0,
        page: 1,
        per_page: perPage,
        total_pages: 0,
        category,
      };
    }

    const data = await response.json();

    // Transform articles to frontend format
    const transformedArticles = (data.articles || []).map((article: BackendArticle) =>
      transformArticle(article)
    );

    return {
      articles: transformedArticles,
      total_count: data.total_count || 0,
      page: data.page || 1,
      per_page: data.per_page || perPage,
      total_pages: data.total_pages || 0,
      category: data.category || category,
    };
  } catch (error) {
    console.error('Error fetching category articles:', error);
    return {
      articles: [],
      total_count: 0,
      page: 1,
      per_page: perPage,
      total_pages: 0,
      category,
    };
  }
}

/**
 * Record article preference (more/less like this)
 */
export async function recordArticlePreference(
  uri: string,
  preference: 'more' | 'less' | 'clear'
): Promise<{ success: boolean; message: string }> {
  const response = await fetch('/api/article-preference', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ uri, preference }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(extractErrorMessage(errorData, `Failed to record preference: ${response.status}`));
  }

  return response.json();
}

// ============================================================================
// Saved Incidents and Narratives API
// ============================================================================

export interface SavedIncident {
  name: string;
  title?: string;
  type?: string;
  significance?: string;
  description?: string;
  summary?: string;
  topic?: string;
  entities?: string[];
  timeline?: string | string[];
  organizational_relevance?: string;
  plausibility?: string;
  source_quality?: string;
  article_uris?: string[];
  articles?: any[];
  article_metadata?: any[];
  investigation_leads?: string[];
  credibility_summary?: string;
  misinfo_flags?: string[];
  _saved_id?: number;
  _saved_at?: string;
}

export interface SavedNarrative {
  name: string;
  theme_name?: string;
  description?: string;
  theme_summary?: string;
  sentiment?: string;
  confidence?: number;
  article_count?: number;
  source_count?: number;
  key_entities?: string[];
  topic?: string;
  _saved_id?: number;
  _saved_at?: string;
}

/**
 * Get all saved incidents from the database
 */
export async function getSavedIncidents(topic?: string): Promise<SavedIncident[]> {
  try {
    const params = topic ? `?topic=${encodeURIComponent(topic)}` : '';
    const response = await fetch(`/api/news-feed/saved/incidents${params}`, {
      credentials: 'include',
    });

    if (!response.ok) {
      console.warn(`Failed to fetch saved incidents: ${response.status}`);
      return [];
    }

    const data = await response.json();
    return data.incidents || [];
  } catch (error) {
    console.error('Error fetching saved incidents:', error);
    return [];
  }
}

/**
 * Save an incident to the database
 */
export async function saveIncident(incident: SavedIncident): Promise<boolean> {
  try {
    const response = await fetch('/api/news-feed/saved/incidents', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(incident),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      console.error('Failed to save incident:', error);
      return false;
    }

    return true;
  } catch (error) {
    console.error('Error saving incident:', error);
    return false;
  }
}

/**
 * Delete a saved incident from the database
 */
export async function deleteSavedIncident(incidentName: string, topic: string): Promise<boolean> {
  try {
    const params = new URLSearchParams({ topic });
    const response = await fetch(
      `/api/news-feed/saved/incidents/${encodeURIComponent(incidentName)}?${params}`,
      {
        method: 'DELETE',
        credentials: 'include',
      }
    );

    if (!response.ok) {
      console.warn(`Failed to delete incident: ${response.status}`);
      return false;
    }

    return true;
  } catch (error) {
    console.error('Error deleting incident:', error);
    return false;
  }
}

/**
 * Get all saved narratives from the database
 */
export async function getSavedNarratives(topic?: string): Promise<SavedNarrative[]> {
  try {
    const params = topic ? `?topic=${encodeURIComponent(topic)}` : '';
    const response = await fetch(`/api/news-feed/saved/narratives${params}`, {
      credentials: 'include',
    });

    if (!response.ok) {
      console.warn(`Failed to fetch saved narratives: ${response.status}`);
      return [];
    }

    const data = await response.json();
    return data.narratives || [];
  } catch (error) {
    console.error('Error fetching saved narratives:', error);
    return [];
  }
}

/**
 * Save a narrative to the database
 */
export async function saveNarrativeToDb(narrative: SavedNarrative): Promise<boolean> {
  try {
    const response = await fetch('/api/news-feed/saved/narratives', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(narrative),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      console.error('Failed to save narrative:', error);
      return false;
    }

    return true;
  } catch (error) {
    console.error('Error saving narrative:', error);
    return false;
  }
}

/**
 * Delete a saved narrative from the database
 */
export async function deleteSavedNarrative(narrativeName: string, topic?: string): Promise<boolean> {
  try {
    const params = topic ? `?topic=${encodeURIComponent(topic)}` : '';
    const response = await fetch(
      `/api/news-feed/saved/narratives/${encodeURIComponent(narrativeName)}${params}`,
      {
        method: 'DELETE',
        credentials: 'include',
      }
    );

    if (!response.ok) {
      console.warn(`Failed to delete narrative: ${response.status}`);
      return false;
    }

    return true;
  } catch (error) {
    console.error('Error deleting narrative:', error);
    return false;
  }
}

// ============================================================================
// List View API (Chronological Articles)
// ============================================================================

export interface ArticlesListParams {
  dateRange?: DateRange;
  topic?: string;
  page?: number;
  perPage?: number;
}

export interface ArticlesListResponse {
  articles: BackendArticle[];
  total_count: number;
  page: number;
  per_page: number;
  total_pages: number;
}

/**
 * Get articles as a flat list sorted by publication date (newest first)
 * Used for the "List View" in the explore page
 */
export async function getArticlesList(params: ArticlesListParams): Promise<{
  articles: NewsArticle[];
  totalCount: number;
  page: number;
  perPage: number;
  totalPages: number;
}> {
  const queryParams = new URLSearchParams();

  if (params.dateRange) queryParams.append('date_range', params.dateRange);
  if (params.topic) queryParams.append('topic', params.topic);
  if (params.page) queryParams.append('page', params.page.toString());
  if (params.perPage) queryParams.append('per_page', params.perPage.toString());

  const response = await fetch(`/api/news-feed/articles/list?${queryParams}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch articles list: ${response.status}`);
  }

  const data: ArticlesListResponse = await response.json();

  // Transform articles to frontend format
  const transformedArticles = (data.articles || []).map(transformArticle);

  return {
    articles: transformedArticles,
    totalCount: data.total_count || 0,
    page: data.page || 1,
    perPage: data.per_page || 25,
    totalPages: data.total_pages || 0,
  };
}

// Filter options types
export interface FilterOption {
  name?: string;
  level?: string;
  count: number;
}

export interface ArticleFilterOptions {
  sources: FilterOption[];
  factuality: FilterOption[];
  bias: FilterOption[];
}

/**
 * Get available filter options for article list (sources, factuality, bias)
 */
export async function getArticleFilterOptions(params: {
  dateRange?: DateRange;
  topic?: string;
}): Promise<ArticleFilterOptions> {
  const queryParams = new URLSearchParams();

  if (params.dateRange) queryParams.append('date_range', params.dateRange);
  if (params.topic) queryParams.append('topic', params.topic);

  const response = await fetch(`/api/news-feed/filter-options?${queryParams}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch filter options: ${response.status}`);
  }

  return response.json();
}

/**
 * Get configured categories for a specific topic
 */
export async function getTopicCategories(topicName: string): Promise<{
  topic: string;
  categories: string[];
}> {
  const response = await fetch(`/api/news-feed/topic/${encodeURIComponent(topicName)}/categories`, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch topic categories: ${response.status}`);
  }

  return response.json();
}
