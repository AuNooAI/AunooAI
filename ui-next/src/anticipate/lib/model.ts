/**
 * Maps the monolith's stored trend-convergence payloads (GET /api/trend-convergence/{topic})
 * onto what the design's Anticipate views render. Field names verified against stored runs on
 * bugfixing, 14 Oct 2026.
 */

/** UI tab id → the backend's tab id (`tab=` on the analysis endpoint, prompts, raw output). */
export const BACKEND_TAB: Record<string, string> = {
  consensus: 'consensus',
  'strategic-recommendations': 'strategic',
  'market-signals': 'signals',
  'impact-timeline': 'timeline',
  'future-horizons': 'horizons',
};

/** Backend tab id → the path segment of its /articles and /raw endpoints. */
export const ARTICLES_SEGMENT: Record<string, string> = {
  consensus: 'consensus',
  strategic: 'strategic',
  signals: 'market-signals',
  timeline: 'timeline',
  horizons: 'horizons',
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Payload = Record<string, any>;

/** A numbered source behind the "[n]" markers in the analysis text. */
export interface Reference {
  n: number;
  title: string;
  url?: string;
  source?: string;
  published?: string;
}

/** "2025-2032", "2025–2032", "2030-2035+", "2026" → years; null when there's no year. */
export function parseYears(timeframe: unknown): { start: number; end: number } | null {
  if (typeof timeframe !== 'string') return null;
  const years = timeframe.match(/\b(19|20)\d{2}\b/g)?.map(Number);
  if (!years?.length) return null;
  const start = Math.min(...years);
  const end = Math.max(...years) + (/\+\s*$/.test(timeframe.trim()) ? 5 : 0);
  return { start, end: Math.max(end, start) };
}

/* ---------- Strategic recommendations ---------- */

export interface Trend {
  name: string;
  description: string;
  confidence?: string;
  keyDrivers: string[];
  impact?: string;
}
export interface Horizon {
  timeframe: string;
  years: { start: number; end: number } | null;
  trends: Trend[];
}

const str = (v: unknown) => (typeof v === 'string' ? v : v == null ? '' : String(v));

export function horizonOf(raw: Payload | undefined): Horizon {
  const trends = (Array.isArray(raw?.trends) ? raw!.trends : []).map((t: unknown): Trend => {
    if (typeof t === 'string') return { name: t, description: '', keyDrivers: [] };
    const o = (t ?? {}) as Payload;
    return {
      name: str(o.name || o.title || o.description),
      description: o.name ? str(o.description) : '',
      confidence: o.confidence != null ? str(o.confidence) : undefined,
      keyDrivers: Array.isArray(o.key_drivers) ? o.key_drivers.map(str) : [],
      impact: o.potential_impact ? str(o.potential_impact) : undefined,
    };
  });
  return { timeframe: str(raw?.timeframe), years: parseYears(raw?.timeframe), trends };
}

export interface Principle {
  name: string;
  description: string;
  rationale?: string;
  implementation?: string;
}

/**
 * The decision framework. The server always adds an empty `executive_decision_framework` and
 * puts the organisation-specific one under another `*_framework` key, so take the first with
 * principles (the old page took the empty default and hid the real one).
 */
export function frameworkOf(data: Payload): { title: string; principles: Principle[] } | null {
  const keys = Object.keys(data).filter((k) => k.endsWith('_framework'));
  const key = keys.find((k) => Array.isArray(data[k]?.principles) && data[k].principles.length > 0);
  if (!key) return null;
  const title = key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  return {
    title,
    principles: data[key].principles.map((p: Payload) => ({
      name: str(p.name || p.title),
      description: str(p.description || p.content),
      rationale: p.rationale ? str(p.rationale) : undefined,
      implementation: p.implementation ? str(p.implementation) : undefined,
    })),
  };
}

export interface NextStep {
  priority?: string;
  action: string;
  timeline?: string;
  stakeholders: string[];
  metrics: string[];
}

export const nextStepsOf = (data: Payload): NextStep[] =>
  (Array.isArray(data.next_steps) ? data.next_steps : []).map((s: unknown) =>
    typeof s === 'string'
      ? { action: s, stakeholders: [], metrics: [] }
      : {
          priority: (s as Payload).priority ? str((s as Payload).priority) : undefined,
          action: str((s as Payload).action || (s as Payload).description),
          timeline: (s as Payload).timeline ? str((s as Payload).timeline) : undefined,
          stakeholders: Array.isArray((s as Payload).stakeholders) ? (s as Payload).stakeholders.map(str) : [],
          metrics: Array.isArray((s as Payload).success_metrics) ? (s as Payload).success_metrics.map(str) : [],
        },
  );

/* ---------- Market signals ---------- */

export type Level = 'critical' | 'high' | 'medium' | 'low' | 'unknown';
/** The prompt writes lowercase; older runs used "High". */
export const levelOf = (v: unknown): Level => {
  const s = str(v).toLowerCase();
  return s === 'critical' || s === 'high' || s === 'medium' || s === 'low' ? s : 'unknown';
};

/* ---------- Consensus ---------- */

export interface Theme {
  id: string;
  title: string;
  description: string;
  articles: number;
  summary?: string;
  agreement?: number;
  strength?: string;
  evidence?: string;
  sentiment?: { positive: number; neutral: number; critical: number };
  timing?: { start: number; end: number; label?: string };
  timingDistribution: { label: string; pct: number }[];
  implications?: string;
  optimistic: Payload[];
  pessimistic: Payload[];
  keyArticles: { title: string; url?: string; summary?: string; sentiment?: string }[];
  decisionWindows: { urgency?: string; window?: string; action?: string; rationale?: string; owner?: string }[];
  timeframe?: { immediate?: string; short_term?: string; mid_term?: string; key_milestones?: unknown };
}

export function themesOf(data: Payload): Theme[] {
  const cats: Payload[] = Array.isArray(data.categories) ? data.categories : [];
  return cats.map((c, i) => {
    const type = c['1_consensus_type'] ?? {};
    const timeline = c['2_timeline_consensus'] ?? {};
    const conf = c['3_confidence_level'] ?? {};
    const win = timeline.consensus_window;
    return {
      id: `${i}-${c.category_name}`,
      title: str(c.category_name || 'Untitled theme'),
      description: str(c.category_description),
      articles: Number(c.articles_analyzed) || 0,
      summary: type.summary ? str(type.summary) : undefined,
      agreement: conf.majority_agreement != null ? Number(conf.majority_agreement) : undefined,
      strength: conf.consensus_strength ? str(conf.consensus_strength) : undefined,
      evidence: conf.evidence_quality ? str(conf.evidence_quality) : undefined,
      sentiment: type.distribution
        ? { positive: Number(type.distribution.positive) || 0, neutral: Number(type.distribution.neutral) || 0, critical: Number(type.distribution.critical) || 0 }
        : undefined,
      timing: win?.start_year ? { start: Number(win.start_year), end: Number(win.end_year ?? win.start_year), label: win.label } : undefined,
      timingDistribution: Object.entries((timeline.distribution ?? {}) as Record<string, number>).map(([label, pct]) => ({ label, pct: Number(pct) || 0 })),
      implications: c['7_strategic_implications'] ? str(c['7_strategic_implications']) : undefined,
      optimistic: Array.isArray(c['4_optimistic_outliers']) ? c['4_optimistic_outliers'] : [],
      pessimistic: Array.isArray(c['5_pessimistic_outliers']) ? c['5_pessimistic_outliers'] : [],
      keyArticles: (Array.isArray(c['6_key_articles']) ? c['6_key_articles'] : []).map((a: Payload) => ({
        title: str(a.title), url: a.url, summary: a.summary, sentiment: a.sentiment,
      })),
      decisionWindows: Array.isArray(c['8_key_decision_windows']) ? c['8_key_decision_windows'] : [],
      timeframe: c['9_timeframe_analysis'] ?? undefined,
    };
  });
}

/* ---------- Future horizons ---------- */

export type Band = 'h1' | 'h2' | 'h3';
export interface Scenario {
  id: string;
  band: Band;
  title: string;
  description: string;
  timeframe: string;
  years: { start: number; end: number } | null;
  sentiment?: string;
}

const bandOf = (s: Payload): Band => {
  const t = str(s.type || s.horizon || s.horizon_type).toLowerCase();
  if (t.includes('3') || t.includes('future') || t.includes('emerg')) return 'h3';
  if (t.includes('2') || t.includes('transition') || t.includes('innov')) return 'h2';
  return 'h1';
};

export const scenariosOf = (list: unknown): Scenario[] =>
  (Array.isArray(list) ? list : []).map((s: Payload, i) => ({
    id: str(s.scenario_key || `${i}`),
    band: bandOf(s),
    title: str(s.title || s.name),
    description: str(s.description),
    timeframe: str(s.timeframe),
    years: s.timeline_start ? { start: Number(s.timeline_start), end: Number(s.timeline_end ?? s.timeline_start) } : parseYears(s.timeframe),
    sentiment: s.sentiment ? str(s.sentiment) : undefined,
  }));

/** One executive-summary card (data/prompts/future_horizons/executive_summary.json). The prompt
 *  forbids consensus percentages, so none is shown. */
export interface ExecSummary {
  title: string;
  horizonLabel?: string;
  statement: string;
  minority?: string;
  primarySignal?: string;
  forks: { condition: string; outcome: string }[];
  windows: { timeframe: string; action: string }[];
  sources: string[];
}

const fork = (f: Payload | undefined) =>
  f && (f.condition || f.outcome || f.if_clause) ? { condition: str(f.condition || f.if_clause), outcome: str(f.outcome || f.then_clause) } : null;

export const execSummariesOf = (list: unknown): ExecSummary[] =>
  (Array.isArray(list) ? list : []).map((s: Payload) => ({
    title: str(s.topic_title || s.title),
    horizonLabel: s.horizon_label ? str(s.horizon_label) : undefined,
    statement: str(s.opening_statement || s.summary),
    minority: s.minority_view?.statement ? str(s.minority_view.statement) : undefined,
    primarySignal: s.primary_signal ? str(s.primary_signal) : undefined,
    forks: [fork(s.decision_fork?.condition_a), fork(s.decision_fork?.condition_b)].filter((f): f is { condition: string; outcome: string } => f !== null),
    windows: Object.values((s.action_window ?? {}) as Record<string, Payload>)
      .filter((w) => w && (w.timeframe || w.action))
      .map((w) => ({ timeframe: str(w.timeframe), action: str(w.action) })),
    sources: Array.isArray(s.source_scenarios)
      ? s.source_scenarios.map((x: unknown) => (typeof x === 'string' ? x : `${str((x as Payload)?.title)}${(x as Payload)?.horizon ? ` (${str((x as Payload).horizon).toUpperCase()})` : ''}`))
      : [],
  }));

/* ---------- References ---------- */

export const referencesOf = (articles: unknown): Reference[] =>
  (Array.isArray(articles) ? articles : [])
    .map((a: Payload) => ({
      n: Number(a.id ?? a.citation_number),
      title: str(a.title || a.uri || a.url),
      url: a.url || (typeof a.uri === 'string' && a.uri.startsWith('http') ? a.uri : undefined),
      source: a.source || a.news_source,
      published: a.published_at || a.publication_date,
    }))
    .filter((r) => Number.isFinite(r.n))
    .sort((a, b) => a.n - b.n);
