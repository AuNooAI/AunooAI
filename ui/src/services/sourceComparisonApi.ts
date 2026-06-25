/**
 * Source Comparison API — Existing news dataset vs Opoint, per brand.
 * Backed by GET /api/brand-watcher/source-comparison (reuses brand-watcher helpers).
 */
export { getBrands } from './brandWatcherApi';
export type { Brand } from './brandWatcherApi';

const BASE = '/api/brand-watcher';

export interface SCDomain { domain: string; articles: number; scholarly?: boolean }
export interface SCCountry { country: string; count: number }
export interface SCMonth { month: string; existing: number; opoint: number }
export interface SCDatasetSummary { articles: number; unique_sources: number; countries: number }

export interface SourceComparison {
  brand: string;
  topic: string;
  window_days: number;
  summary: { existing: SCDatasetSummary; opoint: SCDatasetSummary };
  top_domains: { existing: SCDomain[]; opoint: SCDomain[] };
  country_compare: { existing: SCCountry[]; opoint: SCCountry[] };
  monthly: SCMonth[];
  source_domains: { opoint: number; existing: number; opoint_only: number; shared: number; existing_only: number };
  enrichment_exclusive: Record<string, { opoint: number; existing: number }>;
  precision: { opoint_entity_verified: number; keyword_classified: number; wikidata_ids: string[] };
  chargeable_value: { min_relevance: number; opoint_total: number; on_brand: number; non_scholarly: number; chargeable: number; chargeable_with_reach: number; chargeable_rate_pct: number };
  relevance_histogram: { bucket: string; count: number }[];
  chargeable_samples: { title: string; url: string; source: string; relevance: number; rank_global: number | null }[];
  cost: { annual_eur: number; chargeable: number; annualized_chargeable: number; cost_per_chargeable_eur: number | null };
  sentiment_compare: { existing: { sentiment: string; count: number }[]; opoint: { sentiment: string; count: number }[] };
  media_type_compare: { existing: { media_type: string; count: number }[]; opoint: { media_type: string; count: number }[] };
  overlap: { shared: number; existing_only: number; opoint_only: number; opoint_only_domains: SCDomain[]; shared_domains: SCDomain[] };
}

export interface SCPortfolioRow { brand: string; existing_articles: number; opoint_articles: number; chargeable: number; annualized_chargeable: number; cost_per_chargeable_eur: number | null; chargeable_rate_pct: number }
export interface SCPortfolio { window_days: number; annual_cost: number; brands: SCPortfolioRow[]; totals: { existing_articles: number; opoint_articles: number; chargeable: number; annualized_chargeable: number; cost_per_chargeable_eur: number | null } }
export interface SCDomainArticle { uri: string; title: string; publication_date: string | null; sentiment: string | null; relevance: number | null; source: string }

export async function getPortfolio(daysBack = 365, annualCost = 20000): Promise<SCPortfolio> {
  const res = await fetch(`${BASE}/source-comparison/portfolio?days_back=${daysBack}&annual_cost=${annualCost}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`portfolio ${res.status}`);
  return res.json();
}

export async function getDomainArticles(brandId: number, domain: string, dataset: 'opoint' | 'existing', daysBack = 365): Promise<{ articles: SCDomainArticle[] }> {
  const p = new URLSearchParams({ brand_id: String(brandId), domain, dataset, days_back: String(daysBack), limit: '50' });
  const res = await fetch(`${BASE}/source-comparison/domain-articles?${p}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`domain-articles ${res.status}`);
  return res.json();
}

export function reportUrl(daysBack = 365, annualCost = 20000): string {
  return `${BASE}/source-comparison/report?days_back=${daysBack}&annual_cost=${annualCost}`;
}

export async function getSourceComparison(brandId: number, daysBack: number = 90, minRelevance: number = 0.4, annualCost: number = 20000): Promise<SourceComparison> {
  const params = new URLSearchParams({
    brand_id: String(brandId), days_back: String(daysBack),
    min_relevance: String(minRelevance), annual_cost: String(annualCost),
  });
  const res = await fetch(`${BASE}/source-comparison?${params}`, { credentials: 'include' });
  if (!res.ok) throw new Error(`Failed to get source comparison: ${res.status}`);
  return res.json();
}
