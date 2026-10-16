// Tab registry: one source for the tab bar, URL, breadcrumb, toolbar visibility (spec §5),
// generate-button label and Manage Tabs.
import type { IconName } from '@aunoo/ui';

export interface TabDef {
  id: string;
  label: string;
  icon: IconName;
  /** Configure / Tune / exports (PDF·PNG·Raw·References·Save) — spec §5 matrix. */
  toolbar: { configure: boolean; tune: boolean; exports: boolean } | null;
  /** Label of the context-row refresh/generate button. */
  generateLabel: string;
  /** Generator tabs start empty and use "Generate" rather than "Refresh". */
  generator?: boolean;
  /** Rebuilt on this page yet; the others link to the current page (/trend-convergence). */
  built?: boolean;
}

const REFRESH = 'Refresh analysis (bypass cache)';
const FULL = { configure: true, tune: true, exports: true };
/** Future Horizons has no prompt Tune here (the old page used a separate summary dialog). */
const GEN = { configure: true, tune: true, exports: false };

export const TABS: TabDef[] = [
  { id: 'strategic-recommendations', built: true, label: 'Strategic Recommendations', icon: 'Target', toolbar: FULL, generateLabel: REFRESH },
  { id: 'market-signals', built: true, label: 'Market Signals & Strategic Risks', icon: 'Warning', toolbar: FULL, generateLabel: REFRESH },
  { id: 'consensus', built: true, label: 'Consensus Analysis', icon: 'Scales', toolbar: FULL, generateLabel: REFRESH },
  { id: 'impact-timeline', built: true, label: 'Impact Timeline', icon: 'ClockCounterClockwise', toolbar: FULL, generateLabel: REFRESH },
  { id: 'future-horizons', built: true, label: 'Future Horizons', icon: 'TrendUp', toolbar: FULL, generateLabel: REFRESH },
  // Spec §5 recommends hiding the toolbar where its actions don't apply
  { id: 'topics', built: true, label: 'Topics', icon: 'Folder', toolbar: null, generateLabel: REFRESH },
  { id: 'forecast-tracker', built: true, label: 'Forecast Tracker', icon: 'ChartLineUp', toolbar: null, generateLabel: REFRESH },
  { id: 'topic-reports', built: true, label: 'Topic Reports', icon: 'FileText', toolbar: null, generateLabel: REFRESH },
  { id: 'extreme-outliers', built: true, label: 'Extreme Outliers', icon: 'Lightning', toolbar: GEN, generateLabel: 'Generate extreme outlier scenarios', generator: true },
  { id: 'focus-group', built: true, label: 'Focus Group', icon: 'ChatCentered', toolbar: GEN, generateLabel: 'Generate focus group personas', generator: true },
  { id: 'executive-briefing', built: true, label: 'Executive Briefing', icon: 'Notebook', toolbar: GEN, generateLabel: 'Generate executive briefing', generator: true },
  { id: 'situation-assessment', built: true, label: 'Situation Assessment', icon: 'Globe', toolbar: GEN, generateLabel: 'Generate situation assessment', generator: true },
  { id: 'newsletter', built: true, label: 'Newsletter', icon: 'Newspaper', toolbar: GEN, generateLabel: 'Generate newsletter', generator: true },
  { id: 'changelog', built: true, label: 'Changelog', icon: 'ListBullets', toolbar: null, generateLabel: REFRESH },
  { id: 'roadmap', built: true, label: 'Roadmap', icon: 'Flag', toolbar: null, generateLabel: REFRESH },
];

export const DEFAULT_TAB = TABS[0].id;
export const tabById = (id: string) => TABS.find((t) => t.id === id);
