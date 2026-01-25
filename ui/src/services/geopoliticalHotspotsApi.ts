/**
 * Geopolitical Hotspots API Service
 * Handles all API calls for the geopolitical hotspots feature
 */

// Types
export interface Hotspot {
  id: number;
  location_name: string;
  location_type: string;
  country_code: string | null;
  country_name: string | null;
  latitude: number;
  longitude: number;
  intensity_score: number;
  risk_level: RiskLevel;
  trend: Trend | null;
  article_count: number;
  recent_article_count: number;
  primary_category: ThreatCategory | null;
  tags: string[] | null;
  last_article_date: string | null;
  created_at?: string;
  updated_at?: string;
  topic?: string;
}

export type RiskLevel = 'critical' | 'high' | 'medium' | 'low' | 'info';

export type Trend = 'escalating' | 'stable' | 'de-escalating';

export type ThreatCategory =
  | 'conflict'
  | 'protest'
  | 'disaster'
  | 'diplomatic'
  | 'economic'
  | 'terrorism'
  | 'cyber'
  | 'health'
  | 'environmental'
  | 'military'
  | 'crime'
  | 'piracy'
  | 'infrastructure'
  | 'commodities';

export const THREAT_CATEGORIES: ThreatCategory[] = [
  'conflict',
  'protest',
  'disaster',
  'diplomatic',
  'economic',
  'terrorism',
  'cyber',
  'health',
  'environmental',
  'military',
  'crime',
  'piracy',
  'infrastructure',
  'commodities',
];

export const RISK_LEVELS: RiskLevel[] = ['critical', 'high', 'medium', 'low', 'info'];

export const RISK_COLORS: Record<RiskLevel, string> = {
  critical: '#DC2626',
  high: '#F97316',
  medium: '#EAB308',
  low: '#22C55E',
  info: '#3B82F6',
};

export interface OverviewStats {
  total_hotspots: number;
  by_risk_level: Record<RiskLevel, number>;
  total_articles: number;
  recent_articles: number;
  countries_affected: number;
  escalating_count: number;
  de_escalating_count: number;
  by_category: Record<string, number>;
  top_hotspots: HotspotSummary[];
}

export interface HotspotSummary {
  id: number;
  location_name: string;
  country_name: string | null;
  intensity_score: number;
  risk_level: RiskLevel;
  primary_category: ThreatCategory | null;
  article_count: number;
  trend: Trend | null;
}

export interface CountryStats {
  country_code: string;
  country_name: string;
  total_hotspots: number;
  total_articles: number;
  heat_value: number;
  max_risk_level: RiskLevel | null;
  primary_category: ThreatCategory | null;
}

export interface HotspotArticle {
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

export interface TimelineDataPoint {
  date: string;
  article_count: number;
  avg_intensity: number;
  hotspot_count: number;
}

export interface RegionData {
  region: string;
  hotspot_count: number;
  article_count: number;
}

export interface CategoryData {
  category: string;
  count: number;
  avg_intensity: number;
  total_articles: number;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// API Base URL
const API_BASE = '/api/geopolitical-hotspots';

// API Functions

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

export async function getMapData(options: {
  topic?: string;
  categories?: ThreatCategory[];
  riskLevels?: RiskLevel[];
  daysBack?: number;
}): Promise<Hotspot[]> {
  const params = new URLSearchParams();
  if (options.topic) params.append('topic', options.topic);
  if (options.categories?.length) params.append('categories', options.categories.join(','));
  if (options.riskLevels?.length) params.append('risk_levels', options.riskLevels.join(','));
  if (options.daysBack) params.append('days_back', String(options.daysBack));

  const response = await fetch(`${API_BASE}/map-data?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch map data: ${response.statusText}`);
  }
  const data = await response.json();
  return data.hotspots;
}

export async function getCountriesData(topic?: string): Promise<CountryStats[]> {
  const params = new URLSearchParams();
  if (topic) params.append('topic', topic);

  const response = await fetch(`${API_BASE}/countries?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch countries data: ${response.statusText}`);
  }
  const data = await response.json();
  return data.countries;
}

export async function getHotspots(options: {
  topic?: string;
  categories?: ThreatCategory[];
  riskLevels?: RiskLevel[];
  countryCode?: string;
  page?: number;
  pageSize?: number;
  sortBy?: 'intensity' | 'articles' | 'recent' | 'name' | 'updated';
  sortOrder?: 'asc' | 'desc';
}): Promise<PaginatedResponse<Hotspot>> {
  const params = new URLSearchParams();
  if (options.topic) params.append('topic', options.topic);
  if (options.categories?.length) params.append('categories', options.categories.join(','));
  if (options.riskLevels?.length) params.append('risk_levels', options.riskLevels.join(','));
  if (options.countryCode) params.append('country_code', options.countryCode);
  if (options.page) params.append('page', String(options.page));
  if (options.pageSize) params.append('page_size', String(options.pageSize));
  if (options.sortBy) params.append('sort_by', options.sortBy);
  if (options.sortOrder) params.append('sort_order', options.sortOrder);

  const response = await fetch(`${API_BASE}/hotspots?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch hotspots: ${response.statusText}`);
  }
  const data = await response.json();
  return {
    data: data.hotspots,
    total: data.total,
    page: data.page,
    page_size: data.page_size,
    total_pages: data.total_pages,
  };
}

export async function getHotspotById(hotspotId: number): Promise<Hotspot> {
  const response = await fetch(`${API_BASE}/hotspot/${hotspotId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch hotspot: ${response.statusText}`);
  }
  return response.json();
}

export async function getHotspotArticles(
  hotspotId: number,
  page: number = 1,
  pageSize: number = 20
): Promise<PaginatedResponse<HotspotArticle>> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });

  const response = await fetch(`${API_BASE}/hotspot/${hotspotId}/articles?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch hotspot articles: ${response.statusText}`);
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

export async function getRegionsData(topic?: string): Promise<RegionData[]> {
  const params = new URLSearchParams();
  if (topic) params.append('topic', topic);

  const response = await fetch(`${API_BASE}/regions?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch regions data: ${response.statusText}`);
  }
  const data = await response.json();
  return data.regions;
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
