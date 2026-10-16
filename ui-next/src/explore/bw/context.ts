import type { Confirm } from '@aunoo/shell';
import type { Brand } from '@monolith/brandWatcherApi';
import type { useBrandWatcher } from './useBrandWatcher';

export type BrandWatcherData = ReturnType<typeof useBrandWatcher>;

export type BwTabId =
  | 'dashboard' | 'analysis' | 'perception' | 'voices' | 'comparison' | 'insights' | 'articles'
  | 'social' | 'accounts' | 'workforce' | 'incidents' | 'help';

/**
 * What every Brand Watcher sub-tab gets from the frame (BrandWatcher.tsx). Sub-tabs load their own
 * extra data; the shared data (brands, stats, categories, temporal, articles…) lives in `bw`.
 */
export interface BwContext {
  bw: BrandWatcherData;
  /** Brands picked in the header; empty = all brands */
  selectedBrands: Brand[];
  /** The one brand most views focus on: the single picked brand, else the primary, else the first */
  focusBrand: Brand | null;
  notify: (message: string) => void;
  askConfirm: (c: Confirm) => void;
  /** Opens an article in the shared details sheet (uri alone is enough) */
  openArticle: (a: { uri: string; title?: string } & Record<string, unknown>) => void;
  /** Switches sub-tab, optionally changing filters first (e.g. a category click → Articles) */
  goTo: (tab: BwTabId, patch?: Partial<BrandWatcherData['config']>) => void;
  /** Opens the Five Signals screening dialog for an article (Articles fork owns the dialog) */
  openSignals: (a: { uri: string; title?: string; brand_id?: number | null }) => void;
  /** Site switch for the Voices view (/api/modules features.bw_voices) */
  voicesEnabled: boolean;
}

export const DAYS_OPTIONS = [
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
  { value: '180', label: 'Last 6 months' },
  { value: '365', label: 'Last year' },
  { value: '0', label: 'All time' },
];

export const periodLabel = (days: number) => (days === 0 ? 'all time' : days === 365 ? 'the last year' : `the last ${days} days`);
