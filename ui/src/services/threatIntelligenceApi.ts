/**
 * Threat Intelligence API Service
 * Handles all API calls for the threat intelligence feature
 */

// ============================================================================
// Types
// ============================================================================

export interface Threat {
  id: number;
  threat_name: string;
  threat_type: ThreatCategory;
  threat_subtype: string | null;
  severity_level: SeverityLevel;
  severity_score: number;
  trend: Trend | null;
  threat_actor_id: number | null;
  threat_actor_name: string | null;
  attributed_country: string | null;
  attributed_country_name: string | null;
  target_countries: string[] | null;
  target_latitude: number | null;
  target_longitude: number | null;
  target_industries: string[] | null;
  cve_ids: string[] | null;
  mitre_techniques: string[] | null;
  malware_families: string[] | null;
  first_seen_date: string | null;
  last_seen_date: string | null;
  article_count: number;
  recent_article_count: number;
  description: string | null;
  tags: string[] | null;
  created_at?: string;
  updated_at?: string;
}

export interface ThreatMapData {
  id: number;
  threat_name: string;
  threat_type: ThreatCategory;
  threat_subtype: string | null;
  severity_level: SeverityLevel;
  severity_score: number;
  trend: Trend | null;
  threat_actor_name: string | null;
  attributed_country: string | null;
  attributed_country_name: string | null;
  target_countries: string[] | null;
  latitude: number;
  longitude: number;
  target_industries: string[] | null;
  article_count: number;
  first_seen_date: string | null;
  last_seen_date: string | null;
}

export type SeverityLevel = 'critical' | 'high' | 'medium' | 'low' | 'info';

export type Trend = 'escalating' | 'stable' | 'declining';

export type ThreatCategory =
  | 'malware'
  | 'ransomware'
  | 'apt'
  | 'phishing'
  | 'vulnerability'
  | 'data_breach'
  | 'botnet'
  | 'ddos'
  | 'supply_chain'
  | 'credential_theft'
  | 'cryptojacking'
  | 'insider_threat'
  | 'iot_ot'
  | 'mobile';

export type ActorType =
  | 'nation_state'
  | 'cybercrime'
  | 'hacktivist'
  | 'insider'
  | 'script_kiddie'
  | 'unknown';

export const THREAT_CATEGORIES: ThreatCategory[] = [
  'malware',
  'ransomware',
  'apt',
  'phishing',
  'vulnerability',
  'data_breach',
  'botnet',
  'ddos',
  'supply_chain',
  'credential_theft',
  'cryptojacking',
  'insider_threat',
  'iot_ot',
  'mobile',
];

export const THREAT_CATEGORY_LABELS: Record<ThreatCategory, string> = {
  malware: 'Malware',
  ransomware: 'Ransomware',
  apt: 'APT',
  phishing: 'Phishing',
  vulnerability: 'Vulnerability',
  data_breach: 'Data Breach',
  botnet: 'Botnet',
  ddos: 'DDoS',
  supply_chain: 'Supply Chain',
  credential_theft: 'Credential Theft',
  cryptojacking: 'Cryptojacking',
  insider_threat: 'Insider Threat',
  iot_ot: 'IoT/OT',
  mobile: 'Mobile',
};

export const SEVERITY_LEVELS: SeverityLevel[] = ['critical', 'high', 'medium', 'low', 'info'];

export const SEVERITY_COLORS: Record<SeverityLevel, string> = {
  critical: '#DC2626',
  high: '#F97316',
  medium: '#EAB308',
  low: '#22C55E',
  info: '#3B82F6',
};

export const SEVERITY_LABELS: Record<SeverityLevel, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
  info: 'Info',
};

export const ACTOR_TYPES: ActorType[] = [
  'nation_state',
  'cybercrime',
  'hacktivist',
  'insider',
  'script_kiddie',
  'unknown',
];

export const ACTOR_TYPE_LABELS: Record<ActorType, string> = {
  nation_state: 'Nation State',
  cybercrime: 'Cybercrime',
  hacktivist: 'Hacktivist',
  insider: 'Insider',
  script_kiddie: 'Script Kiddie',
  unknown: 'Unknown',
};

export interface OverviewStats {
  total_threats: number;
  by_severity: Record<SeverityLevel, number>;
  total_articles: number;
  recent_articles: number;
  total_actors: number;
  escalating_count: number;
  declining_count: number;
  new_threats: number;
  by_type: Record<string, number>;
  top_threats: ThreatSummary[];
}

export interface ThreatSummary {
  id: number;
  threat_name: string;
  threat_type: ThreatCategory;
  severity_level: SeverityLevel;
  severity_score: number;
  threat_actor_name: string | null;
  article_count: number;
  trend: Trend | null;
}

export interface ThreatActor {
  id: number;
  name: string;
  aliases: string[] | null;
  actor_type: ActorType;
  attributed_country: string | null;
  attributed_country_name: string | null;
  description: string | null;
  motivation: string | null;
  sophistication_level: string | null;
  target_industries: string[] | null;
  target_regions: string[] | null;
  known_ttps: string[] | null;
  associated_malware: string[] | null;
  first_observed: string | null;
  last_active: string | null;
  threat_count: number;
  article_count: number;
  created_at?: string;
  updated_at?: string;
}

export interface ThreatArticle {
  uri: string;
  title: string | null;
  source: string | null;
  publication_date: string | null;
  summary: string | null;
  category: string | null;
  sentiment: string | null;
  relevance_score: number | null;
  mention_type: string | null;
}

export interface LinkedThreat {
  id: number;
  name: string;
  severity_level: SeverityLevel;
  type: string | null;
  severity_score: number;
}

export interface LinkedArticle {
  uri: string;
  title: string | null;
  source: string | null;
  publication_date: string | null;
  summary: string | null;
  category: string | null;
  sentiment: string | null;
  relevance_score: number | null;
  threat_id: number | null;
  threat_name: string | null;
  severity_level: SeverityLevel;
  threat_type: string | null;
  severity_score: number | null;
  threats: LinkedThreat[];
}

export interface TimelineDataPoint {
  date: string;
  article_count: number;
  avg_severity: number;
  threat_count: number;
}

export interface DailyCount {
  date: string;
  article_count: number;
  threat_count: number;
  avg_severity: number;
  rolling_avg: number;
}

export interface CategoryData {
  category: string;
  count: number;
  avg_severity: number;
  total_articles: number;
}

export interface CategoryTrendPeriod {
  period: string;
  by_type: Record<string, number>;
}

export interface TTPAnalysis {
  technique_id: string;
  technique_name: string | null;
  tactic: string | null;
  threat_count: number;
}

export interface IOC {
  id: number;
  indicator_type: string;
  indicator_value: string;
  threat_id: number | null;
  confidence: number | null;
  first_seen: string | null;
  last_seen: string | null;
  is_active: boolean;
  description: string | null;
}

export interface Campaign {
  id: number;
  name: string;
  description: string | null;
  threat_actor_id: number | null;
  threat_actor_name: string | null;
  start_date: string | null;
  end_date: string | null;
  is_active: boolean;
  target_countries: string[] | null;
  target_industries: string[] | null;
  techniques_used: string[] | null;
  malware_used: string[] | null;
  threat_count: number;
  article_count: number;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ProcessingStats {
  total_curated_articles: number;
  processed_articles: number;
  unprocessed_articles: number;
  total_threats: number;
  total_actors: number;
  processing_percentage: number;
  topic: string;
}

export interface AvailableTopic {
  topic: string;
  total_articles: number;
  unprocessed_count: number;
}

export interface ProcessArticlesRequest {
  batch_size: number;
  model: string;
  topic?: string;
  process_all?: boolean;
}

export interface ProcessArticlesResponse {
  status: string;
  message: string;
  articles_processed: number;
  threats_created: number;
  threats_updated: number;
  articles_skipped: number;
  errors: number;
}

export interface ThreatIntelSchedule {
  id: number;
  name: string;
  topic: string | null;
  batch_size: number;
  model: string;
  process_all: boolean;
  schedule_enabled: boolean;
  schedule_type: 'interval' | 'daily' | null;
  schedule_interval: number | null;
  schedule_unit: 'minutes' | 'hours' | 'days' | null;
  schedule_time: string | null;
  notify_on_complete: boolean;
  notify_threshold: number;
  last_run_at: string | null;
  next_run_at: string | null;
  last_run_status: 'success' | 'error' | 'running' | null;
  last_run_error: string | null;
  last_run_articles_processed: number;
  last_run_threats_created: number;
  last_run_threats_updated: number;
  run_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface CreateScheduleRequest {
  name: string;
  topic?: string;
  batch_size?: number;
  model?: string;
  process_all?: boolean;
  schedule_enabled?: boolean;
  schedule_type?: 'interval' | 'daily';
  schedule_interval?: number;
  schedule_unit?: 'minutes' | 'hours' | 'days';
  schedule_time?: string;
  notify_on_complete?: boolean;
  notify_threshold?: number;
}

export interface UpdateScheduleRequest {
  name?: string;
  topic?: string;
  batch_size?: number;
  model?: string;
  process_all?: boolean;
  schedule_enabled?: boolean;
  schedule_type?: 'interval' | 'daily';
  schedule_interval?: number;
  schedule_unit?: 'minutes' | 'hours' | 'days';
  schedule_time?: string;
  notify_on_complete?: boolean;
  notify_threshold?: number;
}

export interface MonitorStatus {
  running: boolean;
  last_check_time: string | null;
  last_error: string | null;
  schedules_checked: number;
  schedules_run: number;
  is_checking: boolean;
}

export interface Narrative {
  id: number;
  narrative_text: string;
  executive_summary: string | null;
  threat_landscape: string | null;
  emerging_threats: string | null;
  recommendations: string | null;
  threat_count: number;
  article_count: number;
  top_threat_types: string[] | null;
  top_actors: string[] | null;
  severity_breakdown: Record<string, number> | null;
  model_used: string | null;
  topic: string | null;
  generated_at: string | null;
}

export interface ThreatNarrative {
  id: number;
  period_type: 'daily' | 'weekly' | 'monthly';
  period_start: string;
  period_end: string;
  content: string;
  threat_count: number;
  actor_count: number;
  article_count: number;
  model_used: string | null;
  topic: string | null;
  created_at: string;
}

export interface ThreatSchedule {
  id: number;
  name: string;
  schedule_type: 'interval' | 'daily';
  schedule_interval: number;
  schedule_unit: 'minutes' | 'hours' | 'days' | 'weeks';
  schedule_time: string | null;
  batch_size: number;
  schedule_enabled: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  last_run_status: string | null;
  run_count: number;
}

export interface ProcessingStatus {
  status: 'idle' | 'processing' | 'completed' | 'failed';
  processed: number;
  total_articles: number;
  threats_extracted: number;
  actors_identified: number;
  iocs_extracted: number;
  current_article: string | null;
  error: string | null;
}

// ============================================================================
// API Base URL
// ============================================================================

const API_BASE = '/api/threat-intelligence';

// ============================================================================
// API Functions - Overview & Stats
// ============================================================================

export async function getOverviewStats(
  topic?: string,
  daysBack: number = 30
): Promise<OverviewStats> {
  const params = new URLSearchParams();
  if (topic) params.append('topic', topic);
  params.append('days_back', String(daysBack));

  const response = await fetch(`${API_BASE}/overview?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch overview stats: ${response.statusText}`);
  }
  return response.json();
}

export async function getThreatCategories(): Promise<ThreatCategory[]> {
  const response = await fetch(`${API_BASE}/threat-categories`);
  if (!response.ok) {
    throw new Error(`Failed to fetch threat categories: ${response.statusText}`);
  }
  const data = await response.json();
  return data.categories;
}

export async function getSeverityLevels(): Promise<SeverityLevel[]> {
  const response = await fetch(`${API_BASE}/severity-levels`);
  if (!response.ok) {
    throw new Error(`Failed to fetch severity levels: ${response.statusText}`);
  }
  const data = await response.json();
  return data.severity_levels;
}

// ============================================================================
// API Functions - Threats
// ============================================================================

export async function getMapData(options: {
  topic?: string;
  threatTypes?: ThreatCategory[];
  severityLevels?: SeverityLevel[];
  daysBack?: number;
}): Promise<ThreatMapData[]> {
  const params = new URLSearchParams();
  if (options.topic) params.append('topic', options.topic);
  if (options.threatTypes?.length) params.append('threat_types', options.threatTypes.join(','));
  if (options.severityLevels?.length) params.append('severity_levels', options.severityLevels.join(','));
  if (options.daysBack) params.append('days_back', String(options.daysBack));

  const response = await fetch(`${API_BASE}/map-data?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch map data: ${response.statusText}`);
  }
  const data = await response.json();
  return data.threats;
}

export async function getThreats(options: {
  topic?: string;
  threatTypes?: ThreatCategory[];
  severityLevels?: SeverityLevel[];
  actorId?: number;
  daysBack?: number;
  page?: number;
  pageSize?: number;
  sortBy?: 'severity' | 'articles' | 'name' | 'type' | 'updated';
  sortOrder?: 'asc' | 'desc';
}): Promise<PaginatedResponse<Threat>> {
  const params = new URLSearchParams();
  if (options.topic) params.append('topic', options.topic);
  if (options.threatTypes?.length) params.append('threat_types', options.threatTypes.join(','));
  if (options.severityLevels?.length) params.append('severity_levels', options.severityLevels.join(','));
  if (options.actorId) params.append('actor_id', String(options.actorId));
  if (options.daysBack) params.append('days_back', String(options.daysBack));
  if (options.page) params.append('page', String(options.page));
  if (options.pageSize) params.append('page_size', String(options.pageSize));
  if (options.sortBy) params.append('sort_by', options.sortBy);
  if (options.sortOrder) params.append('sort_order', options.sortOrder);

  const response = await fetch(`${API_BASE}/threats?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch threats: ${response.statusText}`);
  }
  const data = await response.json();
  return {
    data: data.threats,
    total: data.total,
    page: data.page,
    page_size: data.page_size,
    total_pages: data.total_pages,
  };
}

export async function getThreatById(threatId: number): Promise<Threat> {
  const response = await fetch(`${API_BASE}/threat/${threatId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch threat: ${response.statusText}`);
  }
  return response.json();
}

export async function getThreatArticles(
  threatId: number,
  page: number = 1,
  pageSize: number = 20
): Promise<PaginatedResponse<ThreatArticle>> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });

  const response = await fetch(`${API_BASE}/threat/${threatId}/articles?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch threat articles: ${response.statusText}`);
  }
  const data = await response.json();
  return {
    data: data.articles,
    total: data.total,
    page: data.page,
    page_size: data.page_size,
    total_pages: data.total_pages,
  };
}

/**
 * Get all articles that have linked threats (paginated with filters)
 */
export async function getAllThreatArticles(options: {
  page?: number;
  pageSize?: number;
  search?: string;
  severityLevel?: SeverityLevel;
  threatType?: ThreatType;
  threatId?: number;
  actorId?: number;
  campaignId?: number;
  sortBy?: 'date' | 'title' | 'relevance' | 'severity';
  sortOrder?: 'asc' | 'desc';
}): Promise<PaginatedResponse<LinkedArticle>> {
  const params = new URLSearchParams();
  if (options.page) params.append('page', String(options.page));
  if (options.pageSize) params.append('page_size', String(options.pageSize));
  if (options.search) params.append('search', options.search);
  if (options.severityLevel) params.append('severity_level', options.severityLevel);
  if (options.threatType) params.append('threat_type', options.threatType);
  if (options.threatId) params.append('threat_id', String(options.threatId));
  if (options.actorId) params.append('actor_id', String(options.actorId));
  if (options.campaignId) params.append('campaign_id', String(options.campaignId));
  if (options.sortBy) params.append('sort_by', options.sortBy);
  if (options.sortOrder) params.append('sort_order', options.sortOrder);

  const response = await fetch(`${API_BASE}/articles?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch articles: ${response.statusText}`);
  }
  const data = await response.json();
  return {
    data: data.articles,
    total: data.total,
    page: data.page,
    page_size: data.page_size,
    total_pages: data.total_pages,
  };
}

// ============================================================================
// API Functions - Actors
// ============================================================================

export async function getActors(options: {
  actorType?: ActorType;
  page?: number;
  pageSize?: number;
  sortBy?: 'threat_count' | 'article_count' | 'name' | 'sophistication' | 'last_active';
  sortOrder?: 'asc' | 'desc';
}): Promise<PaginatedResponse<ThreatActor>> {
  const params = new URLSearchParams();
  if (options.actorType) params.append('actor_type', options.actorType);
  if (options.page) params.append('page', String(options.page));
  if (options.pageSize) params.append('page_size', String(options.pageSize));
  if (options.sortBy) params.append('sort_by', options.sortBy);
  if (options.sortOrder) params.append('sort_order', options.sortOrder);

  const response = await fetch(`${API_BASE}/actors?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch actors: ${response.statusText}`);
  }
  const data = await response.json();
  return {
    data: data.actors,
    total: data.total,
    page: data.page,
    page_size: data.page_size,
    total_pages: data.total_pages,
  };
}

export async function getActorById(actorId: number): Promise<ThreatActor> {
  const response = await fetch(`${API_BASE}/actor/${actorId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch actor: ${response.statusText}`);
  }
  return response.json();
}

export async function getActorThreats(
  actorId: number,
  page: number = 1,
  pageSize: number = 20
): Promise<PaginatedResponse<Threat>> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });

  const response = await fetch(`${API_BASE}/actor/${actorId}/threats?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch actor threats: ${response.statusText}`);
  }
  const data = await response.json();
  return {
    data: data.threats,
    total: data.total,
    page: data.page,
    page_size: data.page_size,
    total_pages: data.total_pages,
  };
}

// ============================================================================
// API Functions - Timeline & Analysis
// ============================================================================

export async function getTimelineData(
  topic?: string,
  daysBack: number = 30
): Promise<TimelineDataPoint[]> {
  const params = new URLSearchParams();
  if (topic) params.append('topic', topic);
  params.append('days_back', String(daysBack));

  const response = await fetch(`${API_BASE}/timeline?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch timeline data: ${response.statusText}`);
  }
  const data = await response.json();
  return data.timeline;
}

export async function getDailyCounts(
  topic?: string,
  daysBack: number = 30
): Promise<DailyCount[]> {
  const params = new URLSearchParams();
  if (topic) params.append('topic', topic);
  params.append('days_back', String(daysBack));

  const response = await fetch(`${API_BASE}/daily-counts?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch daily counts: ${response.statusText}`);
  }
  const data = await response.json();
  return data.daily_counts;
}

export async function getCategoriesData(topic?: string): Promise<CategoryData[]> {
  const params = new URLSearchParams();
  if (topic) params.append('topic', topic);

  const response = await fetch(`${API_BASE}/categories?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch categories data: ${response.statusText}`);
  }
  const data = await response.json();
  return data.categories;
}

export async function getCategoryTrends(
  topic?: string,
  daysBack: number = 90,
  granularity: 'weekly' | 'monthly' = 'weekly'
): Promise<CategoryTrendPeriod[]> {
  const params = new URLSearchParams();
  if (topic) params.append('topic', topic);
  params.append('days_back', String(daysBack));
  params.append('granularity', granularity);

  const response = await fetch(`${API_BASE}/category-trends?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch category trends: ${response.statusText}`);
  }
  const data = await response.json();
  return data.trends;
}

export async function getTTPAnalysis(topic?: string): Promise<TTPAnalysis[]> {
  const params = new URLSearchParams();
  if (topic) params.append('topic', topic);

  const response = await fetch(`${API_BASE}/ttp-analysis?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch TTP analysis: ${response.statusText}`);
  }
  const data = await response.json();
  return data.techniques || [];
}

// ============================================================================
// API Functions - IOCs
// ============================================================================

export async function getIOCs(options: {
  indicatorType?: string;
  threatId?: number;
  page?: number;
  pageSize?: number;
}): Promise<PaginatedResponse<IOC>> {
  const params = new URLSearchParams();
  if (options.indicatorType) params.append('indicator_type', options.indicatorType);
  if (options.threatId) params.append('threat_id', String(options.threatId));
  if (options.page) params.append('page', String(options.page));
  if (options.pageSize) params.append('page_size', String(options.pageSize));

  const response = await fetch(`${API_BASE}/iocs?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch IOCs: ${response.statusText}`);
  }
  const data = await response.json();
  return {
    data: data.iocs,
    total: data.total,
    page: data.page,
    page_size: data.page_size,
    total_pages: data.total_pages,
  };
}

// ============================================================================
// API Functions - Campaigns
// ============================================================================

export async function getCampaigns(options: {
  isActive?: boolean;
  page?: number;
  pageSize?: number;
}): Promise<PaginatedResponse<Campaign>> {
  const params = new URLSearchParams();
  if (options.isActive !== undefined) params.append('is_active', String(options.isActive));
  if (options.page) params.append('page', String(options.page));
  if (options.pageSize) params.append('page_size', String(options.pageSize));

  const response = await fetch(`${API_BASE}/campaigns?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch campaigns: ${response.statusText}`);
  }
  const data = await response.json();
  return {
    data: data.campaigns,
    total: data.total,
    page: data.page,
    page_size: data.page_size,
    total_pages: data.total_pages,
  };
}

// ============================================================================
// API Functions - Articles
// ============================================================================

export async function getAllArticles(options: {
  page?: number;
  pageSize?: number;
  severityLevel?: SeverityLevel;
  threatType?: ThreatCategory;
  threatId?: number;
  search?: string;
  sortBy?: 'date' | 'title' | 'relevance' | 'severity';
  sortOrder?: 'asc' | 'desc';
}): Promise<PaginatedResponse<LinkedArticle>> {
  const params = new URLSearchParams();
  if (options.page) params.append('page', String(options.page));
  if (options.pageSize) params.append('page_size', String(options.pageSize));
  if (options.severityLevel) params.append('severity_level', options.severityLevel);
  if (options.threatType) params.append('threat_type', options.threatType);
  if (options.threatId) params.append('threat_id', String(options.threatId));
  if (options.search) params.append('search', options.search);
  if (options.sortBy) params.append('sort_by', options.sortBy);
  if (options.sortOrder) params.append('sort_order', options.sortOrder);

  const response = await fetch(`${API_BASE}/articles?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch articles: ${response.statusText}`);
  }
  const data = await response.json();
  return {
    data: data.articles,
    total: data.total,
    page: data.page,
    page_size: data.page_size,
    total_pages: data.total_pages,
  };
}

// ============================================================================
// API Functions - Processing
// ============================================================================

export async function getProcessingStats(topic?: string): Promise<ProcessingStats> {
  const params = new URLSearchParams();
  if (topic) params.append('topic', topic);

  const response = await fetch(`${API_BASE}/processing-stats?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch processing stats: ${response.statusText}`);
  }
  return response.json();
}

export async function getAvailableTopics(): Promise<AvailableTopic[]> {
  const response = await fetch(`${API_BASE}/available-topics`);
  if (!response.ok) {
    throw new Error(`Failed to fetch available topics: ${response.statusText}`);
  }
  const data = await response.json();
  return data.topics;
}

export async function processArticles(
  request: ProcessArticlesRequest
): Promise<ProcessArticlesResponse> {
  const response = await fetch(`${API_BASE}/process-articles`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Failed to process articles: ${response.statusText}`);
  }
  return response.json();
}

export async function getProcessingStatus(): Promise<{
  running: boolean;
  progress: number;
  total: number;
  processed: number;
  created: number;
  updated: number;
  skipped: number;
  errors: number;
  last_error: string | null;
  completed: boolean;
  message: string;
}> {
  const response = await fetch(`${API_BASE}/process-articles/status`);
  if (!response.ok) {
    throw new Error(`Failed to fetch processing status: ${response.statusText}`);
  }
  return response.json();
}

// ============================================================================
// API Functions - Narratives
// ============================================================================

export async function getNarratives(
  page: number = 1,
  pageSize: number = 20,
  topic?: string
): Promise<PaginatedResponse<ThreatNarrative>> {
  const params = new URLSearchParams();
  params.append('page', String(page));
  params.append('page_size', String(pageSize));
  if (topic) params.append('topic', topic);

  const response = await fetch(`${API_BASE}/narratives?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch narratives: ${response.statusText}`);
  }
  const result = await response.json();

  // Map backend fields to frontend interface
  const mappedData = (result.data || []).map((item: any) => {
    const generatedAt = item.generated_at || new Date().toISOString();
    return {
      id: item.id,
      period_type: 'weekly' as const,
      period_start: item.period_start || generatedAt,
      period_end: item.period_end || generatedAt,
      content: item.narrative_text || item.executive_summary || '',
      threat_count: item.threat_count || 0,
      actor_count: item.actor_count || item.top_actors?.length || 0,
      article_count: item.article_count || 0,
      model_used: item.model_used,
      topic: item.topic,
      created_at: generatedAt,
    };
  });

  return {
    data: mappedData,
    total: result.total,
    page: result.page,
    page_size: result.page_size,
    total_pages: result.total_pages,
  };
}

export async function getLatestNarrative(topic?: string): Promise<Narrative | null> {
  const params = new URLSearchParams();
  if (topic) params.append('topic', topic);

  const response = await fetch(`${API_BASE}/narrative?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch narrative: ${response.statusText}`);
  }
  return response.json();
}

export async function deleteNarrative(narrativeId: number): Promise<void> {
  const response = await fetch(`${API_BASE}/narratives/${narrativeId}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Failed to delete narrative: ${response.statusText}`);
  }
}

export async function generateNarrative(
  periodType: 'daily' | 'weekly' | 'monthly' = 'weekly',
  topic?: string,
  model: string = 'gpt-4o-mini'
): Promise<ThreatNarrative> {
  const response = await fetch(`${API_BASE}/generate-narrative`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ period_type: periodType, topic, model }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Failed to generate narrative: ${response.statusText}`);
  }
  const data = await response.json();
  const item = data.narrative;

  // Map backend fields to frontend interface
  return {
    id: item.id,
    period_type: periodType,
    period_start: item.period_start || item.generated_at || '',
    period_end: item.period_end || item.generated_at || '',
    content: item.narrative_text || item.executive_summary || '',
    threat_count: item.threat_count || 0,
    actor_count: 0,
    article_count: item.article_count || 0,
    model_used: item.model_used,
    topic: item.topic,
    created_at: item.generated_at || new Date().toISOString(),
  };
}

// ============================================================================
// API Functions - Schedules
// ============================================================================

export async function getSchedules(): Promise<ThreatIntelSchedule[]> {
  const response = await fetch(`${API_BASE}/schedules`);
  if (!response.ok) {
    throw new Error(`Failed to fetch schedules: ${response.statusText}`);
  }
  const data = await response.json();
  return data.schedules;
}

export async function createSchedule(
  request: CreateScheduleRequest
): Promise<{ schedule_id: number; next_run_at: string | null }> {
  const response = await fetch(`${API_BASE}/schedules`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Failed to create schedule: ${response.statusText}`);
  }
  return response.json();
}

export async function updateSchedule(
  scheduleId: number,
  request: UpdateScheduleRequest
): Promise<void> {
  const response = await fetch(`${API_BASE}/schedules/${scheduleId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Failed to update schedule: ${response.statusText}`);
  }
}

export async function deleteSchedule(scheduleId: number): Promise<void> {
  const response = await fetch(`${API_BASE}/schedules/${scheduleId}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Failed to delete schedule: ${response.statusText}`);
  }
}

export async function runScheduleNow(scheduleId: number): Promise<ProcessArticlesResponse> {
  const response = await fetch(`${API_BASE}/schedules/${scheduleId}/run`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Failed to run schedule: ${response.statusText}`);
  }
  return response.json();
}

// Alias for backwards compatibility
export const runSchedule = runScheduleNow;

export async function getMonitorStatus(): Promise<MonitorStatus> {
  const response = await fetch(`${API_BASE}/schedules/status`);
  if (!response.ok) {
    throw new Error(`Failed to fetch monitor status: ${response.statusText}`);
  }
  return response.json();
}
