import type { Confirm } from '@aunoo/shell';

/** What Explore passes to each analysis-module tab (GeoHotSpots, US Crisis Tracker, ScienceWatch, Threat Intelligence) */
export interface ModuleTabProps {
  /** The model picked in the Explore filter bar, for any AI run the reader starts */
  model: string;
  notify: (m: string) => void;
  askConfirm: (c: Confirm) => void;
}
