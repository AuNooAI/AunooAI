import type { Confirm } from '@aunoo/shell';
import type {
  CollectionPlan, Market, MarketOverview, MarketPulse, SourceHealth, Vendor,
} from '@monolith/marketMonitorApi';
import type { VendorColours } from './shared/colours';
import type { DrilldownSpec } from './shared/Records';

/** The seven views, as on the old tab (ui/src/components/newsfeed/MarketMonitorTab.tsx). */
export type MmView = 'findings' | 'analysis' | 'voices' | 'horizon' | 'collection' | 'briefings' | 'vendors';
export type CollectionSub = 'overview' | 'health' | 'coverage' | 'wire' | 'data' | 'sourcemap';
export type SettingsPanel = 'collection' | 'sources' | 'health' | 'scope';

/**
 * What every Market Monitor view gets from the frame (MarketMonitor.tsx). The frame loads what the
 * header and several views share; each view loads anything else it needs itself, only while open.
 */
export interface MmContext {
  marketId: number;
  market: Market;
  /** Shared reporting window in days (7, 30, 90, 365) for Findings, Analysis, Voices, Coverage and Wire */
  periodDays: number;
  /** null while loading */
  vendors: Vendor[] | null;
  overview: MarketOverview | null;
  pulse: MarketPulse | null;
  plan: CollectionPlan | null;
  health: SourceHealth | null;
  colours: VendorColours;
  /** Reloads the shared data (after a save, or the Refresh button) */
  reload: () => void;
  notify: (message: string) => void;
  askConfirm: (c: Confirm) => void;
  /** Opens a vendor's own page (kept in the URL as ?vendor=) */
  openVendor: (brandId: number) => void;
  /** Lists the vendors behind an overview figure (kept in the URL as ?drill=), e.g. 'hiring' */
  openDrill: (name: string) => void;
  /** Lists the records behind a figure: posts, coverage, jobs, funding, investors or a voice's posts */
  openRecords: (spec: DrilldownSpec) => void;
  /** Switches view, and for Collection which sub-view */
  goTo: (view: MmView, sub?: CollectionSub) => void;
  openSettings: (panel: SettingsPanel) => void;
}

export const PERIOD_OPTIONS = [
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
  { value: '365', label: 'Last 365 days' },
];

/** Views the shared period applies to (founding years and funding are always all-time) */
export const usesPeriod = (view: MmView, sub: CollectionSub) =>
  view === 'findings' || view === 'analysis' || view === 'voices' || (view === 'collection' && (sub === 'coverage' || sub === 'wire'));
