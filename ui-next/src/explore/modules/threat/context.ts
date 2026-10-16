import type { Confirm } from '@aunoo/shell';
import type { OverviewStats, SeverityLevel, ThreatMapData } from './api';

export type ThreatTab = 'overview' | 'map' | 'timeline' | 'actors' | 'categories' | 'analysis' | 'insights' | 'articles';

/** What the Articles view is filtered to when another view sends the reader there */
export interface ArticleFilter {
  threat?: { id: number; name: string };
  actor?: { id: number; name: string };
  campaign?: { id: number; name: string };
  severity?: SeverityLevel;
  threatType?: string;
}

/** What every sub-view gets from the frame (ThreatIntel.tsx) */
export interface ThreatCtx {
  daysBack: number;
  model: string;
  stats: OverviewStats | null;
  /** Threats with a location, for the period and the map's filters */
  mapThreats: ThreatMapData[];
  loading: boolean;
  notify: (m: string) => void;
  askConfirm: (c: Confirm) => void;
  /** Opens Articles filtered to what the reader clicked */
  showArticles: (f: ArticleFilter) => void;
  openArticle: (a: { uri: string; title?: string | null; summary?: string | null; source?: string | null; publication_date?: string | null }) => void;
}
