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
  cost: { annual_eur: number; chargeable: number; cost_per_chargeable_eur: number | null };
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
