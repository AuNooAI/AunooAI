/**
 * API Service Layer for Trend Convergence Analysis
 * Connects React frontend to FastAPI backend
 */

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
      window.location.href = '/login';
      throw new Error('Authentication required');
    }

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
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
  analysis_depth?: string;
  sample_size_mode?: string;
  custom_limit?: number;
  consistency_mode?: string;
  enable_caching?: boolean;
  cache_duration_hours?: number;
  profile_id?: number;
  tab?: string;  // Specific tab to generate: consensus, strategic, signals, timeline, horizons
}): Promise<TrendConvergenceData> {
  const queryParams = new URLSearchParams();

  // Required params
  queryParams.append('model', params.model);

  // Optional params with defaults
  queryParams.append('timeframe_days', String(params.timeframe_days || 365));
  queryParams.append('analysis_depth', params.analysis_depth || 'standard');
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

  const url = `${API_BASE_URL}/api/trend-convergence/${encodeURIComponent(params.topic)}?${queryParams}`;

  return fetchWithAuth<TrendConvergenceData>(url);
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
 * Get available AI models
 */
export async function getAvailableModels(): Promise<AIModel[]> {
  try {
    // Use the main available_models endpoint like other templates
    const models = await fetchWithAuth<Array<{name: string; provider: string}>>(`${API_BASE_URL}/api/available_models`);

    // Transform to AIModel format with context limits
    const contextLimits: Record<string, number> = {
      'gpt-3.5-turbo': 16385,
      'gpt-4': 8192,
      'gpt-4-turbo': 128000,
      'gpt-4o': 128000,
      'gpt-4o-mini': 128000,
      'gpt-4.1': 1000000,
      'gpt-4.1-mini': 1000000,
      'gpt-4.1-nano': 1000000,
      'claude-3-opus': 200000,
      'claude-3-sonnet': 200000,
      'claude-3-haiku': 200000,
      'claude-3.5-sonnet': 200000,
      'claude-4': 200000,
      'gemini-pro': 32768,
      'gemini-1.5-pro': 2097152,
      'default': 128000
    };

    return models.map(model => ({
      id: model.name,
      name: `${model.name} (${model.provider})`,
      context_limit: contextLimits[model.name] || contextLimits.default
    }));
  } catch (error) {
    console.error('Error fetching models:', error);
    // Return fallback models
    return [
      { id: 'gpt-4o-mini', name: 'GPT-4o Mini (openai)', context_limit: 128000 },
      { id: 'gpt-4.1-mini', name: 'GPT-4.1 Mini (openai)', context_limit: 1000000 },
      { id: 'claude-3.5-sonnet', name: 'Claude 3.5 Sonnet (anthropic)', context_limit: 200000 },
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
