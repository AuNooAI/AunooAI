/**
 * Market Monitor API Service
 *
 * A market is a tracked vendor portfolio built on Brand Watcher brands. The
 * endpoints mirror app/routes/market_monitor_routes.py one for one.
 */

const BASE = '/api/market-monitor';

// ============================================================================
// Types
// ============================================================================

export interface Market {
  id: number;
  name: string;
  slug: string;
  question: string | null;
  description: string | null;
  enabled: boolean;
  is_public: boolean;
  vendors: number;
  collecting: number;
  public_vendors: number;
  created_at: string | null;
  updated_at: string | null;
  counts?: MarketCounts;
  open_review_tasks?: number;
}

export interface MarketCounts {
  vendors: number;
  excluded: number;
  collecting: number;
  public_vendors: number;
}

export interface VendorIdentifier {
  kind: string;
  value: string | null;
  normalized: string;
}

export interface VendorBaseline {
  source_row?: number;
  hq_country?: string | null;
  founded_year?: number | null;
  taxonomy?: { category?: string | null; sub_category?: string | null };
  /** The three funding states are distinct. A null amount under "Undisclosed"
   * means the raise was never disclosed — not that it was zero. */
  funding_baseline?: {
    status?: string | null;
    total_musd?: number | null;
    notes?: string | null;
  };
  metrics?: {
    employee_count?: number | null;
    employee_growth_ytd?: number | null;
  };
  analyst_note?: string | null;
  warnings?: string[];
}

export interface Vendor {
  brand_id: number;
  slug: string;
  display_name: string;
  role: 'vendor' | 'watch' | 'excluded';
  sort_order: number;
  is_public: boolean;
  collection_enabled: boolean;
  review_status: string;
  enabled: boolean;
  baseline: VendorBaseline;
  identifiers: VendorIdentifier[] | null;
}

export interface FacetValue { value: string; n: number }

export interface Facets {
  funding_status: FacetValue[];
  countries: FacetValue[];
  categories: FacetValue[];
  sub_categories: FacetValue[];
  roles: FacetValue[];
  totals: { total: number; collecting: number; public: number };
}

/** Every field optional; supplied fields are ANDed, values within one ORed.
 * An empty filter is refused by the server rather than read as "all". */
export interface VendorFilter {
  funding_status?: string[];
  countries?: string[];
  categories?: string[];
  sub_categories?: string[];
  roles?: string[];
  min_headcount?: number;
  max_headcount?: number;
  min_founded_year?: number;
  max_founded_year?: number;
  min_funding_musd?: number;
  has_linkedin?: boolean;
  brand_ids?: number[];
}

export interface CollectionToggleResult {
  dry_run: boolean;
  enabled: boolean;
  matched: number;
  would_change?: number;
  changed?: number;
  vendors: { brand_id: number; name: string; currently?: boolean }[];
}

export interface ReviewTask {
  id: number;
  brand_id: number | null;
  vendor: string | null;
  kind: string;
  severity: 'low' | 'medium' | 'high';
  status: 'open' | 'in_progress' | 'resolved' | 'dismissed';
  field: string | null;
  message: string;
  source_ref: Record<string, unknown>;
  created_at: string | null;
  resolved_at: string | null;
}

export interface SourceHealthRow {
  source: string;
  provider: string;
  runs: number;
  failed: number;
  succeeded: number;
  in_flight: number;
  last_success: string | null;
  last_attempt: string | null;
  records_new: number | null;
  records_received: number | null;
  cost: number | null;
  last_error: string | null;
  stale_hours: number | null;
  /** Ran and found nothing is healthy; never succeeded is not. */
  healthy: boolean;
  found_nothing: boolean;
}

export interface SourceHealth {
  market_id: number;
  sources: SourceHealthRow[];
  coverage: { collecting: number; without_linkedin: number };
  providers: {
    brightdata_linkedin_enabled: boolean;
    webhook_secret_set: boolean;
  };
}

export interface CollectionRun {
  id: number;
  brand_id: number | null;
  vendor: string | null;
  source: string;
  provider: string;
  job_id: string | null;
  status: string;
  records_received: number;
  records_new: number;
  records_skipped: number;
  started_at: string | null;
  completed_at: string | null;
  latency_ms: number | null;
  cost_amount: number | null;
  error: string | null;
}

export interface ImportReport {
  batch_id: string;
  ok: boolean;
  errors: string[];
  counts: {
    rows: number;
    active: number;
    excluded: number;
    websites: number;
    linkedin: number;
    aliases: number;
    review_tasks: number;
    review_tasks_by_severity: Record<string, number>;
    provenance_records: number;
    provenance_unmatched: number;
  };
  vendors: {
    row: number;
    display_name: string;
    slug: string;
    role: string;
    aliases: string[];
    former_names: string[];
    domain: string | null;
    linkedin_url: string | null;
    hq_country: string | null;
    founded_year: number | null;
    headcount: number | null;
    funding_status: string | null;
    total_funding_musd: number | null;
    warnings: string[];
  }[];
  review_tasks: {
    kind: string;
    severity: string;
    field: string | null;
    vendor: string | null;
    message: string;
  }[];
}

// ============================================================================
// Calls
// ============================================================================

async function jsonOrThrow(res: Response, what: string) {
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === 'string') detail = body.detail;
    } catch { /* keep the status */ }
    throw new Error(`${what}: ${detail}`);
  }
  return res.json();
}

export async function getMarkets(): Promise<Market[]> {
  return jsonOrThrow(await fetch(`${BASE}/markets`, { credentials: 'include' }),
    'Failed to load markets');
}

export async function getMarket(id: number): Promise<Market> {
  return jsonOrThrow(await fetch(`${BASE}/markets/${id}`, { credentials: 'include' }),
    'Failed to load market');
}

export async function createMarket(body: {
  name: string; question?: string; description?: string;
}): Promise<Market> {
  return jsonOrThrow(await fetch(`${BASE}/markets`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }), 'Failed to create market');
}

export async function getVendors(
  marketId: number,
  opts: { role?: string; collectingOnly?: boolean } = {},
): Promise<Vendor[]> {
  const params = new URLSearchParams();
  if (opts.role) params.set('role', opts.role);
  if (opts.collectingOnly) params.set('collecting_only', 'true');
  const qs = params.toString();
  return jsonOrThrow(await fetch(
    `${BASE}/markets/${marketId}/vendors${qs ? `?${qs}` : ''}`,
    { credentials: 'include' }), 'Failed to load vendors');
}

export async function getFacets(marketId: number): Promise<Facets> {
  return jsonOrThrow(await fetch(`${BASE}/markets/${marketId}/vendors/facets`,
    { credentials: 'include' }), 'Failed to load facets');
}

/** Defaults to a dry run on the server too — pass dryRun false deliberately. */
export async function setVendorCollection(
  marketId: number, enabled: boolean, filter: VendorFilter, dryRun = true,
): Promise<CollectionToggleResult> {
  return jsonOrThrow(await fetch(`${BASE}/markets/${marketId}/vendors/collection`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled, filter, dry_run: dryRun }),
  }), 'Failed to change collection');
}

export async function setVendorVisibility(
  marketId: number, brandIds: number[], isPublic: boolean,
): Promise<{ updated: number }> {
  return jsonOrThrow(await fetch(`${BASE}/markets/${marketId}/vendors/visibility`, {
    method: 'PUT', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ brand_ids: brandIds, is_public: isPublic }),
  }), 'Failed to change visibility');
}

export async function getReviewTasks(
  marketId: number, opts: { status?: string; severity?: string } = {},
): Promise<ReviewTask[]> {
  const params = new URLSearchParams();
  if (opts.status) params.set('status', opts.status);
  if (opts.severity) params.set('severity', opts.severity);
  const qs = params.toString();
  return jsonOrThrow(await fetch(
    `${BASE}/markets/${marketId}/review-tasks${qs ? `?${qs}` : ''}`,
    { credentials: 'include' }), 'Failed to load review tasks');
}

export async function updateReviewTask(
  marketId: number, taskId: number, status: ReviewTask['status'],
): Promise<void> {
  await jsonOrThrow(await fetch(
    `${BASE}/markets/${marketId}/review-tasks/${taskId}`, {
      method: 'PUT', credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, resolution: {} }),
    }), 'Failed to update review task');
}

export async function getSourceHealth(marketId: number): Promise<SourceHealth> {
  return jsonOrThrow(await fetch(`${BASE}/markets/${marketId}/source-health`,
    { credentials: 'include' }), 'Failed to load source health');
}

export async function getRuns(marketId: number, limit = 50): Promise<CollectionRun[]> {
  return jsonOrThrow(await fetch(`${BASE}/markets/${marketId}/runs?limit=${limit}`,
    { credentials: 'include' }), 'Failed to load runs');
}

export async function startRun(marketId: number, source: string):
  Promise<{ run_id: number; status: string; source: string }> {
  return jsonOrThrow(await fetch(`${BASE}/markets/${marketId}/runs`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source }),
  }), 'Failed to queue run');
}

export async function validateImport(file: File): Promise<ImportReport> {
  const form = new FormData();
  form.append('file', file);
  return jsonOrThrow(await fetch(`${BASE}/markets/import/validate`, {
    method: 'POST', credentials: 'include', body: form,
  }), 'Validation failed');
}

export async function commitImport(
  marketId: number, file: File, batchId: string,
): Promise<Record<string, unknown>> {
  const form = new FormData();
  form.append('file', file);
  form.append('market_id', String(marketId));
  form.append('batch_id', batchId);
  return jsonOrThrow(await fetch(`${BASE}/markets/import/commit`, {
    method: 'POST', credentials: 'include', body: form,
  }), 'Import failed');
}

export interface CollectionPlan {
  /** The market's own search language — what the category is called. */
  market_terms: string[];
  /** Terms past the 30-character cap, and what they will really be searched
   * as. A term that quietly broadens is worse than one refused. */
  truncated?: { term: string; searched_as: string }[];
  /** Vendor names, per the vendor_names mode. */
  vendor_keywords: string[];
  vendor_names: 'none' | 'funded' | 'all';
  funded_vendors?: number;
  error?: string;
  keywords: string[];
  /** Names too short or too ordinary to search alone; a qualifier was added
   * so the collector demands both words. */
  qualified: string[];
  skipped: string[];
  vendors: number;
  qualifier: string;
  group_name: string;
  topic_name: string;
  dry_run?: boolean;
  group_id?: number;
  group_created?: boolean;
  topic_created?: boolean;
  keywords_written?: number;
  existing?: {
    group_id: number; group_name: string; topic_name: string;
    keywords: number; qualifier: string;
  } | null;
}

export async function getCollectionPlan(
  marketId: number, vendorNames: 'none' | 'funded' | 'all' = 'funded',
  qualifier = 'security',
): Promise<CollectionPlan> {
  const params = new URLSearchParams({ qualifier, vendor_names: vendorNames });
  return jsonOrThrow(await fetch(
    `${BASE}/markets/${marketId}/collection-plan?${params}`,
    { credentials: 'include' }), 'Failed to load collection plan');
}

export async function setCollectionTerms(
  marketId: number, terms: string[],
): Promise<{ terms: string[]; truncated: { term: string; searched_as: string }[] }> {
  return jsonOrThrow(await fetch(`${BASE}/markets/${marketId}/collection-terms`, {
    method: 'PUT', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ terms }),
  }), 'Failed to save terms');
}

export async function setupCollection(
  marketId: number, opts: {
    qualifier?: string; vendorNames?: 'none' | 'funded' | 'all'; dryRun?: boolean;
  } = {},
): Promise<CollectionPlan> {
  return jsonOrThrow(await fetch(`${BASE}/markets/${marketId}/collection-setup`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      qualifier: opts.qualifier ?? 'security',
      vendor_names: opts.vendorNames ?? 'funded',
      dry_run: opts.dryRun ?? true,
    }),
  }), 'Failed to set up collection');
}

export interface CandidateVendor {
  name: string;
  amount_musd: number | null;
  round: string | null;
  matched_by: string;
  mentions: number;
  article_uri: string;
  article_title: string | null;
  news_source: string | null;
  published: string | null;
}

export interface DiscoveryResult {
  scanned: number;
  /** Articles in the topic but below the relevance floor. Reported so a zero
   * result reads as "nothing relevant" rather than "nothing collected". */
  below_alignment_floor?: number;
  min_alignment?: number;
  candidates: number;
  written?: number;
  days: number;
  topic?: string;
  error?: string;
  proposals: CandidateVendor[];
}

/** Reads the market's own funding coverage for companies not in the registry.
 * Costs nothing external — it re-reads articles already collected. */
export async function discoverCandidates(
  marketId: number, days = 14, dryRun = false,
): Promise<DiscoveryResult> {
  const params = new URLSearchParams({ days: String(days), dry_run: String(dryRun) });
  return jsonOrThrow(await fetch(
    `${BASE}/markets/${marketId}/discover?${params}`,
    { method: 'POST', credentials: 'include' }), 'Discovery failed');
}

// ============================================================================
// Timeline
// ============================================================================
//
// The market is a scope in the shared timeline (`scope_type: 'topic'`,
// `scope_id` = its collection topic), the same machinery brands use. Nothing
// market-specific here beyond knowing which scope to ask for.

export interface TimelineEvent {
  id: number;
  event_type: string;
  event_subtype: string | null;
  title: string;
  description: string | null;
  significance: 'low' | 'medium' | 'high' | 'critical';
  entities: unknown;
  article_uris: string[] | null;
  article_count: number;
  event_date: string;
  occurrence_count: number;
  granularity: string;
}

export async function getMarketTimeline(
  topicName: string, limit = 50,
): Promise<{ total: number; events: TimelineEvent[] }> {
  const params = new URLSearchParams({
    scope_type: 'topic', scope_id: topicName, limit: String(limit),
  });
  return jsonOrThrow(await fetch(`/api/timeline/events?${params}`,
    { credentials: 'include' }), 'Failed to load timeline');
}

/** Extract events for the last N days. Only the two most recent days use the
 * LLM, so a wide backfill stays cheap. */
export async function generateMarketTimeline(
  topicName: string, daysBack = 3,
): Promise<{ articles_processed: number; events_created: number;
             events_deduplicated: number }> {
  return jsonOrThrow(await fetch('/api/timeline/generate', {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      scope_type: 'topic', scope_id: topicName, days_back: daysBack,
      use_llm: true,
    }),
  }), 'Failed to generate timeline');
}

// ============================================================================
// Brief, dataset, sources
// ============================================================================

export interface BriefEvent {
  title: string;
  description: string | null;
  event_type: string;
  significance: 'low' | 'medium' | 'high' | 'critical';
  event_date: string;
  article_count: number;
}

export interface HeadcountMover {
  vendor: string;
  was: number;
  now_count: number;
  delta: number;
  pct: number | null;
}

export interface MarketBrief {
  market: string;
  question: string | null;
  period_days: number;
  generated_at: string;
  standing_summary: string | null;
  events: BriefEvent[];
  headcount_movers: HeadcountMover[];
  loudest_vendors: { vendor: string; posts: number }[];
  coverage: { watching: number; registry: number; paused: number };
  open_questions: { severity: string; kind: string; n: number }[];
}

export async function getBrief(marketId: number, days = 7): Promise<MarketBrief> {
  return jsonOrThrow(await fetch(`${BASE}/markets/${marketId}/brief?days=${days}`,
    { credentials: 'include' }), 'Failed to load brief');
}

export interface DatasetRow { [key: string]: unknown }

export async function getDataset(
  marketId: number,
): Promise<{ rows: number; columns: string[]; data: DatasetRow[] }> {
  return jsonOrThrow(await fetch(`${BASE}/markets/${marketId}/dataset`,
    { credentials: 'include' }), 'Failed to load dataset');
}

export function datasetCsvUrl(marketId: number): string {
  return `${BASE}/markets/${marketId}/dataset?fmt=csv`;
}

export function feedUrl(marketId: number): string {
  return `${BASE}/markets/${marketId}/feed.xml`;
}

export interface SourceSetting {
  source: string;
  paid: boolean;
  enabled: boolean;
  interval_hours: number | null;
  default_interval_hours: number;
  effective_interval_hours: number;
  last_success: string | null;
}

export async function getSources(
  marketId: number,
): Promise<{ sources: SourceSetting[]; min_interval_hours: number }> {
  return jsonOrThrow(await fetch(`${BASE}/markets/${marketId}/sources`,
    { credentials: 'include' }), 'Failed to load sources');
}

export async function saveSources(
  marketId: number,
  settings: Record<string, { enabled: boolean; interval_hours?: number | null }>,
): Promise<unknown> {
  return jsonOrThrow(await fetch(`${BASE}/markets/${marketId}/sources`, {
    method: 'PUT', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  }), 'Failed to save sources');
}

// ============================================================================
// One vendor, everything we hold
// ============================================================================

export interface VendorIdentifier2 {
  kind: string;
  display_value: string | null;
  normalized_value: string;
  provenance: Record<string, unknown>;
  verified: boolean;
  /** Superseded identifiers are kept and shown on demand — a corrected
   * identifier is part of how the registry got here. */
  live: boolean;
  valid_to: string | null;
}

export interface ProfileReading {
  observed_at: string;
  employee_count: number | null;
  followers: number | null;
}

export interface WatchedPage {
  url: string;
  observed_at: string;
  kind: string | null;
  title: string | null;
  http_status: string | null;
  diff: {
    added: string[]; removed: string[];
    added_count: number; removed_count: number; material: boolean;
  } | null;
}

export interface VendorDetail {
  brand_id: number;
  slug: string;
  display_name: string;
  role: string;
  collection_enabled: boolean;
  is_public: boolean;
  review_status: string;
  enabled: boolean;
  baseline: VendorBaseline;
  identifiers: VendorIdentifier2[];
  profile_series: ProfileReading[];
  funding: Record<string, any> | null;
  pages: WatchedPage[];
  jobs: { title: string; location: string | null; seniority: string | null;
          function: string | null; posted_date: string | null; url: string | null }[];
  posts: { uri: string; title: string; summary: string | null;
           publication_date: string | null; url: string | null }[];
  coverage_by_category: { category: string; n: number }[];
  recent_coverage: { uri: string; title: string; news_source: string | null;
                     publication_date: string | null; sentiment: string | null;
                     url: string | null }[];
  review_tasks: { id: number; kind: string; severity: string; status: string;
                  field: string | null; message: string }[];
  feeds: { name: string; url: string; is_active: boolean;
           last_checked_at: string | null; articles_fetched: number }[];
}

export async function getVendorDetail(
  marketId: number, brandId: number,
): Promise<VendorDetail> {
  return jsonOrThrow(await fetch(`${BASE}/markets/${marketId}/vendors/${brandId}`,
    { credentials: 'include' }), 'Failed to load vendor');
}
