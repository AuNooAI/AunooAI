/**
 * Narrative Explorer API Service
 * Handles Highlights (incident tracking) and Narratives (article insights)
 */

import { extractErrorMessage } from './api';

// Types for Incident Tracking (Highlights)
export type IncidentType = 'incident' | 'entity' | 'expertise' | 'informed_insider' | 'trend_signal' | 'strategic_shift' | 'event';
export type IncidentSignificance = 'high' | 'medium' | 'low';
export type IncidentStatus = 'active' | 'seen' | 'saved' | 'deleted';
export type Plausibility = 'likely' | 'questionable' | 'implausible';
export type SourceQuality = 'high' | 'mixed' | 'low';

export interface IncidentArticleMetadata {
  title: string;
  news_source: string;
  uri?: string;
  factual_reporting?: string;
  mbfc_credibility_rating?: string;
  bias?: string;
  tags?: string[];
}

export interface IncidentArticle {
  uri: string;
  title: string;
  source: string;
  date?: string;
  relevance_score?: number;
  // MBFC quality indicators
  factual_reporting?: string;
  mbfc_credibility_rating?: string;
  bias?: string;
}

export interface Incident {
  id: string;
  name: string;  // Primary display name
  title?: string;  // Alias for name
  description: string;  // Primary description
  summary?: string;  // Alias for description

  // Classification
  type: IncidentType;
  category?: string;  // Legacy field
  significance: IncidentSignificance;
  severity?: 'critical' | 'high' | 'medium' | 'low';  // Legacy field
  status?: IncidentStatus;
  topic?: string;

  // Organizational context
  organizational_relevance?: string;
  credibility_summary?: string;

  // Timeline - can be string (legacy) or array of ISO dates
  timeline?: string | string[];
  first_seen?: string;
  last_seen?: string;

  // Entities
  entities?: string[];

  // Source articles
  articles?: IncidentArticle[];  // Legacy format
  article_uris?: string[];
  article_metadata?: IncidentArticleMetadata[];

  // Investigation
  investigation_leads?: string[];

  // Quality assessment
  plausibility?: Plausibility;
  source_quality?: SourceQuality;
  misinfo_flags?: string[];
}

export interface IncidentTrackingResponse {
  incidents: Incident[];
  total_articles_analyzed: number;
  topics: string[];
  date_range: {
    start: string;
    end: string;
  };
  generated_at: string;
}

export interface IncidentTrackingParams {
  topics: string[];
  daysLimit?: number;
  startDate?: string;
  endDate?: string;
  maxArticles?: number;
  model?: string;
  forceRegenerate?: boolean;
  profileId?: number;
  // Custom configuration (optional)
  systemPrompt?: string;
  userPrompt?: string;
  baseOntology?: string;
  analysisInstructions?: string;
  qualityGuidelines?: string;
}

// Types for Article Insights (Narratives)
export interface ThemeArticle {
  uri: string;
  title: string;
  news_source?: string;
  publication_date?: string;
  summary?: string;
  short_summary?: string;  // Backend returns this field name
}

export interface ArticleTheme {
  theme_name: string;
  theme_summary?: string; // More concise summary for display
  description: string;
  article_count: number;
  articles: ThemeArticle[];
  key_entities?: string[];
  sentiment?: string;
  research_suggestions?: string[];
  confidence?: number; // Analysis confidence percentage
  source_count?: number; // Number of unique sources
}

export interface ArticleInsightsParams {
  topic: string;
  startDate?: string;
  endDate?: string;
  daysLimit?: number;
  forceRegenerate?: boolean;
  model?: string;
  // Custom prompt configuration
  systemPrompt?: string;
  userPrompt?: string;
}

// ===== Narratives Config =====
export interface NarrativesConfig {
  system_prompt: string;
  user_prompt: string;
  additional_instructions: string;
}

const NARRATIVES_CONFIG_KEY = 'narrativesConfig';
const INCIDENT_CONFIG_KEY = 'incidentTrackingConfig';

/**
 * Get narratives configuration from localStorage
 */
export function getNarrativesConfig(): NarrativesConfig | null {
  try {
    const saved = localStorage.getItem(NARRATIVES_CONFIG_KEY);
    if (saved) {
      return JSON.parse(saved);
    }
  } catch (err) {
    console.error('Error loading narratives config:', err);
  }
  return null;
}

// Incident config interface (matches IncidentConfigModal)
export interface IncidentConfigLocalStorage {
  system_prompt?: string;
  user_prompt?: string;
  base_ontology?: string;
  analysis_instructions?: string;
  quality_guidelines?: string;
}

/**
 * Get incident tracking configuration from localStorage
 */
export function getIncidentConfigFromStorage(): IncidentConfigLocalStorage | null {
  try {
    const saved = localStorage.getItem(INCIDENT_CONFIG_KEY);
    if (saved) {
      return JSON.parse(saved);
    }
  } catch (err) {
    console.error('Error loading incident config:', err);
  }
  return null;
}

/**
 * Get incident tracking (Highlights)
 */
export async function getIncidentTracking(params: IncidentTrackingParams): Promise<IncidentTrackingResponse> {
  const response = await fetch('/api/incident-tracking', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
    body: JSON.stringify({
      topics: params.topics,
      days_limit: params.daysLimit || 14,
      start_date: params.startDate,
      end_date: params.endDate,
      max_articles: params.maxArticles || 100,
      model: params.model || 'gpt-4o-mini',
      force_regenerate: params.forceRegenerate || false,
      profile_id: params.profileId,
      // Custom configuration (if provided)
      system_prompt: params.systemPrompt,
      user_prompt: params.userPrompt,
      base_ontology: params.baseOntology,
      analysis_instructions: params.analysisInstructions,
      quality_guidelines: params.qualityGuidelines,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(extractErrorMessage(errorData, `Failed to fetch incident tracking: ${response.status}`));
  }

  return response.json();
}

/**
 * Get article insights/themes (Narratives)
 * Uses POST to support custom prompt configuration
 */
export async function getArticleInsights(params: ArticleInsightsParams): Promise<ArticleTheme[]> {
  const response = await fetch(
    `/api/dashboard/article-insights/${encodeURIComponent(params.topic)}`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify({
        start_date: params.startDate,
        end_date: params.endDate,
        days_limit: params.daysLimit,
        force_regenerate: params.forceRegenerate || false,
        model: params.model,
        system_prompt: params.systemPrompt,
        user_prompt: params.userPrompt,
      }),
    }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(extractErrorMessage(errorData, `Failed to fetch article insights: ${response.status}`));
  }

  return response.json();
}

/**
 * Get available topics
 */
export async function getTopics(): Promise<Array<{ name: string; description?: string }>> {
  const response = await fetch('/api/topics', {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch topics: ${response.status}`);
  }

  const data = await response.json();
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

// ===== Incident Config API =====

export interface IncidentConfig {
  system_prompt?: string;
  user_prompt?: string;
  profile_context_template?: string;
  enable_profile_integration?: boolean;
  base_ontology?: string;
  domain_key?: string;
  domain_overlay?: string;
  ontology_examples?: string;
  analysis_instructions?: string;
  quality_guidelines?: string;
  output_format?: string;
}

/**
 * Get incident tracking configuration
 * Falls back to defaults if no custom config exists
 */
export async function getIncidentConfig(): Promise<IncidentConfig> {
  // First try to get custom config
  const response = await fetch('/api/incident-config', {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch incident config: ${response.status}`);
  }

  const data = await response.json();

  // If we got an empty config or just success wrapper, fetch defaults
  if (!data.system_prompt && !data.systemPrompt && (!data.config || Object.keys(data.config).length === 0)) {
    // Fetch defaults
    const defaultsResponse = await fetch('/api/incident-config/defaults', {
      credentials: 'include',
    });

    if (defaultsResponse.ok) {
      const defaults = await defaultsResponse.json();
      // Map the defaults to our expected format
      return {
        system_prompt: defaults.system_prompt || defaults.systemPrompt,
        user_prompt: defaults.user_prompt || defaults.userPrompt,
        base_ontology: defaults.base_ontology || defaults.baseOntology,
        domain_key: defaults.domain_key || defaults.domainKey || 'vanilla',
        domain_overlay: defaults.domain_overlay || defaults.domainOverlay || '',
        ontology_examples: defaults.ontology_examples || defaults.ontologyExamples || '',
        analysis_instructions: defaults.analysis_instructions || defaults.analysisInstructions || '',
        quality_guidelines: defaults.quality_guidelines || defaults.qualityGuidelines || '',
        output_format: defaults.output_format || defaults.outputFormat || '',
        profile_context_template: defaults.profile_context_template || defaults.profileContextTemplate || '',
        enable_profile_integration: defaults.enable_profile_integration ?? defaults.enableProfileIntegration ?? true,
      };
    }
  }

  // Map response to expected format (handle both snake_case and camelCase)
  const config = data.config || data;
  return {
    system_prompt: config.system_prompt || config.systemPrompt,
    user_prompt: config.user_prompt || config.userPrompt,
    base_ontology: config.base_ontology || config.baseOntology,
    domain_key: config.domain_key || config.domainKey,
    domain_overlay: config.domain_overlay || config.domainOverlay,
    ontology_examples: config.ontology_examples || config.ontologyExamples,
    analysis_instructions: config.analysis_instructions || config.analysisInstructions,
    quality_guidelines: config.quality_guidelines || config.qualityGuidelines,
    output_format: config.output_format || config.outputFormat,
    profile_context_template: config.profile_context_template || config.profileContextTemplate,
    enable_profile_integration: config.enable_profile_integration ?? config.enableProfileIntegration,
  };
}

/**
 * Save incident tracking configuration
 */
export async function saveIncidentConfig(config: IncidentConfig): Promise<void> {
  const response = await fetch('/api/incident-config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(config),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(extractErrorMessage(errorData, `Failed to save incident config: ${response.status}`));
  }
}

/**
 * Reset incident config to defaults
 */
export async function resetIncidentConfigToDefaults(): Promise<IncidentConfig> {
  const response = await fetch('/api/incident-config/defaults', {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Failed to reset incident config: ${response.status}`);
  }

  const defaults = await response.json();
  // Map the defaults to our expected format
  return {
    system_prompt: defaults.system_prompt || defaults.systemPrompt,
    user_prompt: defaults.user_prompt || defaults.userPrompt,
    base_ontology: defaults.base_ontology || defaults.baseOntology,
    domain_key: defaults.domain_key || defaults.domainKey || 'vanilla',
    domain_overlay: defaults.domain_overlay || defaults.domainOverlay || '',
    ontology_examples: defaults.ontology_examples || defaults.ontologyExamples || '',
    analysis_instructions: defaults.analysis_instructions || defaults.analysisInstructions || '',
    quality_guidelines: defaults.quality_guidelines || defaults.qualityGuidelines || '',
    output_format: defaults.output_format || defaults.outputFormat || '',
    profile_context_template: defaults.profile_context_template || defaults.profileContextTemplate || '',
    enable_profile_integration: defaults.enable_profile_integration ?? defaults.enableProfileIntegration ?? true,
  };
}

// ===== Incident Status API =====

/**
 * Update incident status (mark as seen/active)
 */
export async function updateIncidentStatus(
  incidentName: string,
  status: IncidentStatus
): Promise<{ success: boolean; message: string }> {
  const response = await fetch('/api/incident-status', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ incident_name: incidentName, status }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(extractErrorMessage(errorData, `Failed to update incident status: ${response.status}`));
  }

  return response.json();
}

/**
 * Delete an incident
 */
export async function deleteIncident(incidentName: string): Promise<{ success: boolean; message: string }> {
  const response = await fetch('/api/incident-status', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ incident_name: incidentName }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(extractErrorMessage(errorData, `Failed to delete incident: ${response.status}`));
  }

  return response.json();
}

/**
 * Save an incident
 */
export async function saveIncident(
  incidentName: string,
  topic: string
): Promise<{ success: boolean; message: string }> {
  const params = new URLSearchParams({ status: 'saved', topic });
  const response = await fetch(`/api/incident-status/${encodeURIComponent(incidentName)}?${params}`, {
    method: 'POST',
    credentials: 'include',
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(extractErrorMessage(errorData, `Failed to save incident: ${response.status}`));
  }

  return response.json();
}

/**
 * Unsave an incident (set back to active)
 */
export async function unsaveIncident(
  incidentName: string,
  topic: string
): Promise<{ success: boolean; message: string }> {
  const params = new URLSearchParams({ status: 'active', topic });
  const response = await fetch(`/api/incident-status/${encodeURIComponent(incidentName)}?${params}`, {
    method: 'POST',
    credentials: 'include',
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(extractErrorMessage(errorData, `Failed to unsave incident: ${response.status}`));
  }

  return response.json();
}

/**
 * Get list of saved incident names for a topic
 */
export async function getSavedIncidents(
  topic: string
): Promise<string[]> {
  const params = new URLSearchParams({ topic });
  const response = await fetch(`/api/incidents/saved?${params}`, {
    credentials: 'include',
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(extractErrorMessage(errorData, `Failed to get saved incidents: ${response.status}`));
  }

  const data = await response.json();
  return data.saved_incidents || [];
}

/**
 * Extended incident data for fine-tuning purposes
 */
export interface IncidentPreferenceData {
  type?: string;
  topic?: string;
  entities?: string[];
  // Enhanced fields for fine-tuning
  summary?: string;
  article_urls?: string[];
  article_titles?: string[];
  significance?: string;
  velocity?: string;
  browsing_topic?: string;
}

/**
 * Record more/less like this preference for an incident
 */
export async function recordIncidentPreference(
  incidentName: string,
  preference: 'more' | 'less',
  incidentData: IncidentPreferenceData = {}
): Promise<{ success: boolean; message: string }> {
  const response = await fetch('/api/incident-preference', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({
      incident_name: incidentName,
      preference,
      incident_data: incidentData,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(extractErrorMessage(errorData, `Failed to record preference: ${response.status}`));
  }

  return response.json();
}

/**
 * Clear a preference for an incident (toggle off)
 */
export async function clearIncidentPreference(
  incidentName: string
): Promise<{ success: boolean; message: string }> {
  const response = await fetch('/api/incident-preference', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({
      incident_name: incidentName,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(extractErrorMessage(errorData, `Failed to clear preference: ${response.status}`));
  }

  return response.json();
}

/**
 * Stored incident preference entry
 */
export interface IncidentPreferenceEntry {
  incident_name: string;
  timestamp: string;
  type?: string;
  topic?: string;
  entities?: string[];
  summary?: string;
  article_urls?: string[];
  article_titles?: string[];
  significance?: string;
  velocity?: string;
  browsing_topic?: string;
}

/**
 * Get user's incident preferences
 */
export async function getIncidentPreferences(): Promise<{
  more_like: IncidentPreferenceEntry[];
  less_like: IncidentPreferenceEntry[];
}> {
  const response = await fetch('/api/incident-preferences', {
    credentials: 'include',
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(extractErrorMessage(errorData, `Failed to get preferences: ${response.status}`));
  }

  return response.json();
}

// ===== Helper Functions =====

/**
 * Get badge class for MBFC factual reporting rating
 */
export function getFactualityClass(rating?: string): string {
  if (!rating) return 'bg-gray-100 text-gray-600';
  const lower = rating.toLowerCase();
  if (lower.includes('very high') || lower === 'high') return 'bg-green-100 text-green-700';
  if (lower.includes('mostly factual') || lower === 'mostly') return 'bg-lime-100 text-lime-700';
  if (lower === 'mixed') return 'bg-yellow-100 text-yellow-700';
  if (lower === 'low') return 'bg-red-100 text-red-700';
  if (lower.includes('very low')) return 'bg-red-200 text-red-800';
  return 'bg-gray-100 text-gray-600';
}

/**
 * Get badge class for MBFC credibility rating
 */
export function getMBFCCredibilityClass(rating?: string): string {
  if (!rating) return 'bg-gray-100 text-gray-600';
  const lower = rating.toLowerCase();
  if (lower.includes('high')) return 'bg-green-100 text-green-700';
  if (lower === 'medium' || lower === 'mixed') return 'bg-yellow-100 text-yellow-700';
  if (lower === 'low') return 'bg-red-100 text-red-700';
  return 'bg-gray-100 text-gray-600';
}

/**
 * Get badge class for bias rating
 */
export function getBiasClass(bias?: string): string {
  if (!bias) return 'bg-gray-100 text-gray-600';
  const lower = bias.toLowerCase();
  if (lower.includes('least') || lower === 'center') return 'bg-green-100 text-green-700';
  if (lower.includes('left-center') || lower.includes('right-center')) return 'bg-blue-100 text-blue-700';
  if (lower === 'left' || lower === 'right') return 'bg-yellow-100 text-yellow-700';
  if (lower.includes('extreme') || lower.includes('conspiracy') || lower.includes('fringe')) return 'bg-red-100 text-red-700';
  return 'bg-gray-100 text-gray-600';
}

/**
 * Get consistent color for a topic
 */
export function getTopicColor(topic: string): string {
  const colors = [
    '#ec4899', // pink
    '#8b5cf6', // violet
    '#3b82f6', // blue
    '#10b981', // emerald
    '#f59e0b', // amber
    '#ef4444', // red
    '#06b6d4', // cyan
    '#84cc16', // lime
  ];

  // Simple hash function for consistent color
  let hash = 0;
  for (let i = 0; i < topic.length; i++) {
    hash = topic.charCodeAt(i) + ((hash << 5) - hash);
  }
  return colors[Math.abs(hash) % colors.length];
}

/**
 * Get type badge color for incident type (with dark mode support)
 */
export function getTypeBadgeColor(type: IncidentType): string {
  switch (type) {
    case 'incident': return 'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300';
    case 'entity': return 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300';
    case 'expertise': return 'bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300';
    case 'informed_insider': return 'bg-gray-800 text-white dark:bg-gray-600 dark:text-gray-100';
    case 'trend_signal': return 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/50 dark:text-cyan-300';
    case 'strategic_shift': return 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-200';
    case 'event': return 'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300';
    default: return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300';
  }
}

/**
 * Get significance badge color (with dark mode support)
 */
export function getSignificanceBadgeColor(significance: IncidentSignificance): string {
  switch (significance) {
    case 'high': return 'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300';
    case 'medium': return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300';
    case 'low': return 'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300';
    default: return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300';
  }
}

/**
 * Get plausibility badge color (with dark mode support)
 */
export function getPlausibilityBadgeColor(plausibility?: Plausibility): string {
  switch (plausibility) {
    case 'likely': return 'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300';
    case 'questionable': return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300';
    case 'implausible': return 'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300';
    default: return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300';
  }
}

/**
 * Get source quality badge color (with dark mode support)
 */
export function getSourceQualityBadgeColor(quality?: SourceQuality): string {
  switch (quality) {
    case 'high': return 'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300';
    case 'mixed': return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300';
    case 'low': return 'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300';
    default: return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300';
  }
}

/**
 * Format source name from URL or provided source
 */
export function formatSource(source?: string, uri?: string): string {
  if (source) return source;
  if (!uri) return 'Unknown Source';
  try {
    const url = new URL(uri);
    return url.hostname.replace(/^www\./, '');
  } catch {
    return 'Unknown Source';
  }
}

/**
 * Prettify misinfo flag for display
 */
export function prettifyMisinfoFlag(flag: string): string {
  switch (flag) {
    case 'extraordinary_claim': return 'Extraordinary claim';
    case 'no_independent_verification': return 'No independent verification';
    case 'low_factuality_source': return 'Check Source';
    case 'low_credibility_source': return 'Check Source (credibility)';
    case 'fringe_bias': return 'Fringe bias';
    default: return flag.replace(/_/g, ' ');
  }
}

// ===== Briefing Preference API =====

/**
 * Extended briefing data for fine-tuning purposes
 */
export interface BriefingPreferenceData {
  summary?: string;
  category?: string;
  executive_takeaway?: string;
  strategic_relevance?: string;
  signal_strength?: string;
  risk_opportunity?: string;
  time_horizon?: string;
  source?: string;
  url?: string;
}

/**
 * Stored briefing preference entry
 */
export interface BriefingPreferenceEntry {
  headline: string;
  timestamp: string;
  summary?: string;
  category?: string;
  executive_takeaway?: string;
  strategic_relevance?: string;
  signal_strength?: string;
  risk_opportunity?: string;
  time_horizon?: string;
  source?: string;
  url?: string;
}

/**
 * Record more/less like this preference for a briefing story
 */
export async function recordBriefingPreference(
  headline: string,
  preference: 'more' | 'less',
  briefingData: BriefingPreferenceData = {}
): Promise<{ success: boolean; message: string }> {
  const response = await fetch('/api/briefing-preference', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({
      headline,
      preference,
      briefing_data: briefingData,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(extractErrorMessage(errorData, `Failed to record preference: ${response.status}`));
  }

  return response.json();
}

/**
 * Clear a preference for a briefing story (toggle off)
 */
export async function clearBriefingPreference(
  headline: string
): Promise<{ success: boolean; message: string }> {
  const response = await fetch('/api/briefing-preference', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({
      headline,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(extractErrorMessage(errorData, `Failed to clear preference: ${response.status}`));
  }

  return response.json();
}

/**
 * Get user's briefing preferences
 */
export async function getBriefingPreferences(): Promise<{
  more_like: BriefingPreferenceEntry[];
  less_like: BriefingPreferenceEntry[];
}> {
  const response = await fetch('/api/briefing-preferences', {
    credentials: 'include',
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(extractErrorMessage(errorData, `Failed to get preferences: ${response.status}`));
  }

  return response.json();
}

/**
 * Hide a briefing story from future display
 */
export async function hideBriefing(
  headline: string
): Promise<{ success: boolean; message: string }> {
  const response = await fetch('/api/briefing-hide', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ headline }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(extractErrorMessage(errorData, `Failed to hide briefing: ${response.status}`));
  }

  return response.json();
}

/**
 * Get list of hidden briefing headlines
 */
export async function getHiddenBriefings(): Promise<string[]> {
  const response = await fetch('/api/hidden-briefings', {
    credentials: 'include',
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(extractErrorMessage(errorData, `Failed to get hidden briefings: ${response.status}`));
  }

  const data = await response.json();
  return data.hidden_briefings || [];
}
