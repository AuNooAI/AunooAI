import { Text } from '@aunoo/ui';
import type { Coverage, MarketAnalyses } from '@monolith/marketMonitorApi';
import type { MmContext } from '../../../context';

/*
 * Every analysis panel says what it rests on. Most of them cover only part of the registry, and a
 * chart without its denominator invites the wrong conclusion: "one shared investor" reads as a
 * fragmented market when it really means half the Crunchbase pages are unread.
 */
export function CoverageLine({ coverage, note }: { coverage: Coverage; note?: string }) {
  // coverage.label is already a full clause ("81 of 83 vendors have a founding year")
  const label = coverage.label ? coverage.label[0].toUpperCase() + coverage.label.slice(1) : coverage.label;
  return (
    <Text variant="caption">
      {note ? `${note} ` : ''}
      {label}.{coverage.complete ? '' : ' Not every vendor is covered yet.'}
    </Text>
  );
}

/** What each panel gets: the shared context plus the one /analysis response */
export interface PanelProps {
  ctx: MmContext;
  data: MarketAnalyses;
}

/**
 * Hands a founding-year filter to the Vendors view. The frame has no slot for it, so it travels in
 * sessionStorage; the Vendors view reads and clears this key on mount.
 */
export const FOUNDED_FILTER_KEY = 'aunoo.mm.foundedFilter';
export function openFoundedYear(ctx: MmContext, year: string) {
  try {
    sessionStorage.setItem(FOUNDED_FILTER_KEY, year);
  } catch {
    // The Vendors view then opens unfiltered
  }
  ctx.goTo('vendors');
}

export const pct = (v: number | null | undefined, digits = 0) => (v === null || v === undefined ? '—' : `${(v * 100).toFixed(digits)}%`);
