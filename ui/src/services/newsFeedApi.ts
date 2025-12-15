/**
 * News Feed API Service
 * Handles all API calls for the news feed functionality
 */

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

  return response.json();
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
