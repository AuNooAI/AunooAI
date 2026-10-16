import type { CorpusArticle } from '@monolith/marketMonitorApi';

/*
 * Labels and grouping for the Collection view, copied from the old MarketMonitorTab.tsx.
 */

/** A vendor's own blog post is not a trade-press story, so the list says which is which */
export const CLASS_LABEL: Record<string, string> = {
  news: 'news', vendor: 'vendor blog', social: 'vendor post', discussion: 'practitioner', research: 'research',
};

/** Chip tone per kind of article: a vendor talking about itself is a different kind of evidence from a practitioner */
export const CLASS_TONE: Record<string, 'neutral' | 'warning' | 'info' | 'accent'> = {
  news: 'neutral', vendor: 'warning', social: 'warning', discussion: 'info', research: 'accent',
};

/** Plain words for the post review verdicts */
export const VERDICT_LABEL: Record<string, string> = { signal: 'announcement', commentary: 'opinion', noise: 'promotion' };

export const SEVERITY_TONE: Record<string, 'error' | 'warning' | 'neutral'> = { critical: 'error', high: 'error', medium: 'warning', low: 'neutral' };

/**
 * What each source collects and where it lands, for the Data Map. Fixed by the code
 * (app/services/brightdata_linkedin.py, app/tasks/market_monitor.py); cost and cadence are read live
 * from the source settings instead.
 */
export const SOURCE_MAP: { source: string; label: string; collects: string; landsIn: string; requires: string; manualOnly?: boolean }[] = [
  { source: 'linkedin_company_profile', label: 'LinkedIn profile', collects: 'Country, founding year, headcount, industry, description', landsIn: 'Vendor snapshot. Fills in a blank registry field (country, founded year, headcount) and never overwrites a value already on file.', requires: 'A LinkedIn company URL on file' },
  { source: 'linkedin_company_post', label: 'LinkedIn posts', collects: 'Post text, author, publish date, likes, comments and shares', landsIn: 'Articles, tagged as a vendor post', requires: 'A LinkedIn company URL on file' },
  { source: 'linkedin_jobs', label: 'LinkedIn jobs', collects: 'Open roles: title, location, seniority, function, posted date', landsIn: 'Job-posting snapshot', requires: 'A LinkedIn company URL on file' },
  { source: 'crunchbase_company', label: 'Crunchbase', collects: 'Funding rounds, investors, growth and heat score, operating status. No dollar amounts, because Crunchbase’s public record doesn’t carry them.', landsIn: 'Vendor snapshot, kept separate from the registry’s own funding total', requires: 'A Crunchbase URL on file (guessed from the company name if missing, then corrected)' },
  { source: 'pitchbook_company', label: 'PitchBook', collects: 'Headcount, total funding, last round, investors. Field names not yet checked against a live response.', landsIn: 'Vendor snapshot', requires: 'A PitchBook URL, entered by hand (no auto-discovery)' },
  { source: 'zoominfo_company', label: 'ZoomInfo', collects: 'Revenue, headcount, leadership, tech stack. Field names not yet checked against a live response.', landsIn: 'Vendor snapshot', requires: 'A ZoomInfo URL, entered by hand (no auto-discovery)' },
  { source: 'indeed_jobs', label: 'Indeed jobs', collects: 'Open roles, matched to the vendor by employer name. Not yet confirmed against a real response.', landsIn: 'Job-posting snapshot, pooled with LinkedIn jobs', requires: 'Run one vendor at a time from its page, never the whole registry', manualOnly: true },
  { source: 'vendor_web', label: 'Vendor web pages', collects: 'Page-by-page changes on pages already found for the vendor', landsIn: 'Page-state snapshot, only when something changed', requires: 'A page found by web-page discovery, below' },
  { source: 'vendor_web_discovery', label: 'Web-page discovery', collects: 'RSS and Atom feeds, and pages worth watching, on the vendor’s own site', landsIn: 'A feed added to the article collector; page URLs added for vendor web pages to watch', requires: 'A domain on file' },
  { source: 'funding_discovery', label: 'Funding scan', collects: 'Funding-round mentions in the news already collected', landsIn: 'The review queue, for a person to confirm before anything is written to the registry', requires: 'Nothing: it reads what collection already gathered' },
  { source: 'corpus_match', label: 'Corpus match', collects: 'Articles matching this market’s search terms, including ones collected under an unrelated topic', landsIn: 'Market articles', requires: 'Nothing: it reads what collection already gathered' },
  { source: 'post_review', label: 'Post review', collects: 'An AI check of vendor LinkedIn posts already collected, for whether they say what they claim', landsIn: 'A verdict attached to the post', requires: 'Nothing: it reads what collection already gathered' },
  { source: 'monthly_briefing', label: 'Monthly briefing', collects: 'Checks daily and writes a summary once a month', landsIn: 'Reports', requires: 'Nothing: it reads what collection already gathered' },
];

/** An article that names no vendor: the market talked about something without a tracked competitor being the subject */
export const NO_VENDOR = 'Market chatter';
/** Posts not judged to state a fact have no kind of their own, so they collect here rather than in a fake "other" */
export const NOT_ANNOUNCED = 'Not an announcement';

/** Reactions on a post. The card and the "most reactions" sort share this so they agree */
export function engagementOf(a: CorpusArticle): number {
  const sm = a.social_meta;
  if (!sm) return 0;
  return (sm.likes ?? 0) + (sm.comments ?? 0) + (sm.reposts ?? sm.shares ?? 0);
}

/** "Today", "Yesterday", a weekday inside the last week, else a date */
export function dayLabel(iso: string | null): string {
  if (!iso) return 'Undated';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'Undated';
  const startOf = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((startOf(new Date()) - startOf(d)) / 86400000);
  if (diff === 0) return 'Today';
  if (diff === 1) return 'Yesterday';
  if (diff > 1 && diff < 7) return d.toLocaleDateString('en-GB', { weekday: 'long' });
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: diff > 300 ? 'numeric' : undefined });
}

export interface CoverageGroup {
  key: string;
  label: string;
  items: CorpusArticle[];
  /** Vendor groups only, for the vendor's colour */
  brandId?: number;
}

/** One section per vendor, most covered first; articles naming no vendor get their own section */
export function groupByVendor(articles: CorpusArticle[]): CoverageGroup[] {
  const map = new Map<string, CoverageGroup>();
  for (const a of articles) {
    const v = a.vendors[0];
    const key = v ? `v${v.brand_id}` : 'no-vendor';
    if (!map.has(key)) map.set(key, { key, label: v ? v.vendor : NO_VENDOR, items: [], brandId: v?.brand_id });
    map.get(key)!.items.push(a);
  }
  return [...map.values()].sort((a, b) => b.items.length - a.items.length);
}

/** One section per day, newest first. A real group-by, so the "most reactions" sort doesn't split a day apart */
export function groupByDay(articles: CorpusArticle[]): CoverageGroup[] {
  const map = new Map<string, CoverageGroup>();
  for (const a of articles) {
    const label = dayLabel(a.published);
    if (!map.has(label)) map.set(label, { key: label, label, items: [] });
    map.get(label)!.items.push(a);
  }
  const newest = (g: CoverageGroup) => g.items.reduce((m, a) => ((a.published ?? '') > m ? a.published ?? '' : m), '');
  return [...map.values()].sort((a, b) => newest(b).localeCompare(newest(a)));
}

/** One section per kind of announcement (launch, partnership…); the residue goes last whatever its size */
export function groupByKind(articles: CorpusArticle[]): CoverageGroup[] {
  const map = new Map<string, CoverageGroup>();
  for (const a of articles) {
    const kind = a.review_verdict === 'signal' && a.review_kind ? a.review_kind : NOT_ANNOUNCED;
    if (!map.has(kind)) map.set(kind, { key: kind, label: kind === NOT_ANNOUNCED ? kind : kind.charAt(0).toUpperCase() + kind.slice(1), items: [] });
    map.get(kind)!.items.push(a);
  }
  return [...map.values()].sort((a, b) => (a.key === NOT_ANNOUNCED ? 1 : b.key === NOT_ANNOUNCED ? -1 : b.items.length - a.items.length));
}

export const fmtDateTime = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleString('en-GB') : 'never');
