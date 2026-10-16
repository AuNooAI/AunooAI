// News ticker settings ("Latest" strip → gear). Saved per browser, like the page layout.
import { useEffect, useState } from 'react';
import type { SelectOption } from '@aunoo/ui';

export interface TickerSettings {
  count: string;
  range: string;
  speed: string;
  refresh: string;
  showSource: boolean;
  showTime: boolean;
  playOnLoad: boolean;
}

export const DEFAULT_TICKER: TickerSettings = {
  count: '15',
  range: '7d',
  speed: '120',
  refresh: '5',
  showSource: true,
  showTime: true,
  playOnLoad: true,
};

export const COUNT_OPTIONS: SelectOption[] = ['5', '10', '15', '20', '30'].map((n) => ({ value: n, label: `${n} articles` }));
export const RANGE_OPTIONS: SelectOption[] = [
  { value: '24h', label: 'Last 24 Hours' },
  { value: '72h', label: 'Last 3 Days' },
  { value: '7d', label: 'Last 7 Days' },
  { value: '30d', label: 'Last 30 Days' },
];
export const RANGE_MINUTES: Record<string, number> = { '24h': 1440, '72h': 4320, '7d': 10080, '30d': 43200 };
export const SPEED_OPTIONS: SelectOption[] = [
  { value: '30', label: 'Fast (30 seconds)' },
  { value: '60', label: 'Normal (60 seconds)' },
  { value: '120', label: 'Lazy (120 seconds)' },
];
export const REFRESH_OPTIONS: SelectOption[] = [
  { value: 'off', label: 'Off' },
  { value: '1', label: 'Every minute' },
  { value: '5', label: 'Every 5 minutes' },
  { value: '15', label: 'Every 15 minutes' },
  { value: '30', label: 'Every 30 minutes' },
];

const STORAGE_KEY = 'aunoo.operationshq.ticker';

function load(): TickerSettings {
  try {
    return { ...DEFAULT_TICKER, ...JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? '{}') };
  } catch {
    return DEFAULT_TICKER;
  }
}

export function useTickerSettings() {
  const [settings, setSettings] = useState(load);
  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    } catch {
      // Storage unavailable (private mode) — the settings still work for this visit.
    }
  }, [settings]);
  return [settings, setSettings] as const;
}
