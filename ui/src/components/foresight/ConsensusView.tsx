/**
 * ConsensusView — cross-source evidence synthesis, ported from the saas app's
 * shared-dashboard Consensus page (ui/src/pages/ConsensusPage.tsx there). The
 * "area + panels" layout: an overview stat grid and a topic→theme accordion
 * with per-theme timelines, a filter-pill row, search, and a list/grid toggle.
 *
 * Display-only: the caller supplies a ConsensusResponse (see
 * foresightAdapters.toConsensusResponse) — no fetching, sharing, or Auspex
 * hooks from the saas original.
 */
import { useMemo, useState, ReactNode } from 'react';
import { cn } from '../ui/utils';
import { TopicIcon, iconSlugFor, ConsensusTitleIcon } from './dashboardIcons';
import '../../styles/shared-dashboard.css';

// ─── Types (view contract) ──────────────────────────────────────────────────

interface SentimentDist {
  positive: number;
  neutral: number;
  critical: number;
}
interface KeyArticle {
  title: string;
  url: string;
  sentiment?: string;
}
interface Outlier {
  scenario: string;
  details: string;
  source_percentage?: number;
  year?: number;
  reference?: string;
}
interface Milestone {
  year: number;
  milestone: string;
  significance?: string;
}
interface TimeframeAnalysis {
  immediate?: string;
  short_term?: string;
  mid_term?: string;
  key_milestones?: Milestone[];
}
export interface ConsensusCategory {
  category_name: string;
  category_description?: string;
  sentiment_distribution?: SentimentDist;
  consensus_strength?: string;
  evidence_quality?: string;
  majority_agreement?: number;
  articles_analyzed?: number;
  timeline_window?: { start_year: number; end_year: number; label?: string };
  strategic_implications?: string;
  key_articles?: KeyArticle[];
  optimistic_outlier?: Outlier | null;
  pessimistic_outlier?: Outlier | null;
  timeframe_analysis?: TimeframeAnalysis;
  topic_id?: number;
  topic_name?: string;
}
interface KeyInsight {
  quote: string;
  source?: string;
  relevance?: string;
  topic_id?: number;
  topic_name?: string;
}
interface TopicRef {
  id: number;
  name: string;
}
export interface ReferencedArticle {
  id?: number;
  citation_number?: number;
  title?: string;
  url?: string;
  source?: string;
  published_at?: string | null;
}
type CitationMap = Record<number, ReferencedArticle>;

export interface ConsensusResponse {
  categories: ConsensusCategory[];
  key_insights: KeyInsight[];
  article_count: number;
  articles?: ReferencedArticle[];
  topic?: string;
  topics?: TopicRef[];
}

// ─── View-model (ported from the saas renderers/consensus.py transform) ─────

const PALETTE: Array<[string, string]> = [
  ['var(--accent)', 'var(--accent-tint-15)'],
  ['var(--m-auspex)', 'var(--mention-tint)'],
  ['var(--star-active)', 'var(--star-tint)'],
  ['var(--live)', 'var(--live-tint)'],
  ['var(--m-ciops)', 'rgba(129,69,181,0.10)'],
  ['var(--m-deepresearch)', 'rgba(204,78,0,0.10)'],
  ['var(--accent-strong)', 'var(--counter-tint)'],
  ['var(--m-nocorr)', 'rgba(91,91,214,0.10)'],
];

const STRENGTH_COLOR: Record<string, string> = {
  Strong: 'var(--live)',
  Moderate: 'var(--star-active)',
  Emergent: 'var(--accent-strong)',
};

function strengthFor(agreement: number): string {
  if (agreement >= 85) return 'Strong';
  if (agreement >= 75) return 'Moderate';
  return 'Emergent';
}

function safeYear(v: unknown): number | null {
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? Math.round(n) : null;
}
function safeInt(v: unknown, def = 0): number {
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? Math.trunc(n) : def;
}
function pctOf(year: number | null, lo: number, hi: number): number | null {
  if (year == null || hi <= lo) return null;
  return Math.round(Math.max(0, Math.min(100, ((year - lo) / (hi - lo)) * 100)) * 100) / 100;
}

interface ThemeDetailVM {
  agreement: string;
  strengthLabel: string;
  evidence: string;
  sentiment: { aligned: number; mixed: number; counter: number };
  consequences: string;
  horizons: Array<{ label: string; text: string }>;
  optimistic: { year: string | number; title: string; text: string; cite: string } | null;
  pessimistic: { year: string | number; title: string; text: string; cite: string } | null;
  milestones: Array<{ year: string | number; title: string; sub: string }>;
  supportingArticles: Array<{ title: string; tag: 'critical' | 'neutral'; url: string }>;
}

interface ThemeVM {
  title: string;
  articles: number;
  pct: number;
  strength: string;
  strengthColor: string;
  divergence: boolean;
  years: { start: number; end: number; peak: number; opt: number | null; pess: number | null };
  geom: { rangeLeft: number; rangeWidth: number; peakLeft: number | null; optLeft: number | null; pessLeft: number | null };
  detail: ThemeDetailVM;
  raw: ConsensusCategory;
}

interface TopicVM {
  id: string;
  topicId: number | null;
  letter: string;
  icon: string | null;
  name: string;
  color: string;
  tint: string;
  peak: string;
  insights: number;
  insightItems: Array<{ quote: string; relevance: string }>;
  themes: ThemeVM[];
}

interface AxisVM {
  min: number;
  max: number;
  ticks: Array<{ year: number; left: number | null }>;
}

interface OverviewVM {
  themes_tracked: number;
  topics_count: number;
  peak_year: number | null;
  peak_count: number;
  high_divergence: number;
  article_count: number;
  window_label: string;
}

function buildDetail(cat: ConsensusCategory): ThemeDetailVM {
  const agreement = safeInt(cat.majority_agreement);
  const sd = cat.sentiment_distribution || ({} as SentimentDist);
  const tf = cat.timeframe_analysis || {};
  const horizons: Array<{ label: string; text: string }> = [];
  if (tf.immediate) horizons.push({ label: 'Near-term · 0–6 mo', text: tf.immediate });
  if (tf.short_term) horizons.push({ label: 'Short-term · 6–18 mo', text: tf.short_term });
  if (tf.mid_term) horizons.push({ label: 'Mid-term · 18+ mo', text: tf.mid_term });

  const milestones = (tf.key_milestones || []).map((m) => {
    const y = safeYear(m.year);
    return { year: y ?? '—', title: m.milestone || '', sub: m.significance || '' };
  });

  const outlier = (o: Outlier | null | undefined) => {
    if (!o || !(o.scenario || o.details)) return null;
    const y = safeYear(o.year);
    return { year: y ?? '', title: o.scenario || '', text: o.details || '', cite: o.reference || '' };
  };

  const arts = (cat.key_articles || [])
    .filter((a) => a && a.title)
    .map((a) => ({
      title: a.title || '',
      tag: ((a.sentiment || '').toLowerCase() === 'critical' ? 'critical' : 'neutral') as 'critical' | 'neutral',
      url: a.url || '',
    }));

  let evidence = cat.evidence_quality || '—';
  const nAnalyzed = safeInt(cat.articles_analyzed);
  if (nAnalyzed) evidence = `${evidence} · ${nAnalyzed} articles`;

  return {
    agreement: `${agreement}%`,
    strengthLabel: strengthFor(agreement),
    evidence,
    sentiment: { aligned: safeInt(sd.positive), mixed: safeInt(sd.neutral), counter: safeInt(sd.critical) },
    consequences: cat.strategic_implications || '',
    horizons,
    optimistic: outlier(cat.optimistic_outlier),
    pessimistic: outlier(cat.pessimistic_outlier),
    milestones,
    supportingArticles: arts,
  };
}

function themePeakYear(start: number, end: number, milestones?: Milestone[]): number {
  const yrs = (milestones || [])
    .map((m) => safeYear(m.year))
    .filter((y): y is number => y != null && y >= start && y <= end)
    .sort((a, b) => a - b);
  if (yrs.length) return yrs[Math.floor(yrs.length / 2)];
  return Math.round((start + end) / 2);
}

function buildTheme(cat: ConsensusCategory): ThemeVM {
  const agreement = safeInt(cat.majority_agreement);
  const strength = strengthFor(agreement);
  const tw = cat.timeline_window || ({} as { start_year: number; end_year: number });
  let start = safeYear(tw.start_year);
  let end = safeYear(tw.end_year);
  const optY = safeYear(cat.optimistic_outlier?.year);
  const pessY = safeYear(cat.pessimistic_outlier?.year);
  const candidates = [start, end, optY, pessY].filter((y): y is number => y != null);
  if (start == null) start = candidates.length ? Math.min(...candidates) : 2026;
  if (end == null) end = candidates.length ? Math.max(...candidates) : start + 4;
  if (end <= start) end = start + 1;
  const peak = themePeakYear(start, end, cat.timeframe_analysis?.key_milestones);

  return {
    title: cat.category_name || 'Untitled theme',
    articles: safeInt(cat.articles_analyzed),
    pct: agreement,
    strength,
    strengthColor: STRENGTH_COLOR[strength] || 'var(--accent-strong)',
    divergence: strength === 'Emergent',
    years: { start, end, peak, opt: optY, pess: pessY },
    geom: { rangeLeft: 0, rangeWidth: 1, peakLeft: null, optLeft: null, pessLeft: null },
    detail: buildDetail(cat),
    raw: cat,
  };
}

function buildTopics(data: ConsensusResponse, topicLabel: string): TopicVM[] {
  const cats = data.categories || [];
  const insights = data.key_insights || [];
  const defaultName = data.topic || topicLabel || 'Consensus';
  const topicNameById = new Map<number, string>();
  for (const t of data.topics || []) topicNameById.set(t.id, t.name);

  const groups = new Map<string, { topicId: number | null; name: string; themes: ThemeVM[]; insights: Array<{ quote: string; relevance: string }> }>();
  const order: string[] = [];
  for (const cat of cats) {
    if (!cat) continue;
    const tid = cat.topic_id ?? null;
    const tname = (tid != null ? topicNameById.get(tid) : undefined) || cat.topic_name || defaultName;
    const key = tid != null ? `id${tid}` : `_${tname}`;
    if (!groups.has(key)) {
      groups.set(key, { topicId: tid, name: tname, themes: [], insights: [] });
      order.push(key);
    }
    groups.get(key)!.themes.push(buildTheme(cat));
  }

  for (const ins of insights) {
    if (!ins || !ins.quote) continue;
    const item = { quote: ins.quote, relevance: ins.relevance || '' };
    const tid = ins.topic_id;
    if (tid != null && groups.has(`id${tid}`)) groups.get(`id${tid}`)!.insights.push(item);
    else if (tid == null && order.length === 1) groups.get(order[0])!.insights.push(item);
  }

  return order.map((key, i) => {
    const g = groups.get(key)!;
    const [color, tint] = PALETTE[i % PALETTE.length];
    const peakPct = g.themes.reduce((mx, t) => Math.max(mx, t.pct), 0);
    return {
      id: `t${i}`,
      topicId: g.topicId,
      letter: (g.name.trim()[0] || '•').toUpperCase(),
      icon: iconSlugFor(g.name),
      name: g.name,
      color,
      tint,
      peak: `${peakPct}%`,
      insights: g.insights.length,
      insightItems: g.insights,
      themes: g.themes,
    };
  });
}

function buildAxis(topics: TopicVM[]): AxisVM {
  const years: number[] = [];
  for (const tp of topics) for (const t of tp.themes) years.push(t.years.start, t.years.end);
  let lo: number;
  let hi: number;
  if (!years.length) {
    lo = 2026;
    hi = 2035;
  } else {
    lo = Math.min(...years);
    hi = Math.max(...years);
    if (hi <= lo) hi = lo + 1;
  }
  const span = hi - lo;
  const step = Math.max(1, Math.round(span / 4));
  const tickYears: number[] = [];
  for (let y = lo; y <= hi; y += step) tickYears.push(y);
  if (tickYears[tickYears.length - 1] !== hi) tickYears.push(hi);
  return { min: lo, max: hi, ticks: tickYears.map((y) => ({ year: y, left: pctOf(y, lo, hi) })) };
}

function attachGeometry(topics: TopicVM[], axis: AxisVM): void {
  const { min: lo, max: hi } = axis;
  for (const tp of topics) {
    for (const t of tp.themes) {
      const a = pctOf(t.years.start, lo, hi) ?? 0;
      const b = pctOf(t.years.end, lo, hi) ?? 0;
      t.geom = {
        rangeLeft: a,
        rangeWidth: Math.round(Math.max(b - a, 1) * 100) / 100,
        peakLeft: pctOf(t.years.peak, lo, hi),
        optLeft: pctOf(t.years.opt, lo, hi),
        pessLeft: pctOf(t.years.pess, lo, hi),
      };
    }
  }
}

function buildOverview(topics: TopicVM[], data: ConsensusResponse, days: number | null): OverviewVM {
  const allThemes = topics.flatMap((tp) => tp.themes);
  const peakCounts = new Map<number, number>();
  for (const t of allThemes) peakCounts.set(t.years.peak, (peakCounts.get(t.years.peak) || 0) + 1);
  let peakYear: number | null = null;
  let peakCount = 0;
  for (const [y, c] of peakCounts) if (c > peakCount) {
    peakYear = y;
    peakCount = c;
  }
  return {
    themes_tracked: allThemes.length,
    topics_count: topics.length,
    peak_year: peakYear,
    peak_count: peakCount,
    high_divergence: allThemes.filter((t) => t.divergence).length,
    article_count: safeInt(data.article_count),
    window_label: days ? `Past ${days} days` : 'Analysis window',
  };
}

interface ConsensusVM {
  topics: TopicVM[];
  axis: AxisVM;
  overview: OverviewVM;
}

function buildConsensusVM(data: ConsensusResponse, days: number | null, topicLabel: string): ConsensusVM {
  const topics = buildTopics(data, topicLabel);
  const axis = buildAxis(topics);
  const overview = buildOverview(topics, data, days); // before geometry — reads peak years
  attachGeometry(topics, axis);
  return { topics, axis, overview };
}

// ─── View ───────────────────────────────────────────────────────────────────

export function ConsensusView({
  data,
  days = null,
  actions = null,
}: {
  data: ConsensusResponse | null;
  /** Lookback window in days, shown on the source-articles stat card. */
  days?: number | null;
  /** Optional buttons rendered in the title row (export, generate, …). */
  actions?: ReactNode;
}) {
  const [filterTopic, setFilterTopic] = useState<number | null>(null);
  const [search, setSearch] = useState('');
  const [gridMode, setGridMode] = useState(false);
  const [openTopics, setOpenTopics] = useState<Record<string, boolean>>({});
  const [openThemes, setOpenThemes] = useState<Record<string, boolean>>({});

  const topicLabelRaw = data?.topic || 'All Topics';
  const vm = useMemo(
    () => (data ? buildConsensusVM(data, days, topicLabelRaw) : null),
    [data, days, topicLabelRaw],
  );

  const citations: CitationMap = useMemo(() => {
    const map: CitationMap = {};
    (data?.articles ?? []).forEach((a) => {
      if (typeof a.citation_number === 'number') map[a.citation_number] = a;
    });
    return map;
  }, [data?.articles]);

  const q = search.trim().toLowerCase();

  // Topic filter + search applied to the VM.
  const visibleTopics = useMemo(() => {
    if (!vm) return [];
    return vm.topics
      .filter((tp) => filterTopic == null || tp.topicId === filterTopic)
      .map((tp) => ({ ...tp, themes: tp.themes.filter((t) => !q || t.title.toLowerCase().includes(q)) }))
      .filter((tp) => tp.themes.length > 0);
  }, [vm, filterTopic, q]);

  const hasContent = visibleTopics.length > 0;

  const topicChips: TopicRef[] = data?.topics ?? [];
  const topicLabel =
    filterTopic != null ? topicChips.find((t) => t.id === filterTopic)?.name ?? 'Selected topic' : data?.topic ?? 'All topics';

  // First topic + its first theme open by default.
  const firstTopicId = vm?.topics[0]?.id;
  const firstThemeKey = vm?.topics[0] ? `${vm.topics[0].id}-0` : undefined;
  const isTopicOpen = (id: string) => (q ? true : openTopics[id] ?? id === firstTopicId);
  const isThemeOpen = (key: string) => openThemes[key] ?? key === firstThemeKey;

  return (
    <div className="aunoo-dash w-full">
      <main className="area">
        <div className="area-inner">
          <div className="title-row">
            <ConsensusTitleIcon />
            <div className="title-text">
              <h1>Consensus Analysis</h1>
              <p className="subhead">
                {topicLabel && topicLabel !== 'All topics' ? `${topicLabel} — ` : ''}
                Cross-source evidence synthesis — where coverage converges, where it diverges, and what it points to.
              </p>
            </div>
            {actions && <div className="title-actions">{actions}</div>}
          </div>

          {vm && (
            <>
              {/* Overview */}
              <section className="panel">
                <div className="panel-head">
                  <span className="panel-title" style={{ color: 'var(--accent)' }}>
                    Overview
                  </span>
                </div>
                <div className="stat-grid">
                  <div className="stat-card">
                    <div className="eyebrow">Themes tracked</div>
                    <div className="value">{vm.overview.themes_tracked}</div>
                    <div className="sub">
                      {vm.overview.topics_count} topic{vm.overview.topics_count === 1 ? '' : 's'}
                    </div>
                  </div>
                  <div className="stat-card">
                    <div className="eyebrow">Aggregated peak</div>
                    <div className="value">{vm.overview.peak_year ?? '—'}</div>
                    <div className="sub">
                      {vm.overview.peak_count
                        ? `${vm.overview.peak_count} theme${vm.overview.peak_count === 1 ? '' : 's'} coalesce here`
                        : 'No clear peak'}
                    </div>
                  </div>
                  <div className="stat-card">
                    <div className="eyebrow">High divergence</div>
                    <div className="value">{vm.overview.high_divergence}</div>
                    <div className="sub">{vm.overview.high_divergence ? 'Worth attention' : 'Broad alignment'}</div>
                  </div>
                  <div className="stat-card">
                    <div className="eyebrow">Source articles</div>
                    <div className="value">{vm.overview.article_count}</div>
                    <div className="sub">{vm.overview.window_label}</div>
                  </div>
                </div>
              </section>

              {/* Consensus Themes */}
              <section className="panel">
                <div className="panel-head">
                  <span className="panel-title" style={{ color: 'var(--m-deepresearch)' }}>
                    Consensus Themes
                  </span>
                  <span className="panel-tools">
                    <span className="view-toggle">
                      <button className={cn(!gridMode && 'active')} title="List view" aria-label="List view" onClick={() => setGridMode(false)}>
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <line x1="8" y1="6" x2="21" y2="6" />
                          <line x1="8" y1="12" x2="21" y2="12" />
                          <line x1="8" y1="18" x2="21" y2="18" />
                          <line x1="3" y1="6" x2="3.01" y2="6" />
                          <line x1="3" y1="12" x2="3.01" y2="12" />
                          <line x1="3" y1="18" x2="3.01" y2="18" />
                        </svg>
                      </button>
                      <button className={cn(gridMode && 'active')} title="Grid view" aria-label="Grid view" onClick={() => setGridMode(true)}>
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <rect x="3" y="3" width="7" height="7" />
                          <rect x="14" y="3" width="7" height="7" />
                          <rect x="14" y="14" width="7" height="7" />
                          <rect x="3" y="14" width="7" height="7" />
                        </svg>
                      </button>
                    </span>
                  </span>
                </div>

                <div className="filter-row">
                  <span className="filter-label">Filter</span>
                  <button className={cn('filter-pill', filterTopic == null && 'active')} onClick={() => setFilterTopic(null)}>
                    All topics
                  </button>
                  {topicChips.map((t) => (
                    <button
                      key={t.id}
                      className={cn('filter-pill', filterTopic === t.id && 'active')}
                      onClick={() => setFilterTopic(filterTopic === t.id ? null : t.id)}
                    >
                      {t.name}
                    </button>
                  ))}
                  <div className="search-box">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="11" cy="11" r="8" />
                      <line x1="21" y1="21" x2="16.65" y2="16.65" />
                    </svg>
                    <input type="text" placeholder="Search themes…" value={search} onChange={(e) => setSearch(e.target.value)} />
                  </div>
                </div>

                {!hasContent && <p className="no-results">No themes match your filter.</p>}

                {hasContent && !gridMode && (
                  <div className="topics-root">
                    {visibleTopics.map((tp) => (
                      <details className="topic" key={tp.id} open={isTopicOpen(tp.id)}>
                        <summary
                          onClick={(e) => {
                            e.preventDefault();
                            setOpenTopics((s) => ({ ...s, [tp.id]: !isTopicOpen(tp.id) }));
                          }}
                        >
                          {tp.icon ? (
                            <TopicIcon slug={tp.icon} />
                          ) : (
                            <span className="t-avatar" style={{ background: tp.tint, color: tp.color }}>
                              {tp.letter}
                            </span>
                          )}
                          <span className="t-titleblock">
                            <span className="t-name">{tp.name}</span>
                            <br />
                            <span className="t-sub">
                              {tp.themes.length} theme{tp.themes.length === 1 ? '' : 's'} · peak {tp.peak}
                              {tp.insights ? ` · ${tp.insights} insight${tp.insights === 1 ? '' : 's'}` : ''}
                            </span>
                          </span>
                          <span className="t-chev">▾</span>
                        </summary>

                        {tp.themes.map((t, ti) => {
                          const key = `${tp.id}-${ti}`;
                          return (
                            <details className="theme" key={key} open={isThemeOpen(key)}>
                              <summary
                                onClick={(e) => {
                                  e.preventDefault();
                                  setOpenThemes((s) => ({ ...s, [key]: !isThemeOpen(key) }));
                                }}
                              >
                                <span className="th-bar" style={{ background: tp.color }} />
                                <span className="th-main">
                                  <span className="th-title">{t.title}</span>
                                  <span className="th-meta">
                                    <span className="topic-chip" style={{ background: tp.tint, color: tp.color }}>
                                      {tp.name}
                                    </span>
                                    <span className="th-articles">
                                      {t.articles} article{t.articles === 1 ? '' : 's'}
                                    </span>
                                    {t.divergence && <span className="divergence-chip">High divergence</span>}
                                  </span>
                                </span>
                                <span className="tl-wrap">
                                  <ThemeTimeline theme={t} color={tp.color} axis={vm.axis} />
                                </span>
                                <span className="th-strength">
                                  <span className="pct" style={{ color: t.strengthColor }}>
                                    {t.pct}%
                                  </span>
                                  <span className="label">{t.strength}</span>
                                </span>
                                <span className="th-chev">▾</span>
                              </summary>
                              <ThemeDetail theme={t} citations={citations} />
                            </details>
                          );
                        })}

                        {tp.insightItems.length > 0 && (
                          <details className="insights">
                            <summary>
                              Key insights <span className="count">{tp.insights}</span>
                              <span className="ins-chev">▾</span>
                            </summary>
                            <div className="insights-body">
                              {tp.insightItems.map((ins, i) => (
                                <div className="ins-item" key={i}>
                                  <div className="ins-quote">{ins.quote}</div>
                                  {ins.relevance && (
                                    <div className="ins-why">
                                      <b>Why it matters</b> · {ins.relevance}
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          </details>
                        )}
                      </details>
                    ))}
                  </div>
                )}

                {hasContent && gridMode && (
                  <div className="topics-grid">
                    {visibleTopics.flatMap((tp) =>
                      tp.themes.map((t, ti) => (
                        <div className="grid-card" key={`${tp.id}-${ti}`}>
                          <div className="gc-top">
                            <span className="topic-chip" style={{ background: tp.tint, color: tp.color }}>
                              {tp.name}
                            </span>
                            <span className="th-articles">
                              {t.articles} article{t.articles === 1 ? '' : 's'}
                            </span>
                            {t.divergence && <span className="divergence-chip">High divergence</span>}
                          </div>
                          <div className="gc-title">{t.title}</div>
                          <div className="gc-meter-row">
                            <div className="gc-meter">
                              <span style={{ width: `${t.pct}%`, background: t.strengthColor }} />
                            </div>
                            <div className="gc-pct" style={{ color: t.strengthColor }}>
                              {t.pct}%<span className="gc-label">{t.strength}</span>
                            </div>
                          </div>
                        </div>
                      )),
                    )}
                  </div>
                )}
              </section>

              <footer className="disclosure">
                <div className="meta">Consensus Analysis · Powered by AunooAI · aunoo.ai</div>
                <em>The analysis is AI-generated from news coverage — AunooAI does not adjudicate truth. Verify claims against the cited sources.</em>
              </footer>
            </>
          )}
        </div>
      </main>
    </div>
  );
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function ThemeTimeline({ theme, color, axis }: { theme: ThemeVM; color: string; axis: AxisVM }) {
  const g = theme.geom;
  return (
    <div className="tl">
      <div className="tl-track" />
      {axis.ticks.map((tick, i) => (
        <span key={i}>
          <span className="tl-tick" style={{ left: `${tick.left ?? 0}%` }} />
          <span className="tl-year" style={{ left: `${tick.left ?? 0}%` }}>
            {tick.year}
          </span>
        </span>
      ))}
      <span className="tl-range" style={{ left: `${g.rangeLeft}%`, width: `${g.rangeWidth}%`, background: color }} />
      {g.peakLeft != null && <span className="tl-peak" style={{ left: `${g.peakLeft}%`, background: color }} />}
      {g.optLeft != null && <span className="tl-dot" style={{ left: `${g.optLeft}%`, background: 'var(--live)' }} />}
      {g.pessLeft != null && <span className="tl-dot" style={{ left: `${g.pessLeft}%`, background: 'var(--accent-strong)' }} />}
    </div>
  );
}

function ThemeDetail({ theme, citations }: { theme: ThemeVM; citations: CitationMap }) {
  const d = theme.detail;
  return (
    <div className="detail">
      <div className="detail-grid">
        <div>
          <div className="dg-label">Consensus theme</div>
          <div className="dg-value">{theme.title}</div>
        </div>
        <div>
          <div className="dg-label">Agreement</div>
          <div className="dg-value">{d.agreement}</div>
        </div>
        <div>
          <div className="dg-label">Strength</div>
          <div className="dg-value">{d.strengthLabel}</div>
        </div>
        <div>
          <div className="dg-label">Evidence quality</div>
          <div className="dg-value">{d.evidence}</div>
        </div>
      </div>

      <div className="sentiment">
        <div className="s-head">
          <span className="s-title">Sentiment distribution</span>
          <span className="s-split">
            {d.sentiment.aligned}% aligned · {d.sentiment.mixed}% mixed · {d.sentiment.counter}% counter
          </span>
        </div>
        <div className="s-bar">
          <span style={{ width: `${d.sentiment.aligned}%`, background: 'var(--live)' }} />
          <span style={{ width: `${d.sentiment.mixed}%`, background: 'var(--star-active)' }} />
          <span style={{ width: `${d.sentiment.counter}%`, background: 'var(--accent-strong)' }} />
        </div>
      </div>

      {d.consequences && (
        <div className="d-box">
          <div className="b-title">Broader consequences</div>
          <p>{renderCitations(d.consequences, citations)}</p>
        </div>
      )}

      {d.horizons.length > 0 && (
        <div className="horizon-grid">
          {d.horizons.map((h, i) => (
            <div className="h-card" key={i}>
              <div className="h-eyebrow">{h.label}</div>
              <p>{renderCitations(h.text, citations)}</p>
            </div>
          ))}
        </div>
      )}

      {(d.optimistic || d.pessimistic) && (
        <div className="outlier-grid">
          {d.optimistic && (
            <div className="o-card optimistic">
              <div className="o-eyebrow">Optimistic outlier{d.optimistic.year ? ` · ${d.optimistic.year}` : ''}</div>
              <div className="o-title">{d.optimistic.title}</div>
              <p>
                {renderCitations(d.optimistic.text, citations)}
                {d.optimistic.cite ? <> {renderCitations(d.optimistic.cite, citations)}</> : null}
              </p>
            </div>
          )}
          {d.pessimistic && (
            <div className="o-card pessimistic">
              <div className="o-eyebrow">Pessimistic outlier{d.pessimistic.year ? ` · ${d.pessimistic.year}` : ''}</div>
              <div className="o-title">{d.pessimistic.title}</div>
              <p>
                {renderCitations(d.pessimistic.text, citations)}
                {d.pessimistic.cite ? <> {renderCitations(d.pessimistic.cite, citations)}</> : null}
              </p>
            </div>
          )}
        </div>
      )}

      {d.milestones.length > 0 && (
        <div className="d-box milestones">
          <div className="b-title">Projected milestones</div>
          {d.milestones.map((m, i) => (
            <div className="m-row" key={i}>
              <div className="m-year">{m.year}</div>
              <div className="m-body">
                <div className="m-title">{m.title}</div>
                {m.sub && <div className="m-sub">{m.sub}</div>}
              </div>
            </div>
          ))}
        </div>
      )}

      {d.supportingArticles.length > 0 && (
        <div className="d-box articles-list">
          <div className="b-title">Key supporting articles</div>
          {d.supportingArticles.map((a, i) => (
            <div className="a-row" key={i}>
              <span className="a-dot" style={{ background: a.tag === 'critical' ? 'var(--accent-strong)' : 'var(--star-active)' }} />
              {a.url ? (
                <a href={a.url} target="_blank" rel="nofollow noreferrer">
                  {a.title}
                </a>
              ) : (
                a.title
              )}
              <span className={cn('a-tag', a.tag)}>{a.tag}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Render plain text with [N] citation markers as linked .cite-chip spans. */
function renderCitations(text: string | undefined, citations: CitationMap): ReactNode {
  if (!text) return null;
  const parts = text.split(/(\[\d+\])/g);
  return parts.map((p, i) => {
    const m = /^\[(\d+)\]$/.exec(p);
    if (!m) return <span key={i}>{p}</span>;
    const n = Number(m[1]);
    const article = citations[n];
    if (article && article.url) {
      return (
        <a key={i} href={article.url} target="_blank" rel="noreferrer" title={article.title || article.source || undefined} className="cite-chip">
          {p}
        </a>
      );
    }
    return (
      <span key={i} className="cite-chip">
        {p}
      </span>
    );
  });
}
