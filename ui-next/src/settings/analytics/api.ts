import { api } from '../../shell';

/*
 * The reads behind the Analytics page, the same routes the old templates/analytics.html called.
 * All of them only read the database.
 */

export interface Distribution { labels: string[]; values: number[] }
export interface ByCategory { categories: string[]; data: Record<string, Record<string, number>>; sentiments?: string[]; future_signals?: string[] }
export interface Bubble { future_signal: string; sentiment?: string; time_to_impact?: string; count: number }
export interface SentimentPoint { date: string; sentiment: string; count: number }
export interface CategoryPoint { date: string; category: string; count: number }

export interface AnalyticsData {
  sentimentDistribution: Distribution;
  timeToImpactDistribution: Distribution;
  futureSignalDistribution: Distribution;
  sentimentByCategory: ByCategory;
  futureSignalByCategory: ByCategory;
  totalArticles: number;
  articlesBubbleChart: Bubble[];
  articlesFutureTimeBubbleChart: Bubble[];
  radarChartData: Bubble[];
  sentimentTimeSeries: SentimentPoint[];
  categoryTimeSeries: CategoryPoint[];
}

export interface TopicOptions { sentiments: string[]; futureSignals: string[]; timeToImpacts: string[]; driverTypes: string[] }

export interface Filters {
  topic: string;
  categories: string[];
  timeframe: string;
  curated: boolean;
  sentiments: string[];
  timeToImpacts: string[];
  driverTypes: string[];
}

export interface FlowRecord { source?: string | null; category?: string | null; sentiment?: string | null }

export const fetchTopics = () => api<{ name: string }[]>('/api/topics').then((t) => t.map((x) => x.name));
export const fetchTopicOptions = (topic: string) =>
  api<Partial<TopicOptions>>(`/api/topic-options/${encodeURIComponent(topic)}`).then((o) => ({
    sentiments: o.sentiments ?? [], futureSignals: o.futureSignals ?? [], timeToImpacts: o.timeToImpacts ?? [], driverTypes: o.driverTypes ?? [],
  }));
export const fetchCategories = (topic: string) => api<string[]>(`/api/categories/${encodeURIComponent(topic)}`);

export function fetchAnalytics(f: Filters) {
  const q = new URLSearchParams({ timeframe: f.timeframe, topic: f.topic, curated: String(f.curated) });
  f.categories.forEach((v) => q.append('category', v));
  f.sentiments.forEach((v) => q.append('sentiment', v));
  f.timeToImpacts.forEach((v) => q.append('timeToImpact', v));
  f.driverTypes.forEach((v) => q.append('driverType', v));
  return api<AnalyticsData>(`/api/analytics?${q}`);
}

/** At most 2,000 articles (the route's cap); the old page asked for the default 500 */
export function fetchFlow(timeframe: string, topic: string) {
  const q = new URLSearchParams({ timeframe, limit: '2000' });
  if (topic) q.append('topic', topic);
  return api<FlowRecord[]>(`/api/flow_data?${q}`);
}

export const TIMEFRAMES = [
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
  { value: '180', label: 'Last 180 days' },
  { value: '365', label: 'Last year' },
  { value: 'all', label: 'All time' },
];
