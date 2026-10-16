import type { MarketFinding } from '@monolith/marketMonitorApi';

/*
 * Wording for a finding row, copied from the old MarketFindingsView.tsx. Pure functions, so they live
 * here rather than being imported from ui/src.
 */

/**
 * The headline without a leading "Vendor:" when that vendor is already shown as a chip. A LinkedIn
 * post with no first sentence of its own ("Kamal Shah: Prophet Security's Post", a bare link) gets
 * the first sentence of the summary instead, when there is one.
 */
export function headlineOf(f: MarketFinding): string {
  let h = (f.headline || '').trim();
  for (const v of f.vendors) {
    const prefix = `${v.vendor}:`;
    if (h.toLowerCase().startsWith(prefix.toLowerCase())) {
      const rest = h.slice(prefix.length).trim();
      if (rest) {
        h = rest;
        break;
      }
    }
  }
  const junk = /(’s|'s) Post$|https?:\/\/|^Full announcement/i;
  if (junk.test(h) && f.summary) {
    const first = f.summary.replace(/\s+/g, ' ').trim().split(/(?<=[.!?])\s+/)[0] || '';
    if (first && first.length >= 12 && !/https?:\/\//.test(first)) return first.length > 160 ? `${first.slice(0, 157)}…` : first;
  }
  return h;
}

/** Who is saying this, in words; `independent` when someone other than the vendor reported it */
export function saidBy(f: MarketFinding): { label: string; independent: boolean } {
  if (f.non_vendor_source_count > 0) {
    const n = f.non_vendor_source_count;
    return { label: n === 1 ? 'Reported by one outside source' : `Reported by ${n} outside sources`, independent: true };
  }
  if (f.corroboration === 'vendor_claim' || f.vendor_voiced) return { label: 'The vendor’s own claim', independent: false };
  if (f.corroboration === 'single_source') return { label: 'One source', independent: false };
  return { label: f.corroboration.replace(/_/g, ' '), independent: false };
}

export function whenOf(f: MarketFinding): string {
  const stamp = f.occurred_at || f.first_observed_at;
  if (!stamp) return 'date unknown';
  const d = new Date(stamp);
  if (Number.isNaN(d.getTime())) return 'date unknown';
  if (f.date_precision === 'month') return d.toLocaleDateString('en-GB', { year: 'numeric', month: 'short' });
  const text = d.toLocaleDateString('en-GB', { year: 'numeric', month: 'short', day: 'numeric' });
  return f.occurred_at ? text : `first seen ${text}`;
}

export function hostOf(uri: string | null | undefined): string {
  if (!uri) return '';
  try {
    const h = new URL(uri).hostname;
    return h.startsWith('www.') ? h.slice(4) : h;
  } catch {
    return '';
  }
}

export const MATERIALITY_LABEL: Record<string, string> = { high: 'Material', medium: 'Notable', low: 'Minor' };
const RANK: Record<string, number> = { high: 3, medium: 2, low: 1 };

/** "Notable and above" includes material findings (the old filter showed only the notable ones) */
export const meetsMateriality = (f: MarketFinding, floor: string) => floor === 'all' || (RANK[f.materiality] ?? 0) >= (RANK[floor] ?? 0);
