import { api } from '../../../shell';

/*
 * Threat Intelligence reads and writes on /api/threat-intelligence. A local copy of the calls the
 * old tab used (ui/src/services/threatIntelligenceApi.ts): that file can't be imported here because
 * it names a ThreatType type it never defines.
 */

const BASE = '/api/threat-intelligence';

export type SeverityLevel = 'critical' | 'high' | 'medium' | 'low' | 'info';
export type Trend = 'escalating' | 'stable' | 'declining';
export type ActorType = 'nation_state' | 'cybercrime' | 'hacktivist' | 'insider' | 'script_kiddie' | 'unknown';

export interface ThreatMapData {
  id: number;
  threat_name: string;
  threat_type: string;
  threat_subtype?: string | null;
  severity_level: SeverityLevel;
  severity_score: number;
  trend: Trend | null;
  threat_actor_name: string | null;
  attributed_country?: string | null;
  attributed_country_name?: string | null;
  target_countries?: string[] | null;
  latitude: number;
  longitude: number;
  target_industries?: string[] | null;
  article_count: number;
  first_seen_date?: string | null;
  last_seen_date?: string | null;
}

export interface ThreatSummary {
  id: number;
  threat_name: string;
  threat_type: string;
  severity_level: SeverityLevel;
  severity_score: number;
  threat_actor_name: string | null;
  article_count: number;
  trend: Trend | null;
}

export interface OverviewStats {
  total_threats: number;
  by_severity: Partial<Record<SeverityLevel, number>>;
  total_articles: number;
  recent_articles: number;
  total_actors: number;
  escalating_count: number;
  declining_count: number;
  new_threats: number;
  by_type: Record<string, number>;
  top_threats: ThreatSummary[];
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
}

export interface ActorThreat {
  id: number;
  threat_name: string;
  threat_type: string;
  severity_level: SeverityLevel;
  severity_score: number;
  trend: Trend | null;
  article_count: number;
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

export interface TimelinePoint {
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

export interface Paged<T> {
  data: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/** A stored AI briefing, as the server sends it */
export interface Narrative {
  id: number;
  narrative_text: string | null;
  executive_summary: string | null;
  threat_count: number | null;
  article_count: number | null;
  top_actors: string[] | null;
  model_used: string | null;
  topic: string | null;
  generated_at: string | null;
  period_start?: string | null;
  period_end?: string | null;
}

export interface AvailableTopic {
  topic: string;
  total_articles: number;
  unprocessed_count: number;
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

export interface ProcessResult {
  status: string;
  message: string;
  articles_processed: number;
  threats_created: number;
  threats_updated: number;
  articles_skipped: number;
  errors: number;
}

export interface Schedule {
  id: number;
  name: string;
  topic: string | null;
  batch_size: number;
  model: string | null;
  process_all: boolean;
  schedule_enabled: boolean;
  schedule_type: 'interval' | 'daily' | null;
  schedule_interval: number | null;
  schedule_unit: 'minutes' | 'hours' | 'days' | 'weeks' | null;
  schedule_time: string | null;
  last_run_at: string | null;
  next_run_at: string | null;
  last_run_status: string | null;
  last_run_error?: string | null;
  last_run_articles_processed?: number;
  last_run_threats_created?: number;
  run_count: number;
}

export interface ScheduleInput {
  name: string;
  topic?: string;
  batch_size: number;
  /** Left out, the server uses its default model */
  model?: string;
  schedule_enabled: boolean;
  schedule_type: 'interval' | 'daily';
  schedule_interval: number;
  schedule_unit: 'minutes' | 'hours' | 'days' | 'weeks';
  schedule_time: string;
}

const qs = (o: Record<string, string | number | boolean | undefined | null>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== '') p.append(k, String(v));
  return p.toString();
};
const paged = <T,>(r: Record<string, unknown>, key: string): Paged<T> => ({
  data: (r[key] as T[]) ?? [],
  total: Number(r.total ?? 0),
  page: Number(r.page ?? 1),
  page_size: Number(r.page_size ?? 0),
  total_pages: Number(r.total_pages ?? 1),
});

export const getOverview = (daysBack: number) => api<OverviewStats>(`${BASE}/overview?${qs({ days_back: daysBack })}`);

export const getMapData = (o: { daysBack: number; threatTypes: string[]; severityLevels: SeverityLevel[] }) =>
  api<{ threats: ThreatMapData[] }>(`${BASE}/map-data?${qs({
    days_back: o.daysBack,
    threat_types: o.threatTypes.join(',') || undefined,
    severity_levels: o.severityLevels.join(',') || undefined,
  })}`).then((r) => r.threats ?? []);

export const getActors = (actorType?: ActorType) =>
  api<Record<string, unknown>>(`${BASE}/actors?${qs({ actor_type: actorType, page: 1, page_size: 50, sort_by: 'threat_count', sort_order: 'desc' })}`).then((r) => paged<ThreatActor>(r, 'actors'));

export const getActorThreats = (actorId: number) =>
  api<Record<string, unknown>>(`${BASE}/actor/${actorId}/threats?${qs({ page: 1, page_size: 10 })}`).then((r) => paged<ActorThreat>(r, 'threats'));

export const getTimeline = (daysBack: number) => api<{ timeline: TimelinePoint[] }>(`${BASE}/timeline?${qs({ days_back: daysBack })}`).then((r) => r.timeline ?? []);
export const getDailyCounts = (daysBack: number) => api<{ daily_counts: DailyCount[] }>(`${BASE}/daily-counts?${qs({ days_back: daysBack })}`).then((r) => r.daily_counts ?? []);
export const getCategories = () => api<{ categories: CategoryData[] }>(`${BASE}/categories`).then((r) => r.categories ?? []);
export const getCategoryTrends = (daysBack = 90) =>
  api<{ trends: CategoryTrendPeriod[] }>(`${BASE}/category-trends?${qs({ days_back: daysBack, granularity: 'weekly' })}`).then((r) => r.trends ?? []);

export const getIOCs = () => api<Record<string, unknown>>(`${BASE}/iocs?${qs({ page: 1, page_size: 100 })}`).then((r) => paged<IOC>(r, 'iocs'));
export const getCampaigns = (activeOnly?: boolean) =>
  api<Record<string, unknown>>(`${BASE}/campaigns?${qs({ is_active: activeOnly, page: 1, page_size: 50 })}`).then((r) => paged<Campaign>(r, 'campaigns'));

export interface ArticleQuery {
  page: number;
  search?: string;
  severityLevel?: SeverityLevel;
  threatType?: string;
  threatId?: number;
  actorId?: number;
  campaignId?: number;
  sortBy: 'date' | 'title' | 'relevance' | 'severity';
  sortOrder: 'asc' | 'desc';
}
export const getArticles = (q: ArticleQuery) =>
  api<Record<string, unknown>>(`${BASE}/articles?${qs({
    page: q.page, page_size: 20, search: q.search, severity_level: q.severityLevel, threat_type: q.threatType,
    threat_id: q.threatId, actor_id: q.actorId, campaign_id: q.campaignId, sort_by: q.sortBy, sort_order: q.sortOrder,
  })}`).then((r) => paged<LinkedArticle>(r, 'articles'));

export const getNarratives = () => api<Record<string, unknown>>(`${BASE}/narratives?${qs({ page: 1, page_size: 20 })}`).then((r) => paged<Narrative>(r, 'data'));
export const deleteNarrative = (id: number) => api(`${BASE}/narratives/${id}`, { method: 'DELETE' });
/** Calls the AI: writes a briefing from the last seven days of threats */
export const generateNarrative = (model: string) =>
  api<{ narrative: Narrative }>(`${BASE}/generate-narrative`, { method: 'POST', json: { model } }).then((r) => r.narrative);

export const getAvailableTopics = () => api<{ topics: AvailableTopic[] }>(`${BASE}/available-topics`).then((r) => r.topics ?? []);
export const getProcessingStatus = () => api<ProcessingStatus>(`${BASE}/process-articles/status`);
/** Calls the AI on each article read */
export const processArticles = (body: { batch_size: number; model: string; topic?: string; process_all: boolean }) =>
  api<ProcessResult>(`${BASE}/process-articles`, { method: 'POST', json: body });

export const getSchedules = () => api<{ schedules: Schedule[] }>(`${BASE}/schedules`).then((r) => r.schedules ?? []);
export const createSchedule = (s: ScheduleInput) => api<Schedule>(`${BASE}/schedules`, { method: 'POST', json: s });
export const updateSchedule = (id: number, s: Partial<ScheduleInput>) => api<Schedule>(`${BASE}/schedules/${id}`, { method: 'PUT', json: s });
export const deleteSchedule = (id: number) => api(`${BASE}/schedules/${id}`, { method: 'DELETE' });
/** Calls the AI: runs the schedule's article processing now and waits for it */
export const runSchedule = (id: number) => api<ProcessResult>(`${BASE}/schedules/${id}/run`, { method: 'POST' });
