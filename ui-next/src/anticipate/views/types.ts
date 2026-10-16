import type { Confirm } from '@aunoo/shell';
import type { TabDef } from '../lib/tabs';
import type { Analysis } from '../lib/useAnalysis';
import type { AnalysisConfig } from '../lib/useWorkspace';

export interface ViewProps {
  tab: TabDef;
  config: AnalysisConfig;
  analysis: Analysis;
  notify: (message: string) => void;
  navigate: (tabId: string) => void;
  /** Switch the page's topic (e.g. Topics → a topic's Forecast Tracker). */
  setTopic: (topic: string) => void;
  /** The page's confirm dialog. */
  askConfirm: (confirm: Confirm) => void;
  /** Lets a view open a dialog owned by the shell. */
  openConfigure: () => void;
}
