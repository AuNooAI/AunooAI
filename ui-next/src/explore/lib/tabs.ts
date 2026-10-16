import type { IconName } from '@aunoo/ui';

export interface ExploreTab {
  id: string;
  label: string;
  icon: IconName;
  /** The old page's tab id (ui/src/pages/NewsFeedPage.tsx), used to open it there until this tab is rebuilt */
  oldId: string;
  /** Shown only when this analysis module is switched on (/api/modules tab_id) */
  module?: string;
  /** Shown on a dedicated Brand Watcher site (the old page's DEDICATED_TABS) */
  dedicated?: boolean;
  /** Hidden on a dedicated Brand Watcher site */
  fullOnly?: boolean;
  /** Rebuilt here; the others open on the old page */
  built?: boolean;
}

/** In the old page's order. Module tabs appear only when their module is on. */
export const TABS: ExploreTab[] = [
  { id: 'overview', label: 'Overview', icon: 'SquaresFour', oldId: 'overview', fullOnly: true, built: true },
  { id: 'news-feed', label: 'News Feed', icon: 'Newspaper', oldId: 'feed', fullOnly: true, built: true },
  { id: 'geohotspots', label: 'GeoHotSpots', icon: 'Globe', oldId: 'geopolitical', module: 'geopolitical', built: true },
  { id: 'us-crisis-tracker', label: 'US Crisis Tracker', icon: 'Scales', oldId: 'policy', module: 'policy', built: true },
  { id: 'sciencewatch', label: 'ScienceWatch', icon: 'Flask', oldId: 'science', module: 'science', built: true },
  { id: 'brand-watcher', label: 'Brand Watcher', icon: 'Megaphone', oldId: 'brand_watcher', module: 'brand_watcher', dedicated: true, built: true },
  { id: 'market-monitor', label: 'Market Monitor', icon: 'ChartLineUp', oldId: 'market_monitor', module: 'market_monitor', dedicated: true, built: true },
  { id: 'threat-intelligence', label: 'Threat Intelligence', icon: 'ShieldCheck', oldId: 'threat_intel', module: 'threat_intel', built: true },
  { id: 'swiss-election', label: 'Swiss Election Watch', icon: 'Flag', oldId: 'swiss_disinfo', module: 'swiss_disinfo', built: true },
  { id: 'emerging-topics', label: 'Emerging Topics', icon: 'TrendUp', oldId: 'emerging', fullOnly: true, built: true },
  { id: 'observer-agents', label: 'Observer Agents', icon: 'Eye', oldId: 'agents', dedicated: true, built: true },
  { id: 'timeline', label: 'Timeline', icon: 'ClockCounterClockwise', oldId: 'timeline', dedicated: true, built: true },
  { id: 'briefing-desk', label: 'Briefing Desk', icon: 'Notebook', oldId: 'briefing-desk', dedicated: true, built: true },
  { id: 'saved', label: 'Saved', icon: 'BookmarkSimple', oldId: 'saved', fullOnly: true, built: true },
];

export const tabById = (id: string) => TABS.find((t) => t.id === id);
