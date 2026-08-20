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
  /** Whether this vendor is also a Brand Watcher brand in its own right. */
  brand_monitoring_enabled: boolean;
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
  field?: VendorSwitch;
  keywords_rewritten?: number;
  dry_run: boolean;
  enabled: boolean;
  matched: number;
  would_change?: number;
  changed?: number;
  vendors: { brand_id: number; name: string; currently?: boolean }[];
}

export interface ReviewTask {
  /** The baseline key this task is about, when it is about one. Null means the
   *  task can be accepted or dismissed but not corrected from the queue. */
  target_field: string | null;
  /** fixed | accepted | dismissed | superseded — set once resolved. */
  outcome: string | null;
  /** What the registry currently holds for target_field. */
  current_value: string | null;
  auto_closed_at: string | null;
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
  /** Only set when the most recent run is the one that failed. */
  last_error: string | null;
  stale_hours: number | null;
  /** State of the most recent run, not a tally over the window. */
  state: 'healthy' | 'failing' | 'in_flight' | 'unknown';
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
/** Which switch to throw. `collection` is whether we spend on watching a
 *  vendor; `brand_monitoring` is whether it appears in Brand Watcher as a
 *  brand in its own right. They are independent. */
export type VendorSwitch = 'collection' | 'brand_monitoring';

/** Every vendor in scope. The API refuses an empty filter on purpose — an
 *  empty rule must not silently mean "all" — so "all" is stated as the two
 *  in-scope roles, which leaves anything marked excluded alone. */
export const ALL_IN_SCOPE: VendorFilter = { roles: ['vendor', 'watch'] };

export async function setVendorCollection(
  marketId: number, enabled: boolean, filter: VendorFilter, dryRun = true,
  field: VendorSwitch = 'collection',
): Promise<CollectionToggleResult> {
  return jsonOrThrow(await fetch(`${BASE}/markets/${marketId}/vendors/collection`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled, filter, dry_run: dryRun, field }),
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
           publication_date: string | null; url: string | null;
           social_meta: Record<string, any> | null }[];
  /** Posts the review pass judged to state a fact, with what kind. */
  announcements: { uri: string; title: string; publication_date: string | null;
                   url: string | null; review_kind: string | null;
                   review_reason: string | null }[];
  post_verdicts: Record<string, number>;
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

// ============================================================================
// Overview and corpus
// ============================================================================

export interface MarketOverview {
  market: string;
  market_id: number;
  question: string | null;
  period_days: number;
  generated_at: string;
  coverage: {
    registry: number; excluded: number; watching: number;
    paused: number; observed: number;
  };
  funding: {
    disclosed: number; undisclosed: number; total_musd: number | null;
  };
  top_funded: { vendor: string; brand_id: number; musd: number | null;
                last_round: string | null }[];
  most_active: { brand_id: number; vendor: string; posts: number;
                 jobs: number; articles: number; signals: number }[];
  quiet_vendors: number;
  corpus: CorpusSummary | Record<string, never>;
  last_runs: { source: string; status: string; records_received: number;
               started_at: string | null; completed_at: string | null;
               error: string | null }[];
  latest_events: { id: number; title: string; event_type: string;
                   significance: string; event_date: string;
                   article_count: number | null }[];
}

/** What kind of thing an article is. A vendor's own blog post and a trade-press
 * story are not the same evidence, so the feed and the UI keep them apart. */
export type ArticleClass = 'news' | 'vendor' | 'social' | 'discussion'
  | 'research';

export interface CorpusSummary {
  by_class: Record<ArticleClass, number>;
  by_verdict: Record<string, number>;
  signal_kinds: { kind: string; n: number }[];
  total: number;
  /** Matched and collected under the market's own topic. */
  collected: number;
  /** Matched from articles collected for some other topic — the ones a
   * vendor-name classifier can never find. */
  corpus: number;
  last_scan: string | null;
  recent_days: number;
  recent: number;
  top_terms: { term: string; n: number }[];
  top_sources: { source: string; n: number }[];
  by_week: { week: string; n: number }[];
  collection_terms?: string[];
  context_terms?: string[];
}

export interface CorpusArticle {
  uri: string;
  title: string;
  summary: string | null;
  news_source: string | null;
  topic: string | null;
  published: string | null;
  sentiment: string | null;
  category: string | null;
  analyzed: boolean | null;
  score: number;
  matched_terms: string[];
  origin: 'collected' | 'corpus';
  article_class: ArticleClass;
  title_terms: number;
  /** Author, platform and engagement for a social post; null otherwise. */
  social_meta: {
    author?: string; author_name?: string; platform?: string;
    likes?: number; comments?: number; reposts?: number; shares?: number;
    thumbnail?: string; hashtags?: string[]; post_type?: string;
  } | null;
  /** Vendors this article is attributed to. */
  vendors: { brand_id: number; vendor: string }[];
  /** Present when other coverage says the same thing. */
  cluster?: {
    size: number;
    others: { uri: string; title: string | null; news_source: string | null;
              published: string | null; article_class: string;
              author?: string | null }[];
  };
  /** Set on vendor posts that were read by the review pass. */
  review_verdict: 'signal' | 'commentary' | 'noise' | null;
  review_kind: string | null;
  review_reason: string | null;
}

export async function getOverview(
  marketId: number, days = 30,
): Promise<MarketOverview> {
  return jsonOrThrow(
    await fetch(`${BASE}/markets/${marketId}/overview?days=${days}`,
      { credentials: 'include' }), 'Failed to load overview');
}

export async function getCorpusSummary(
  marketId: number, days = 30,
): Promise<CorpusSummary> {
  return jsonOrThrow(
    await fetch(`${BASE}/markets/${marketId}/corpus/summary?days=${days}`,
      { credentials: 'include' }), 'Failed to load corpus summary');
}

export async function getCorpusArticles(
  marketId: number,
  opts: { limit?: number; offset?: number; days?: number;
          origin?: string; classes?: string; minScore?: number;
          allPosts?: boolean; vendorId?: number; group?: boolean } = {},
): Promise<{ articles: CorpusArticle[]; limit: number; offset: number;
             grouped: boolean; has_more: boolean }> {
  const q = new URLSearchParams();
  if (opts.limit) q.set('limit', String(opts.limit));
  if (opts.offset) q.set('offset', String(opts.offset));
  if (opts.days) q.set('days', String(opts.days));
  if (opts.origin) q.set('origin', opts.origin);
  if (opts.classes) q.set('classes', opts.classes);
  if (opts.allPosts) q.set('all_posts', 'true');
  if (opts.vendorId) q.set('vendor_id', String(opts.vendorId));
  if (opts.group === false) q.set('group', 'false');
  if (opts.minScore !== undefined) q.set('min_score', String(opts.minScore));
  return jsonOrThrow(
    await fetch(`${BASE}/markets/${marketId}/corpus?${q}`,
      { credentials: 'include' }), 'Failed to load corpus');
}

export async function scanCorpus(
  marketId: number,
  body: { days?: number; limit?: number; min_score?: number;
          dry_run?: boolean } = {},
): Promise<{ terms: number; scanned: number; matched: number;
             inserted: number; updated: number; below_min_score: number;
             truncated: boolean; dry_run: boolean }> {
  return jsonOrThrow(await fetch(`${BASE}/markets/${marketId}/corpus/scan`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }), 'Corpus scan failed');
}

// ============================================================================
// Post review and the data inventory
// ============================================================================

export interface PostReviewResult {
  model: string;
  candidates: number;
  reviewed: number;
  batches: number;
  failed_batches: number;
  dry_run: boolean;
  counts: { signal: number; commentary: number; noise: number };
  samples: { vendor?: string; title?: string; kind?: string; reason?: string }[];
}

export async function reviewPosts(
  marketId: number,
  body: { limit?: number; batch?: number; days?: number;
          redo?: boolean; dry_run?: boolean } = {},
): Promise<PostReviewResult> {
  return jsonOrThrow(await fetch(`${BASE}/markets/${marketId}/posts/review`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }), 'Post review failed');
}

export interface DatasetInfo {
  dataset: string;
  description: string;
  rows: number;
  last_updated: string | null;
}

export async function getDataInventory(
  marketId: number,
): Promise<{ datasets: DatasetInfo[] }> {
  return jsonOrThrow(await fetch(`${BASE}/markets/${marketId}/data`,
    { credentials: 'include' }), 'Failed to load data inventory');
}

/** One named dataset from the data inventory. Distinct from ``getDataset``,
 *  which is the vendor table and predates this. */
export async function getMarketTable(
  marketId: number, dataset: string, limit = 200,
): Promise<{ dataset: string; total: number; limit: number;
             rows: Record<string, any>[] }> {
  return jsonOrThrow(
    await fetch(`${BASE}/markets/${marketId}/data/${dataset}?limit=${limit}`,
      { credentials: 'include' }), 'Failed to load dataset');
}

/** CSV download. Uncapped, unlike the on-screen table. */
export function datasetCsvDownloadUrl(marketId: number, dataset: string): string {
  return `${BASE}/markets/${marketId}/data/${dataset}?fmt=csv`;
}

// ============================================================================
// Analysis
// ============================================================================

/** Every analysis states what it rests on. A figure without its denominator
 *  invites the wrong conclusion — "one shared investor" reads as a fragmented
 *  market when it actually means half the Crunchbase pages are unread. */
export interface Coverage {
  measured: number;
  total: number;
  unit: string;
  complete: boolean;
  label: string;
}

export interface FormationAnalysis {
  founded_by_year: { year: number; vendors: number }[];
  announcements_by_month: {
    month: string; signal: number; commentary: number; posts: number;
  }[];
  founded_since_2023: number;
  vendors_in_scope: number;
  reviewed_posts: number;
  coverage: Coverage;
  announcement_coverage: Coverage;
}

export interface SignalNoiseAnalysis {
  vendors: {
    brand_id: number; vendor: string; signal: number; commentary: number;
    noise: number; posts: number; signal_share: number | null;
  }[];
  signal_kinds: { kind: string; n: number }[];
  min_posts_for_ratio: number;
  totals: { signal: number; commentary: number; noise: number };
  coverage: Coverage;
}

export interface FundingAnalysis {
  stages: { stage: string; vendors: number }[];
  momentum: {
    brand_id: number; vendor: string;
    growth_score: number | null; heat_score: number | null;
    growth_trend: string | null; heat_trend: string | null;
    cb_rank: number | null; rounds: number | null;
  }[];
  shared_investors: { investor: string; vendors: number; backing: string[] }[];
  coverage: Coverage;
}

export interface HiringAnalysis {
  openings: number;
  by_function: { function: string; openings: number }[];
  by_seniority: { seniority: string; openings: number }[];
  by_role: { role: string; openings: number }[];
  by_country: { country: string; openings: number }[];
  by_region: { region: string; openings: number }[];
  function_by_region: Record<string, number | string>[];
  by_vendor: {
    brand_id: number; vendor: string; openings: number;
    engineering: number; sales: number;
    by_function: Record<string, number>;
    by_role: Record<string, number>;
  }[];
  coverage: Coverage;
}

export interface MarketAnalyses {
  share_of_voice?: ShareOfVoice & { error?: string };
  formation?: FormationAnalysis & { error?: string };
  signal_noise?: SignalNoiseAnalysis & { error?: string };
  funding?: FundingAnalysis & { error?: string };
  hiring?: HiringAnalysis & { error?: string };
}

export async function getAnalyses(marketId: number): Promise<MarketAnalyses> {
  return jsonOrThrow(await fetch(`${BASE}/markets/${marketId}/analysis`,
    { credentials: 'include' }), 'Failed to load analysis');
}

// ============================================================================
// Drilldown
// ============================================================================

export interface DrilldownVendor {
  brand_id: number;
  vendor: string;
  role: string;
  collection_enabled: boolean;
  country: string | null;
  founded: string | null;
  funding_status: string | null;
  musd: number | null;
  staff: number | null;
  announcements: number;
  openings: number;
}

export async function getDrilldown(
  marketId: number, name: string,
): Promise<{ drilldown: string; vendors: DrilldownVendor[]; count: number }> {
  return jsonOrThrow(
    await fetch(`${BASE}/markets/${marketId}/drilldown/${name}`,
      { credentials: 'include' }), 'Failed to load drilldown');
}

// ============================================================================
// Report and bundle
// ============================================================================

/** The whole market as one self-contained HTML file. Needs a session, or a
 *  signed link from getReportLink(). */
export function reportUrl(marketId: number, days = 30): string {
  return `${BASE}/markets/${marketId}/report.html?days=${days}`;
}

/** Every dataset in one zip: nine CSVs, market.json, and a README. */
export function exportBundleUrl(marketId: number): string {
  return `${BASE}/markets/${marketId}/export.zip`;
}

/** A signed, expiring URL that opens the report without a login. */
export async function getReportLink(
  marketId: number, days = 30,
): Promise<{ url: string; expires_at: string; ttl_days: number }> {
  return jsonOrThrow(
    await fetch(`${BASE}/markets/${marketId}/report-link?days=${days}`,
      { credentials: 'include' }), 'Failed to create report link');
}

// ============================================================================
// Briefings
// ============================================================================

export interface BriefingSummary {
  id: number;
  period_label: string;
  period_start: string;
  period_end: string;
  title: string | null;
  status: 'draft' | 'approved' | 'rejected';
  /** "fallback" means the model returned nothing usable and the stored text is
   *  the assembled evidence rather than written prose. */
  generation: 'generated' | 'fallback';
  model_used: string | null;
  created_at: string;
  updated_at: string;
  sources: number | null;
}

export interface BriefingDetail extends BriefingSummary {
  report_content: string;
  /** The evidence the prose was written from. Returned so a reader can check
   *  it: a figure in the briefing that is not here is a fabrication. */
  facts: Record<string, any>;
  article_uris: string[];
  lint: { check: string; detail: string }[];
}

export async function getBriefings(
  marketId: number, limit = 24,
): Promise<{ briefings: BriefingSummary[] }> {
  return jsonOrThrow(
    await fetch(`${BASE}/markets/${marketId}/briefings?limit=${limit}`,
      { credentials: 'include' }), 'Failed to load briefings');
}

export async function getBriefing(
  marketId: number, briefingId: number,
): Promise<BriefingDetail> {
  return jsonOrThrow(
    await fetch(`${BASE}/markets/${marketId}/briefings/${briefingId}`,
      { credentials: 'include' }), 'Failed to load briefing');
}

export async function generateBriefing(
  marketId: number,
  body: { year?: number; month?: number; model?: string } = {},
): Promise<{ id?: number; period_label: string; generation: string;
             item_count: number; content: string }> {
  return jsonOrThrow(await fetch(`${BASE}/markets/${marketId}/briefings`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }), 'Briefing generation failed');
}

export async function setBriefingStatus(
  marketId: number, briefingId: number, status: string,
): Promise<{ ok: boolean; status: string }> {
  return jsonOrThrow(
    await fetch(`${BASE}/markets/${marketId}/briefings/${briefingId}/status`, {
      method: 'PUT', credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    }), 'Could not update status');
}

// ============================================================================
// Job postings
// ============================================================================

export interface JobPosting {
  brand_id: number;
  vendor: string;
  title: string | null;
  location: string | null;
  seniority: string | null;
  function: string | null;
  function_group: string;
  employment_type: string | null;
  posted_date: string | null;
  url: string | null;
  observed_at: string;
}

export async function getJobPostings(
  marketId: number, brandId?: number,
): Promise<{ openings: number; postings: JobPosting[] }> {
  const q = brandId ? `?brand_id=${brandId}` : '';
  return jsonOrThrow(
    await fetch(`${BASE}/markets/${marketId}/jobs${q}`, { credentials: 'include' }),
    'Failed to load job postings');
}

// ============================================================================
// Review task resolution
// ============================================================================

export async function fixReviewTask(
  marketId: number, taskId: number,
  body: { value: unknown; source: string; note?: string },
): Promise<{ ok: boolean; field: string; value: unknown; outcome: string }> {
  return jsonOrThrow(
    await fetch(`${BASE}/markets/${marketId}/review-tasks/${taskId}/fix`, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }), 'Could not apply the correction');
}

export async function closeReviewTask(
  marketId: number, taskId: number, outcome: 'accepted' | 'dismissed',
  note = '',
): Promise<{ ok: boolean; outcome: string }> {
  return jsonOrThrow(
    await fetch(`${BASE}/markets/${marketId}/review-tasks/${taskId}/close`, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ outcome, note }),
    }), 'Could not close the task');
}

export async function autoCloseReviewTasks(
  marketId: number, dryRun = false,
): Promise<{ checked: number; closed: number; dry_run: boolean;
             tasks: { id: number; vendor: string; field: string; answer: string }[] }> {
  return jsonOrThrow(
    await fetch(`${BASE}/markets/${marketId}/review-tasks/auto-close?dry_run=${dryRun}`,
      { method: 'POST', credentials: 'include' }), 'Auto-close failed');
}

// ============================================================================
// Share of voice, top voices, channel mix
// ============================================================================

export interface VoiceRow {
  brand_id: number; vendor: string; own_posts: number; earned: number;
  total: number; earned_share: number | null; own_share: number | null;
  reactions: number; measured_posts: number;
  /** Null when too few posts were measured for an average to mean anything. */
  reactions_per_post: number | null;
}

export interface ShareOfVoice {
  vendors: VoiceRow[];
  /** Vendors posting most about themselves, loudest first. */
  loudest: VoiceRow[];
  reactions_total: number;
  earned_total: number;
  own_total: number;
  silent: number;
  days: number | null;
  coverage: Coverage;
}

export interface TopVoices {
  voices: {
    author: string; platform: string; posts: number; likes: number;
    comments: number; reposts: number; engagement: number; last_seen: string;
    /** What this account talks about, and whom it talks about. */
    terms: { term: string; n: number }[];
    vendors: { vendor: string; n: number }[];
  }[];
  days: number | null;
  coverage: Coverage;
}

export interface ChannelMix {
  by_class: { kind: string; articles: number }[];
  by_month: Record<string, number | string>[];
  total: number;
  days: number | null;
}

export async function getTopVoices(
  marketId: number, days?: number, limit = 25,
): Promise<TopVoices> {
  const q = new URLSearchParams({ limit: String(limit) });
  if (days) q.set('days', String(days));
  return jsonOrThrow(await fetch(`${BASE}/markets/${marketId}/voices?${q}`,
    { credentials: 'include' }), 'Failed to load voices');
}

export async function getChannelMix(
  marketId: number, days?: number,
): Promise<ChannelMix> {
  const q = days ? `?days=${days}` : '';
  return jsonOrThrow(await fetch(`${BASE}/markets/${marketId}/channel-mix${q}`,
    { credentials: 'include' }), 'Failed to load channel mix');
}
