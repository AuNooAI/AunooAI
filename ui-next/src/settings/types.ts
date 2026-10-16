import type { Confirm } from '@aunoo/shell';

/** What the Settings frame passes to each page */
export interface SettingsPageProps {
  notify: (m: string) => void;
  askConfirm: (c: Confirm) => void;
}
