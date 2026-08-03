/**
 * API Service Layer for Trend Convergence Analysis
 * Connects React frontend to FastAPI backend
 */

/**
 * Safely extract an error message from an API error response.
 * Handles Pydantic validation errors (array of {type, loc, msg, input}) and standard errors.
 */
export function extractErrorMessage(errorData: unknown, fallback: string = 'An error occurred'): string {
  // Handle string errors directly
  if (typeof errorData === 'string') {
    return errorData;
  }

  if (!errorData || typeof errorData !== 'object') {
    return fallback;
  }

  const data = errorData as Record<string, unknown>;

  // Handle direct Pydantic validation error object: { type, loc, msg, input }
  if ('msg' in data && 'type' in data) {
    return typeof data.msg === 'string' ? data.msg : fallback;
  }

  // Handle Pydantic validation errors: { detail: [{type, loc, msg, input}] }
  if (Array.isArray(data.detail)) {
    const messages = data.detail
      .map((err: unknown) => {
        if (typeof err === 'object' && err !== null && 'msg' in err) {
          return (err as Record<string, unknown>).msg;
        }
        if (typeof err === 'string') {
          return err;
        }
        return null;
      })
      .filter(Boolean);
    if (messages.length > 0) {
      return messages.join('; ');
    }
  }

  // Handle standard error: { detail: "message" } or { message: "message" }
  if (typeof data.detail === 'string') {
    return data.detail;
  }
  if (typeof data.message === 'string') {
    return data.message;
  }
  if (typeof data.error === 'string') {
    return data.error;
  }

  // Handle nested error object: { error: { type, loc, msg, input } }
  if (data.error && typeof data.error === 'object') {
    return extractErrorMessage(data.error, fallback);
  }

  return fallback;
}

// Types
export interface StrategicRecommendations {
  near_term: {
    timeframe: string;
    trends: Array<{
      name?: string;
      description?: string;
      rationale?: string;
    } | string>;
  };
  mid_term: {
    timeframe: string;
    trends: Array<{
      name?: string;
      description?: string;
      rationale?: string;
    } | string>;
  };
  long_term: {
    timeframe: string;
    trends: Array<{
      name?: string;
      description?: string;
      rationale?: string;
    } | string>;
  };
}

export interface ExecutiveDecisionFramework {
  principles: Array<{
    title?: string;
    name?: string;
    description?: string;
    content?: string;
    rationale?: string;
  }>;
}

// Auspex Consensus Analysis Data Structure (matches skunkworkx)
export interface AuspexConsensusType {
  summary: string;
  distribution: {
    positive: number;
    neutral: number;
    critical: number;
  };
  confidence_level: number;
}

export interface AuspexTimelineConsensus {
  distribution: { [key: string]: number };
  consensus_window: {
    start_year: number;
    end_year: number;
    label: string;
  };
}

export interface AuspexConfidenceLevel {
  majority_agreement: number;
  consensus_strength: 'Strong' | 'Moderate' | 'Emerging';
  evidence_quality: 'High' | 'Medium' | 'Low';
}

export interface AuspexOutlier {
  scenario: string;
  details: string;
  year: number;
  source_percentage: number;
  reference: string;
}

export interface AuspexKeyArticle {
  title: string;
  url: string;
  summary: string;
  sentiment: string;
  relevance_score: number;
}

export interface AuspexDecisionWindow {
  urgency: 'Critical' | 'High' | 'Medium' | 'Low';
  window: string;
  action: string;
  rationale: string;
  owner: string;
  dependencies: string[];
  success_metrics: string[];
}

export interface AuspexTimeframeAnalysis {
  immediate: string;
  short_term: string;
  mid_term: string;
  key_milestones: {
    year: number;
    milestone: string;
    significance: string;
  }[];
}

export interface AuspexConsensusCategory {
  category_name: string;
  category_description: string;
  articles_analyzed: number;
  '1_consensus_type': AuspexConsensusType;
  '2_timeline_consensus': AuspexTimelineConsensus;
  '3_confidence_level': AuspexConfidenceLevel;
  '4_optimistic_outliers': AuspexOutlier[];
  '5_pessimistic_outliers': AuspexOutlier[];
  '6_key_articles': AuspexKeyArticle[];
  '7_strategic_implications': string;
  '8_key_decision_windows': AuspexDecisionWindow[];
  '9_timeframe_analysis': AuspexTimeframeAnalysis;
}

// Legacy Convergence interface (kept for backward compatibility with other tabs)
export interface ActionItem {
  priority: 'High' | 'Medium' | 'Low';
  action: string;
  timeframe: string;
  owner: string;
  dependencies: string[];
  success_metrics: string[];
}

export interface TimeframeAnalysis {
  immediate: string;
  short_term: string;
  mid_term: string;
  key_milestones: {
    year: number;
    milestone: string;
    significance: string;
  }[];
}

export interface Convergence {
  name: string;
  description: string;
  consensus_percentage: number;
  consensus_type: string;
  timeline_start_year: number;
  timeline_end_year: number;
  timeline_consensus: string;
  sentiment_distribution: {
    positive: number;
    neutral: number;
    critical: number;
  };
  articles_analyzed: number;
  optimistic_outlier: {
    year: number;
    description: string;
    source_percentage: number;
  };
  pessimistic_outlier: {
    year: number;
    description: string;
    source_percentage: number;
  };
  strategic_implication: string;
  action_items?: ActionItem[];
  timeframe_analysis?: TimeframeAnalysis;
  key_articles: {
    title: string;
    url: string;
    summary: string;
    sentiment?: string;
  }[];
}

export interface KeyInsight {
  quote: string;
  source: string;
  relevance: string;
}

export interface TrendConvergenceData {
  topic?: string;
  // New Auspex structure (Consensus Analysis tab)
  categories?: AuspexConsensusCategory[];
  // Legacy structure (for other tabs)
  convergences?: Convergence[];
  key_insights?: KeyInsight[];
  strategic_recommendations?: StrategicRecommendations;
  executive_decision_framework?: ExecutiveDecisionFramework;
  next_steps?: string[];
  model_used?: string;
  analysis_depth?: string;
  articles_analyzed?: number;
  timestamp?: string;
}

export interface OrganizationalProfile {
  id?: number;
  name: string;
  description?: string;
  industry?: string;
  organization_type?: string;
  region?: string;
  key_concerns: string[];
  strategic_priorities: string[];
  risk_tolerance: string;
  innovation_appetite: string;
  decision_making_style: string;
  stakeholder_focus: string[];
  competitive_landscape: string[];
  regulatory_environment: string[];
  custom_context?: string;
  is_default?: boolean;
}

export interface Topic {
  name: string;
  display_name: string;
  article_count?: number;
}

export interface AIModel {
  id: string;
  name: string;
  context_limit: number;
  description?: string;
}

// ============================================================================
// Market Signals & Strategic Risks Types
// ============================================================================

export interface FutureSignal {
  signal: string;
  description: string;
  timeline: string;
  impact: string;
  confidence: string;
  key_indicators: string[];
}

export interface RiskCard {
  title: string;
  description: string;
  severity: string;
  timeframe: string;
  mitigation_strategies: string[];
}

export interface OpportunityCard {
  title: string;
  description: string;
  potential_value: string;
  timeframe: string;
  action_steps: string[];
}

export interface Quote {
  text: string;
  source: string;
  context: string;
  relevance: string;
}

export interface MarketSignalsData {
  future_signals: FutureSignal[];
  risk_cards: RiskCard[];
  opportunity_cards: OpportunityCard[];
  quotes: Quote[];
  meta: {
    topic: string;
    article_count: number;
    analyzed_count: number;
    prompt_version: string;
    generated_at: string;
    model: string;
  };
}

// API Configuration
const API_BASE_URL = ''; // Empty string means same origin (FastAPI server)

/**
 * Fetch with authentication and error handling
 */
async function fetchWithAuth<T>(
  url: string,
  options: RequestInit = {}
): Promise<T> {
  try {
    const response = await fetch(url, {
      ...options,
      credentials: 'include', // Include session cookie
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    // Handle authentication errors
    if (response.status === 401 || response.status === 403) {
      // Don't redirect for saved-dashboards endpoints (they're optional features)
      if (!url.includes('/api/saved-dashboards')) {
        window.location.href = '/login';
      }
      throw new Error('Authentication required');
    }

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(extractErrorMessage(errorData, `HTTP ${response.status}: ${response.statusText}`));
    }

    return await response.json();
  } catch (error) {
    console.error('API Error:', error);
    throw error;
  }
}

/**
 * Generate trend convergence analysis
 */
export async function generateTrendConvergence(params: {
  topic: string;
  timeframe_days?: number;
  model: string;
  source_quality?: string;
  sample_size_mode?: string;
  custom_limit?: number;
  consistency_mode?: string;
  enable_caching?: boolean;
  cache_duration_hours?: number;
  profile_id?: number;
  tab?: string;  // Specific tab to generate: consensus, strategic, signals, timeline, horizons
  custom_prompt?: string;  // Custom prompt override for tuning
}): Promise<TrendConvergenceData> {
  const queryParams = new URLSearchParams();

  // Required params
  queryParams.append('model', params.model);

  // Optional params with defaults
  queryParams.append('timeframe_days', String(params.timeframe_days || 365));
  queryParams.append('source_quality', params.source_quality || 'all');
  queryParams.append('sample_size_mode', params.sample_size_mode || 'auto');
  queryParams.append('consistency_mode', params.consistency_mode || 'balanced');
  queryParams.append('enable_caching', String(params.enable_caching !== false));
  queryParams.append('cache_duration_hours', String(params.cache_duration_hours || 24));

  if (params.custom_limit) {
    queryParams.append('custom_limit', String(params.custom_limit));
  }

  if (params.profile_id) {
    queryParams.append('profile_id', String(params.profile_id));
  }

  if (params.tab) {
    queryParams.append('tab', params.tab);
  }

  if (params.custom_prompt) {
    queryParams.append('custom_prompt', params.custom_prompt);
  }

  const url = `${API_BASE_URL}/api/trend-convergence/${encodeURIComponent(params.topic)}?${queryParams}`;

  return fetchWithAuth<TrendConvergenceData>(url);
}

/**
 * Load cached trend convergence analysis without triggering generation.
 * Returns null if no cached data exists (404).
 */
export async function loadCachedTrendConvergence(params: {
  topic: string;
  timeframe_days?: number;
  model: string;
  source_quality?: string;
  sample_size_mode?: string;
  custom_limit?: number;
  consistency_mode?: string;
  profile_id?: number;
  tab?: string;
}): Promise<TrendConvergenceData | null> {
  const queryParams = new URLSearchParams();
  queryParams.append('model', params.model);
  queryParams.append('timeframe_days', String(params.timeframe_days || 365));
  queryParams.append('source_quality', params.source_quality || 'all');
  queryParams.append('sample_size_mode', params.sample_size_mode || 'auto');
  queryParams.append('consistency_mode', params.consistency_mode || 'balanced');
  queryParams.append('cache_only', 'true');

  if (params.custom_limit) {
    queryParams.append('custom_limit', String(params.custom_limit));
  }
  if (params.profile_id) {
    queryParams.append('profile_id', String(params.profile_id));
  }
  if (params.tab) {
    queryParams.append('tab', params.tab);
  }

  const url = `${API_BASE_URL}/api/trend-convergence/${encodeURIComponent(params.topic)}?${queryParams}`;

  try {
    const response = await fetch(url, {
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
    });

    if (response.status === 401 || response.status === 403) {
      window.location.href = '/login';
      throw new Error('Authentication required');
    }

    if (response.status === 404) {
      return null;
    }

    if (!response.ok) {
      return null;
    }

    return await response.json();
  } catch (error) {
    console.error('Error loading cached analysis:', error);
    return null;
  }
}

/**
 * Get all available topics
 */
export async function getTopics(): Promise<Topic[]> {
  // The /api/topics endpoint returns a direct array, not wrapped in an object
  const topics = await fetchWithAuth<any[]>(`${API_BASE_URL}/api/topics`);
  return topics.map(topic => ({
    name: topic.name,
    display_name: topic.display_name || topic.name,
    article_count: topic.article_count
  }));
}

/**
 * Get all organizational profiles
 */
export async function getOrganizationalProfiles(): Promise<OrganizationalProfile[]> {
  const response = await fetchWithAuth<{ success: boolean; profiles: OrganizationalProfile[] }>(
    `${API_BASE_URL}/api/organizational-profiles`
  );
  return response.profiles || [];
}

/**
 * Create organizational profile
 */
export async function createOrganizationalProfile(
  profile: Omit<OrganizationalProfile, 'id'>
): Promise<{ success: boolean; profile_id: number; message: string }> {
  return fetchWithAuth(`${API_BASE_URL}/api/organizational-profiles`, {
    method: 'POST',
    body: JSON.stringify(profile),
  });
}

/**
 * Update organizational profile
 */
export async function updateOrganizationalProfile(
  profileId: number,
  profile: Partial<OrganizationalProfile>
): Promise<{ success: boolean; message: string }> {
  return fetchWithAuth(`${API_BASE_URL}/api/organizational-profiles/${profileId}`, {
    method: 'PUT',
    body: JSON.stringify(profile),
  });
}

/**
 * Delete organizational profile
 */
export async function deleteOrganizationalProfile(
  profileId: number
): Promise<{ success: boolean; message: string }> {
  return fetchWithAuth(`${API_BASE_URL}/api/organizational-profiles/${profileId}`, {
    method: 'DELETE',
  });
}

/**
 * Get single organizational profile
 */
export async function getOrganizationalProfile(
  profileId: number
): Promise<OrganizationalProfile> {
  const response = await fetchWithAuth<{ success: boolean; profile: OrganizationalProfile }>(
    `${API_BASE_URL}/api/organizational-profiles/${profileId}`
  );
  return response.profile;
}

/**
 * Get available AI models for the foresight dropdown.
 *
 * Use /api/trend-convergence/models, not /api/available_models. The latter
 * returns every litellm alias (~two dozen gpt-*, gemini-*, mixtral-*,
 * claude-*-latest), all of which collapse onto the same handful of Bedrock
 * models — so the dropdown filled with duplicates under wrong vendor names.
 * The trend-convergence endpoint returns only the distinct real models,
 * already shaped as {id, name, context_limit}.
 */
export async function getAvailableModels(): Promise<AIModel[]> {
  try {
    return await fetchWithAuth<AIModel[]>(`${API_BASE_URL}/api/trend-convergence/models`);
  } catch (error) {
    console.error('Error fetching models:', error);
    // Same list the endpoint serves, so a failed fetch does not resurrect aliases.
    return [
      { id: 'bedrock-claude-sonnet', name: 'Claude Sonnet 4.5', context_limit: 200000 },
      { id: 'bedrock-claude-haiku', name: 'Claude Haiku 4.5', context_limit: 200000 },
      { id: 'nova-pro', name: 'Nova Pro', context_limit: 300000 },
      { id: 'nova-lite', name: 'Nova Lite', context_limit: 300000 },
      { id: 'bedrock-kimi-k2-5', name: 'Kimi K2.5', context_limit: 256000 },
    ];
  }
}

/**
 * Get previous analysis for a topic
 */
export async function getPreviousAnalysis(topic: string): Promise<TrendConvergenceData> {
  return fetchWithAuth<TrendConvergenceData>(
    `${API_BASE_URL}/api/trend-convergence/${encodeURIComponent(topic)}/previous`
  );
}

// ============================================================================
// Onboarding API Functions
// ============================================================================

export interface ApiKeyValidation {
  provider: string;
  api_key: string;
}

export interface TopicSuggestion {
  futureSignals: string[];
  categories: string[];
  sentiments: string[];
  timeToImpact: string[];
  keywords: string[];
}

export interface TopicData {
  name: string;
  description?: string;
  futureSignals: string[];
  categories: string[];
  sentiments: string[];
  timeToImpact: string[];
  keywords?: string[];
}

/**
 * Validate and store API key
 */
export async function validateApiKey(data: ApiKeyValidation): Promise<{
  status: string;
  configured: boolean;
  masked_key?: string
}> {
  return fetchWithAuth(`${API_BASE_URL}/api/onboarding/validate-api-key`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * Check API keys status
 */
export async function checkApiKeys(): Promise<{
  newsapi: boolean;
  newsapi_key?: string;
  firecrawl: boolean;
  firecrawl_key?: string;
  thenewsapi: boolean;
  thenewsapi_key?: string;
  newsdata: boolean;
  newsdata_key?: string;
  openai: boolean;
  openai_key?: string;
  anthropic: boolean;
  anthropic_key?: string;
  gemini: boolean;
  gemini_key?: string;
}> {
  return fetchWithAuth(`${API_BASE_URL}/api/onboarding/check-keys`);
}

/**
 * Get AI-powered topic attribute suggestions
 */
export async function suggestTopicAttributes(data: {
  topic_name: string;
  topic_description?: string;
  keyword_prompt?: string;
}): Promise<{
  explanation: string;
  categories: string[];
  future_signals: string[];
  sentiments?: string[];
  time_to_impact?: string[];
  keywords: any;
}> {
  return fetchWithAuth(`${API_BASE_URL}/api/onboarding/suggest-topic-attributes`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * Save topic configuration
 */
export async function saveTopic(data: TopicData): Promise<{ status: string; success?: boolean; message: string; topic_id?: number }> {
  return fetchWithAuth(`${API_BASE_URL}/api/onboarding/save-topic`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * Complete onboarding process
 */
export async function completeOnboarding(): Promise<{ success: boolean; message: string }> {
  return fetchWithAuth(`${API_BASE_URL}/api/onboarding/complete`, {
    method: 'POST',
  });
}

/**
 * Reset onboarding status
 */
export async function resetOnboarding(): Promise<{ success: boolean; message: string }> {
  return fetchWithAuth(`${API_BASE_URL}/api/onboarding/reset`, {
    method: 'POST',
  });
}

// ============================================================================
// Market Signals API Functions
// ============================================================================

/**
 * Get available topics for market signals analysis
 */
export async function getMarketSignalsTopics(): Promise<{ success: boolean; topics: string[]; count: number }> {
  return fetchWithAuth(`${API_BASE_URL}/api/market-signals/topics`);
}

/**
 * Generate market signals and strategic risks analysis
 */
export async function getMarketSignals(
  topic: string,
  model: string,
  limit: number = 100,
  temperature?: number,
  max_tokens?: number
): Promise<MarketSignalsData> {
  const queryParams = new URLSearchParams();
  queryParams.append('topic', topic);  // URLSearchParams handles encoding automatically
  queryParams.append('model', model);
  queryParams.append('limit', String(limit));

  if (temperature !== undefined) {
    queryParams.append('temperature', String(temperature));
  }
  if (max_tokens !== undefined) {
    queryParams.append('max_tokens', String(max_tokens));
  }

  const url = `${API_BASE_URL}/api/market-signals/analysis?${queryParams}`;
  return fetchWithAuth<MarketSignalsData>(url);
}

/**
 * Retrieve stored market signals analysis by ID
 */
export async function getMarketSignalsRaw(analysisId: string): Promise<any> {
  const url = `${API_BASE_URL}/api/market-signals/${analysisId}/raw`;
  return fetchWithAuth(url);
}

/**
 * Retrieve stored impact timeline analysis by ID
 */
export async function getImpactTimelineRaw(analysisId: string): Promise<any> {
  const url = `${API_BASE_URL}/api/trend-convergence/timeline/${analysisId}/raw`;
  return fetchWithAuth(url);
}

/**
 * Retrieve stored strategic recommendations analysis by ID
 */
export async function getStrategicRecommendationsRaw(analysisId: string): Promise<any> {
  const url = `${API_BASE_URL}/api/trend-convergence/strategic/${analysisId}/raw`;
  return fetchWithAuth(url);
}

/**
 * Retrieve stored future horizons analysis by ID
 */
export async function getFutureHorizonsRaw(analysisId: string): Promise<any> {
  const url = `${API_BASE_URL}/api/trend-convergence/horizons/${analysisId}/raw`;
  return fetchWithAuth(url);
}

/**
 * Generate an executive summary for a Future Horizons analysis
 * @param analysisId - The ID of the horizons analysis
 * @param scenarios - Array of scenarios (h1, h2, h3) from the horizons analysis
 * @param topic - The research topic
 * @param model - Optional AI model to use (default: gpt-4o)
 * @param profileId - Optional organizational profile ID
 */
export async function generateHorizonsExecutiveSummary(
  analysisId: string,
  scenarios: any[],
  topic: string,
  model: string = 'gpt-4o',
  profileId?: number
): Promise<any> {
  const url = `${API_BASE_URL}/api/trend-convergence/horizons/${analysisId}/executive-summary`;
  return fetchWithAuth(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      scenarios,
      topic,
      model,
      profile_id: profileId
    }),
  });
}

/**
 * Retrieve a cached executive summary for a Future Horizons analysis
 * @param analysisId - The ID of the horizons analysis
 * @returns The executive summary data or null if not generated yet
 */
export async function getHorizonsExecutiveSummary(analysisId: string): Promise<any> {
  const url = `${API_BASE_URL}/api/trend-convergence/horizons/${analysisId}/executive-summary`;
  return fetchWithAuth(url);
}

/**
 * Retrieve stored consensus analysis by ID with article list
 */
export async function getConsensusAnalysisRaw(analysisId: string): Promise<any> {
  const url = `${API_BASE_URL}/api/trend-convergence/consensus/${analysisId}/raw`;
  return fetchWithAuth(url);
}

// ==================== Saved Dashboards API ====================

export interface SavedDashboardSummary {
  id: number;
  name: string;
  description?: string;
  created_at: string;
  updated_at: string;
  last_accessed_at: string;
  articles_analyzed?: number;
  model_used?: string;
}

export interface SavedDashboardFull extends SavedDashboardSummary {
  topic: string;
  config: AnalysisConfig;
  article_uris: string[];
  consensus_data?: TrendConvergenceData;
  strategic_data?: TrendConvergenceData;
  timeline_data?: TrendConvergenceData;
  signals_data?: any;
  horizons_data?: TrendConvergenceData;
  profile_snapshot?: OrganizationalProfile;
}

export interface SaveDashboardRequest {
  topic: string;
  name: string;
  description?: string;
  config: AnalysisConfig;
  article_uris: string[];
  tab_data: {
    consensus?: TrendConvergenceData;
    strategic?: TrendConvergenceData;
    timeline?: TrendConvergenceData;
    signals?: any;
    horizons?: TrendConvergenceData;
  };
  profile_snapshot?: OrganizationalProfile;
}

/**
 * Save current dashboard state with all tab data
 */
export async function saveDashboard(request: SaveDashboardRequest): Promise<any> {
  const url = `${API_BASE_URL}/api/saved-dashboards/save`;
  return fetchWithAuth(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
}

/**
 * List all saved dashboards for a topic
 */
export async function listDashboardsForTopic(topic: string): Promise<SavedDashboardSummary[]> {
  const url = `${API_BASE_URL}/api/saved-dashboards/topic/${encodeURIComponent(topic)}`;
  return fetchWithAuth(url);
}

/**
 * Load a specific saved dashboard with all data
 */
export async function loadDashboard(dashboardId: number): Promise<SavedDashboardFull> {
  const url = `${API_BASE_URL}/api/saved-dashboards/${dashboardId}`;
  return fetchWithAuth(url);
}

/**
 * Update saved dashboard metadata or cached data
 */
export async function updateDashboard(
  dashboardId: number,
  updates: { name?: string; description?: string; tab_data?: any }
): Promise<any> {
  const url = `${API_BASE_URL}/api/saved-dashboards/${dashboardId}`;
  return fetchWithAuth(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
}

/**
 * Delete a saved dashboard
 */
export async function deleteDashboard(dashboardId: number): Promise<any> {
  const url = `${API_BASE_URL}/api/saved-dashboards/${dashboardId}`;
  return fetchWithAuth(url, {
    method: 'DELETE',
  });
}

/**
 * Get recently accessed dashboards across all topics
 */
export async function getRecentDashboards(limit = 10): Promise<SavedDashboardSummary[]> {
  const url = `${API_BASE_URL}/api/saved-dashboards/recent/list?limit=${limit}`;
  return fetchWithAuth(url);
}

/**
 * Search saved dashboards using full-text search
 */
export async function searchDashboards(query: string): Promise<SavedDashboardSummary[]> {
  const url = `${API_BASE_URL}/api/saved-dashboards/search?q=${encodeURIComponent(query)}`;
  return fetchWithAuth(url);
}

/**
 * Get aggregate dashboard statistics for current user
 */
export async function getDashboardStats(): Promise<any> {
  const url = `${API_BASE_URL}/api/saved-dashboards/stats`;
  return fetchWithAuth(url);
}

/**
 * Clone an existing dashboard with a new name
 */
export async function cloneDashboard(dashboardId: number, newName: string): Promise<any> {
  const url = `${API_BASE_URL}/api/saved-dashboards/${dashboardId}/clone?new_name=${encodeURIComponent(newName)}`;
  return fetchWithAuth(url, {
    method: 'POST',
  });
}

// ============================================================================
// Strategic Intelligence Oracle (SIO) API Functions
// ============================================================================

export interface SIOScanRequest {
  topic?: string;
  hours_back?: number;
  max_events?: number;
  credibility_threshold?: number;
  profile_id?: number;
  stream?: boolean;
}

export interface SIOEventCluster {
  cluster_id: string;
  title: string;
  summary: string;
  category: string;
  article_count: number;
  source_diversity_score: number;
  preliminary_importance: 'critical' | 'high' | 'medium' | 'low';
  final_importance_score: number;
  keywords: string[];
  analysis?: {
    key_facts: Array<{ fact: string; sources_count?: number; importance?: string }>;
    key_entities: Array<{ name: string; type: string; role: string }>;
    confidence_score: number;
    quality_gates: {
      accuracy_passed: boolean;
      context_passed: boolean;
      sourcing_passed: boolean;
      all_passed: boolean;
      issues: string[];
    };
    impact_assessment: {
      urgency_score: number;
      scale_score: number;
      consequence_score: number;
      overall_importance: number;
      strategic_category: string;
    };
    cross_references: Array<{ title: string; source: string; url?: string }>;
    contradictions: Array<{ topic: string; source_a: string; source_b: string; severity: string }>;
  };
}

export interface SIOScanProgress {
  stage: 'discovery' | 'triage' | 'deep_analysis' | 'synthesis' | 'complete' | 'error';
  status: string;
  progress: number;
  scan_id?: string;
  articles_collected?: number;
  articles_screened?: number;
  events_identified?: number;
  events_analyzed?: number;
  current_event?: string;
  chunk?: string;
  brief?: string;
  metadata?: {
    articles_collected: number;
    articles_screened: number;
    events_identified: number;
    events_analyzed: number;
    duration_seconds: number;
  };
  audit_trail?: any;
  error?: string;
}

export interface SIOArticle {
  id: number;
  title: string;
  uri: string;
  source: string;
  published_at?: string;
  credibility_score?: number;
  summary?: string;
}

export interface SIOBriefData {
  scan_id: string;
  brief: string;
  metadata: {
    articles_collected: number;
    articles_screened: number;
    events_identified: number;
    events_analyzed: number;
    duration_seconds: number;
    generated_at?: string;
  };
  articles?: SIOArticle[];
  audit_trail: any;
  events?: SIOEventCluster[];
}

export interface AnalyzeUrlRequest {
  url: string;
  topic?: string;
  deep_verification?: boolean;
}

export interface ArticleAnalysis {
  analysis_id: string;
  url: string;
  analysis: {
    title: string;
    summary: string;
    key_facts: Array<{ fact: string; type?: string; importance?: string }>;
    key_entities: Array<{ name: string; type: string; role: string }>;
    verification: {
      results: Array<{
        claim: string;
        verified: boolean;
        confidence: number;
        supporting_sources: string[];
        contradicting_sources: string[];
        notes: string;
      }>;
      cross_references: Array<{ title: string; source: string; url?: string }>;
      contradictions: Array<{ topic: string; severity: string }>;
    };
    source: {
      credibility: { rating?: string; score?: number };
      bias?: string;
    };
    confidence_score: number;
    impact_assessment: {
      urgency_score: number;
      scale_score: number;
      consequence_score: number;
      overall_importance: number;
      strategic_category: string;
    };
    quality_gates: {
      accuracy_passed: boolean;
      context_passed: boolean;
      sourcing_passed: boolean;
      all_passed: boolean;
      issues: string[];
    };
  };
}

/**
 * Start a Strategic Intelligence Oracle scan with streaming
 * Returns an EventSource for SSE streaming
 */
export function startSIOScanStream(
  params: SIOScanRequest,
  onProgress: (data: SIOScanProgress) => void,
  onComplete: (data: SIOBriefData) => void,
  onError: (error: string) => void
): () => void {
  const controller = new AbortController();

  const runStream = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/sio/scan`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ ...params, stream: true }),
        signal: controller.signal,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(extractErrorMessage(errorData, `HTTP ${response.status}`));
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6)) as SIOScanProgress;

              if (data.stage === 'complete') {
                onComplete({
                  scan_id: data.scan_id || '',
                  brief: data.brief || '',
                  metadata: data.metadata || {
                    articles_collected: 0,
                    articles_screened: 0,
                    events_identified: 0,
                    events_analyzed: 0,
                    duration_seconds: 0,
                  },
                  articles: (data as any).articles || [],
                  audit_trail: data.audit_trail,
                });
              } else if (data.stage === 'error') {
                onError(extractErrorMessage(data.error, 'Unknown error'));
              } else {
                onProgress(data);
              }
            } catch (e) {
              console.error('Error parsing SSE data:', e);
            }
          }
        }
      }
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        onError((error as Error).message);
      }
    }
  };

  runStream();

  // Return cleanup function
  return () => controller.abort();
}

/**
 * Start a SIO scan without streaming (waits for completion)
 */
export async function startSIOScan(params: SIOScanRequest): Promise<SIOBriefData> {
  const response = await fetchWithAuth<{
    success: boolean;
    scan_id: string;
    brief: string;
    metadata: any;
    audit_trail: any;
  }>(`${API_BASE_URL}/api/sio/scan`, {
    method: 'POST',
    body: JSON.stringify({ ...params, stream: false }),
  });

  return {
    scan_id: response.scan_id,
    brief: response.brief,
    metadata: response.metadata,
    audit_trail: response.audit_trail,
  };
}

/**
 * Analyze a single URL with deep verification
 */
export async function analyzeSIOUrl(request: AnalyzeUrlRequest): Promise<ArticleAnalysis> {
  return fetchWithAuth<ArticleAnalysis>(`${API_BASE_URL}/api/sio/analyze-url`, {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

/**
 * Get SIO service health status
 */
export async function getSIOHealth(): Promise<{ status: string; version: string; components: any }> {
  return fetchWithAuth(`${API_BASE_URL}/api/sio/health`);
}

/**
 * Get a specific SIO scan by ID
 */
export async function getSIOScan(scanId: string): Promise<any> {
  return fetchWithAuth(`${API_BASE_URL}/api/sio/scan/${scanId}`);
}

/**
 * Get just the brief from a scan
 */
export async function getSIOBrief(scanId: string): Promise<{ brief: string }> {
  return fetchWithAuth(`${API_BASE_URL}/api/sio/scan/${scanId}/brief`);
}

/**
 * List recent SIO scans
 */
export async function listSIOScans(params?: {
  page?: number;
  per_page?: number;
  topic?: string;
  status?: string;
}): Promise<{ scans: any[]; total: number; page: number; per_page: number }> {
  const queryParams = new URLSearchParams();
  if (params?.page) queryParams.append('page', String(params.page));
  if (params?.per_page) queryParams.append('per_page', String(params.per_page));
  if (params?.topic) queryParams.append('topic', params.topic);
  if (params?.status) queryParams.append('status', params.status);

  return fetchWithAuth(`${API_BASE_URL}/api/sio/scans?${queryParams}`);
}
