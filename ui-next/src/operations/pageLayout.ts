// Which page sections, metric cards and world clocks are shown, and in what order. Saved per browser.
import { useEffect, useState } from 'react';
import { isValidTimeZone } from './timezones';

export const SECTIONS = [
  { id: 'ticker', label: 'News ticker' },
  { id: 'status', label: 'System status' },
  { id: 'clock', label: 'World clock' },
  { id: 'totals', label: 'Statistics cards' },
] as const;

export const METRICS = [
  { id: 'cpu', label: 'CPU' },
  { id: 'memory', label: 'Memory' },
  { id: 'disk', label: 'Disk' },
  { id: 'apiKeys', label: 'API keys' },
  { id: 'polling', label: 'Auto-polling' },
  { id: 'database', label: 'Database' },
] as const;

export type SectionId = (typeof SECTIONS)[number]['id'];
export type MetricId = (typeof METRICS)[number]['id'];

export interface Clock {
  timeZone: string;
  city: string;
}

export interface PageLayout {
  clocks: Clock[];
  sections: Record<SectionId, boolean>;
  metricOrder: MetricId[];
  hiddenMetrics: MetricId[];
}

const STORAGE_KEY = 'aunoo.operationshq.layout';

const defaultClocks: Clock[] = [
  { city: 'San Francisco', timeZone: 'America/Los_Angeles' },
  { city: 'New York', timeZone: 'America/New_York' },
  { city: 'London', timeZone: 'Europe/London' },
  { city: 'Berlin', timeZone: 'Europe/Berlin' },
  { city: 'Moscow', timeZone: 'Europe/Moscow' },
  { city: 'Dubai', timeZone: 'Asia/Dubai' },
  { city: 'Beijing', timeZone: 'Asia/Shanghai' },
  { city: 'Tokyo', timeZone: 'Asia/Tokyo' },
];

/** Settings saved by the old page (same origin), used once when nothing is saved under the new key. */
function fromOldPage(): Partial<PageLayout> | null {
  const read = (key: string) => {
    try {
      return JSON.parse(window.localStorage.getItem(key) ?? 'null');
    } catch {
      return null;
    }
  };
  const clocks = read('worldClockTimezones') as { timezone?: string; city?: string }[] | null;
  const sections = read('operations_visibleSections') as Record<string, boolean> | null;
  const metrics = read('operations_visibleMetrics') as Record<string, boolean> | null;
  const order = read('operations_metricsOrder') as string[] | null;
  if (!clocks && !sections && !metrics && !order) return null;
  const rename = (id: string) => (id === 'autopolling' ? 'polling' : id) as MetricId;
  return {
    ...(Array.isArray(clocks) && { clocks: clocks.map((c) => ({ city: c.city ?? '', timeZone: c.timezone ?? '' })) }),
    ...(sections && {
      sections: {
        ticker: sections.ticker ?? true,
        status: sections.healthStatus ?? true,
        clock: sections.worldClock ?? true,
        totals: sections.statsCards ?? true,
      },
    }),
    ...(metrics && { hiddenMetrics: Object.entries(metrics).filter(([, shown]) => !shown).map(([id]) => rename(id)) }),
    ...(Array.isArray(order) && { metricOrder: order.map(rename) }),
  };
}

const DEFAULT_LAYOUT: PageLayout = {
  clocks: defaultClocks,
  sections: { ticker: true, status: true, clock: true, totals: true },
  metricOrder: METRICS.map((m) => m.id),
  hiddenMetrics: [],
};

/** Saved layout merged onto the defaults, so new sections/metrics still appear. */
function load(): PageLayout {
  try {
    const saved = (JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? 'null') as Partial<PageLayout> | null) ?? fromOldPage();
    if (!saved) return DEFAULT_LAYOUT;
    const known = new Set<string>(DEFAULT_LAYOUT.metricOrder);
    const order = (saved.metricOrder ?? []).filter((id) => known.has(id));
    const clocks = Array.isArray(saved.clocks)
      ? saved.clocks.filter((c): c is Clock => typeof c?.city === 'string' && isValidTimeZone(c?.timeZone))
      : DEFAULT_LAYOUT.clocks;
    return {
      clocks,
      sections: { ...DEFAULT_LAYOUT.sections, ...saved.sections },
      metricOrder: [...order, ...DEFAULT_LAYOUT.metricOrder.filter((id) => !order.includes(id))],
      hiddenMetrics: (saved.hiddenMetrics ?? []).filter((id) => known.has(id)),
    };
  } catch {
    return DEFAULT_LAYOUT;
  }
}

export function usePageLayout() {
  const [layout, setLayout] = useState(load);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(layout));
    } catch {
      // Storage unavailable (private mode) — the layout still works for this visit.
    }
  }, [layout]);

  return {
    layout,
    setSection: (id: SectionId, shown: boolean) =>
      setLayout((current) => ({ ...current, sections: { ...current.sections, [id]: shown } })),
    setMetricShown: (id: MetricId, shown: boolean) =>
      setLayout((current) => ({
        ...current,
        hiddenMetrics: shown ? current.hiddenMetrics.filter((m) => m !== id) : [...current.hiddenMetrics, id],
      })),
    setClocks: (clocks: Clock[]) => setLayout((current) => ({ ...current, clocks })),
    setMetricOrder: (ids: string[]) =>
      setLayout((current) => ({ ...current, metricOrder: ids as MetricId[] })),
  };
}
