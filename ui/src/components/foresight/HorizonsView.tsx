/**
 * HorizonsPanel / HorizonsView — Three Horizons scenarios, ported from the
 * saas app's shared-dashboard Horizons page (ui/src/pages/HorizonsPage.tsx
 * there): the server-computed S-curve chart with on-curve callouts, the
 * Strategic Consensus cards, the per-horizon scenario columns, and the
 * referenced-article list.
 *
 * Display-only: the caller supplies a HorizonsResponse (see
 * foresightAdapters.toHorizonsResponse) — no fetching, sharing, or Auspex
 * hooks from the saas original.
 */
import { useMemo, ReactNode } from 'react';
import { TrendingDown, TrendingUp, Zap, CheckCircle2, AlertTriangle } from 'lucide-react';
import { cn } from '../ui/utils';
import { HorizonsTitleIcon } from './dashboardIcons';
import type { ReferencedArticle } from './ConsensusView';
import '../../styles/shared-dashboard.css';

// ─── Types ──────────────────────────────────────────────────────────────────

type HorizonType = 'h1' | 'h2' | 'h3';

export interface Scenario {
  type: HorizonType;
  title: string;
  description: string;
  timeframe?: string;
  timeline_start?: number;
  timeline_end?: number;
  sentiment?: string;
}

export interface DecisionFork {
  branch: 'positive' | 'warning' | string;
  if_clause: string;
  then_clause: string;
}

export interface ExecutiveSummary {
  title: string;
  summary: string;
  consensus_pct?: number;
  minority_view?: string;
  primary_signal?: string;
  decision_fork?: DecisionFork[];
  underlying_scenarios?: string[];
}

export interface HorizonsResponse {
  scenarios: Scenario[];
  executive_summaries?: ExecutiveSummary[];
  article_count: number;
  articles?: ReferencedArticle[];
  topic?: string;
}

type CitationMap = Record<number, ReferencedArticle>;

// ─── Chart geometry (ported from the saas renderers/horizons.py) ────────────

const VW = 1000;
const VH = 320;
const L = 24;
const RR = 976;
const TOP = 24;
const BOT = 290;
const NSEG = 160;
const SPAN = RR - L;
const HGT = BOT - TOP;

const AXIS_PHASES = ['Present', 'Short-term', 'Mid-term', 'Long-term', 'Horizon'];

type ColId = 'current' | 'transition' | 'future';

const clamp01 = (x: number) => Math.max(0, Math.min(1, x));
const round1 = (x: number) => Math.round(x * 10) / 10;

function ss(x: number): number {
  x = clamp01(x);
  return x * x * (3 - 2 * x);
}

const CURVES: Record<ColId, (t: number) => number> = {
  current: (t) => 0.06 + 0.74 * (1 - ss((t - 0.05) / 0.75)),
  transition: (t) => (t < 0.38 ? 0.42 + 0.2 * ss(t / 0.38) : 0.62 - 0.48 * ss((t - 0.38) / 0.62)),
  future: (t) => 0.05 + 0.81 * ss((t - 0.28) / 0.78),
};

const X = (t: number) => L + t * SPAN;
const Y = (v: number) => BOT - v * HGT;

function curveTopPct(col: ColId, xPct: number): number {
  const vbX = (xPct / 100) * VW;
  const t = clamp01((vbX - L) / SPAN);
  const v = CURVES[col](t);
  return round1(Math.max(6, Math.min(90, ((BOT - v * HGT) / VH) * 100)));
}

interface Chart {
  area: Record<ColId, string>;
  line: Record<ColId, string>;
  gridXs: number[];
  badges: Record<ColId, number>;
}

function buildChart(): Chart {
  const area = (f: (t: number) => number): string => {
    const d = [`M ${X(0).toFixed(1)} ${BOT}`];
    for (let i = 0; i <= NSEG; i++) d.push(`L ${X(i / NSEG).toFixed(1)} ${Y(f(i / NSEG)).toFixed(1)}`);
    d.push(`L ${X(1).toFixed(1)} ${BOT} Z`);
    return d.join(' ');
  };
  const line = (f: (t: number) => number): string => {
    const pts: string[] = [];
    for (let i = 0; i <= NSEG; i++) pts.push(`${i === 0 ? 'M' : 'L'} ${X(i / NSEG).toFixed(1)} ${Y(f(i / NSEG)).toFixed(1)}`);
    return pts.join(' ');
  };
  return {
    area: { current: area(CURVES.current), transition: area(CURVES.transition), future: area(CURVES.future) },
    line: { current: line(CURVES.current), transition: line(CURVES.transition), future: line(CURVES.future) },
    gridXs: [0, 1, 2, 3, 4].map((i) => X(i / 4)),
    badges: {
      current: round1((Y(CURVES.current(0)) / VH) * 100),
      transition: round1((Y(CURVES.transition(0)) / VH) * 100),
      future: round1((Y(CURVES.future(0)) / VH) * 100),
    },
  };
}

/** Declutter callout x-positions: keep time order but enforce a min gap. */
function spread(desired: number[], lo = 6, hi = 94): number[] {
  const n = desired.length;
  if (n <= 1) return desired.map((d) => Math.max(lo, Math.min(hi, d)));
  const gap = Math.min(16, (hi - lo) / (n - 1));
  const order = [...Array(n).keys()].sort((a, b) => desired[a] - desired[b]);
  const xs = new Array(n).fill(0);
  let prev = -Infinity;
  for (const i of order) {
    const x = Math.max(desired[i], prev + gap);
    xs[i] = x;
    prev = x;
  }
  const overflow = xs[order[order.length - 1]] - hi;
  if (overflow > 0) {
    prev = lo - gap;
    for (const i of order) {
      const x = Math.max(xs[i] - overflow, prev + gap, lo);
      xs[i] = x;
      prev = x;
    }
  }
  return xs;
}

interface Callout {
  x: number;
  y: number;
  colId: ColId;
  eyebrow: string;
  title: string;
  body: string;
  meta: string;
  hAlign: 'tip-left' | 'tip-right' | 'tip-mid';
  vAlign: 'tip-below' | 'tip-above';
}

/** Nudge callout y-positions apart so overlapping cards separate. In-place. */
function decollide(callouts: Callout[]): void {
  const CARD_W = 15;
  const CARD_H = 12;
  for (let it = 0; it < 80; it++) {
    let moved = false;
    for (let i = 0; i < callouts.length; i++) {
      for (let j = i + 1; j < callouts.length; j++) {
        const a = callouts[i];
        const b = callouts[j];
        if (Math.abs(a.x - b.x) >= CARD_W) continue;
        const dy = b.y - a.y;
        if (Math.abs(dy) >= CARD_H) continue;
        const push = (CARD_H - Math.abs(dy)) / 2 + 0.1;
        if (dy >= 0) {
          a.y -= push;
          b.y += push;
        } else {
          a.y += push;
          b.y -= push;
        }
        moved = true;
      }
    }
    if (!moved) break;
  }
  for (const c of callouts) c.y = round1(Math.max(4, Math.min(92, c.y)));
}

const HORIZON_META: Record<HorizonType, { colId: ColId; title: string; sub: string; Icon: typeof TrendingDown; eyebrow: string }> = {
  h1: { colId: 'current', title: 'Current', sub: 'Declining', Icon: TrendingDown, eyebrow: 'Horizon 1 — Declining' },
  h2: { colId: 'transition', title: 'Transition', sub: 'Innovation', Icon: Zap, eyebrow: 'Horizon 2 — Innovation' },
  h3: { colId: 'future', title: 'Future', sub: 'Emerging Vision', Icon: TrendingUp, eyebrow: 'Horizon 3 — Emerging Vision' },
};

function asYear(v: unknown): number | null {
  const y = typeof v === 'number' ? v : Number(v);
  if (!Number.isFinite(y)) return null;
  return y > 1900 && y < 2200 ? Math.trunc(y) : null;
}

function timelineSpan(scenarios: Scenario[]): [number, number] {
  const years: number[] = [];
  for (const s of scenarios) {
    const a = asYear(s.timeline_start);
    const b = asYear(s.timeline_end);
    if (a !== null && b !== null) years.push(a, b);
  }
  const nowY = new Date().getFullYear();
  if (years.length === 0) return [nowY, nowY + 15];
  const lo = Math.max(Math.min(...years), nowY);
  const hi = Math.max(...years);
  return [lo, hi > lo ? hi : lo + 1];
}

const LEAD_LABEL = /^\s*(primary signal|minority view)\b[^:.]*[:.]\s*/i;
const stripLead = (t: string) => (t || '').replace(LEAD_LABEL, '').trim();

interface ColumnVM {
  colId: ColId;
  title: string;
  sub: string;
  Icon: typeof TrendingDown;
  eyebrow: string;
  scenarios: Array<{
    title: string;
    body: string;
    range: string;
    geom: { rangeLeft: number; rangeWidth: number; peakLeft: number | null; tl: boolean };
  }>;
}

interface HorizonsVM {
  columns: ColumnVM[];
  callouts: Callout[];
  axisTicks: Array<{ year: number; phase: string }>;
  consCards: Array<{
    title: string;
    consensusPct?: number;
    body: string;
    minority: string;
    signal: string;
    forks: Array<{ kind: 'pos' | 'warn'; title: string; text: string }>;
    scenarios: string[];
  }>;
}

function buildHorizonsVM(data: HorizonsResponse): HorizonsVM {
  const scenarios = (data.scenarios || []).filter(Boolean);
  const [lo, hi] = timelineSpan(scenarios);
  const yp = (y: number | null): number | null => {
    if (y === null || hi <= lo) return null;
    return round1(Math.max(0, Math.min(100, ((y - lo) / (hi - lo)) * 100)));
  };

  const columns: ColumnVM[] = [];
  const callouts: Callout[] = [];

  for (const h of ['h1', 'h2', 'h3'] as HorizonType[]) {
    const meta = HORIZON_META[h];
    const group = scenarios.filter((s) => s.type === h);
    const colScenarios: ColumnVM['scenarios'] = [];
    const peaks: Array<number | null> = [];
    for (const s of group) {
      let a = asYear(s.timeline_start);
      let b = asYear(s.timeline_end);
      let peakPct: number | null = null;
      let geom: ColumnVM['scenarios'][number]['geom'];
      let rangeStr = '';
      if (a !== null && b !== null) {
        a = Math.max(Math.min(a, b), lo);
        b = Math.max(Math.max(a, b), lo);
        const peak = Math.round((a + b) / 2);
        peakPct = yp(peak);
        geom = {
          rangeLeft: yp(a) ?? 0,
          rangeWidth: Math.max((yp(b) ?? 0) - (yp(a) ?? 0), 2),
          peakLeft: peakPct,
          tl: true,
        };
        rangeStr = `${a}–${b}`;
      } else {
        geom = { rangeLeft: 0, rangeWidth: 0, peakLeft: null, tl: false };
      }
      peaks.push(peakPct);
      colScenarios.push({ title: s.title || '', body: s.description || '', range: rangeStr, geom });
    }
    columns.push({ colId: meta.colId, title: meta.title, sub: meta.sub, Icon: meta.Icon, eyebrow: meta.eyebrow, scenarios: colScenarios });

    const desired = peaks.map((p) => (p !== null ? p : 50));
    const xs = spread(desired);
    group.forEach((s, i) => {
      const x = round1(xs[i]);
      callouts.push({
        x,
        y: curveTopPct(meta.colId, x),
        colId: meta.colId,
        eyebrow: meta.eyebrow,
        title: s.title || '',
        body: s.description || '',
        meta: colScenarios[i].range + (s.sentiment ? ` · ${s.sentiment}` : ''),
        hAlign: x <= 30 ? 'tip-left' : x >= 72 ? 'tip-right' : 'tip-mid',
        vAlign: meta.colId === 'current' ? 'tip-below' : 'tip-above',
      });
    });
  }
  decollide(callouts);

  const consCards: HorizonsVM['consCards'] = (data.executive_summaries || []).map((e) => ({
    title: e.title || '',
    consensusPct: e.consensus_pct,
    body: e.summary || '',
    minority: stripLead(e.minority_view || ''),
    signal: stripLead(e.primary_signal || ''),
    forks: (e.decision_fork || []).map((f) => ({
      kind: (f.branch || '').toLowerCase().startsWith('pos') ? ('pos' as const) : ('warn' as const),
      title: f.if_clause || '',
      text: f.then_clause || '',
    })),
    scenarios: (e.underlying_scenarios || []).filter(Boolean),
  }));

  const axisTicks = [0, 1, 2, 3, 4].map((i) => ({
    year: Math.round(lo + ((hi - lo) * i) / 4),
    phase: AXIS_PHASES[i],
  }));

  return { columns, callouts, axisTicks, consCards };
}

// ─── Panel (title row + content + footer) ───────────────────────────────────

export function HorizonsPanel({
  data,
  actions = null,
  onGenerate,
}: {
  data: HorizonsResponse | null;
  /** Optional buttons rendered in the title row (export, generate, …). */
  actions?: ReactNode;
  /** Renders a Generate button in the empty state when no scenarios exist. */
  onGenerate?: () => void;
}) {
  const scenarios = data?.scenarios ?? [];
  const execSummaries = data?.executive_summaries ?? [];
  const hasContent = scenarios.length > 0 || execSummaries.length > 0;
  const topicLabel = data?.topic || 'All Topics';

  return (
    <div className="aunoo-dash w-full">
      <main className="area">
        <div className="area-inner">
          <div className="title-row">
            <HorizonsTitleIcon />
            <div className="title-text">
              <h1>Future Horizons{topicLabel ? ` — ${topicLabel}` : ''}</h1>
              <p className="subhead">
                {data?.article_count ? (
                  <>
                    Analyzed <b>{data.article_count}</b> articles
                    {topicLabel && topicLabel !== 'All Topics' ? ` for ${topicLabel}` : ''} · Three Horizons scenario synthesis
                  </>
                ) : (
                  'Three Horizons scenario synthesis across coverage'
                )}
              </p>
            </div>
            {actions && <div className="title-actions">{actions}</div>}
          </div>

          {!hasContent && (
            <div className="panel" style={{ textAlign: 'center', padding: '32px 16px' }}>
              <h3 style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>Not yet analyzed</h3>
              <p className="panel-sub" style={{ margin: '6px 0 0' }}>
                Run a Future Horizons analysis for this topic to populate the Three Horizons scenarios.
              </p>
              {onGenerate && (
                <button
                  type="button"
                  onClick={onGenerate}
                  className="inline-flex items-center gap-2 text-sm font-semibold px-4 py-2 rounded-md text-white"
                  style={{ background: 'var(--accent)', marginTop: 14 }}
                >
                  <Zap className="w-4 h-4" />
                  Generate Analysis
                </button>
              )}
              {onGenerate && (
                <p className="panel-sub" style={{ margin: '8px 0 0' }}>
                  This analyzes the topic's articles and takes 30–60 seconds.
                </p>
              )}
            </div>
          )}

          {hasContent && data && <HorizonsView data={data} />}

          {hasContent && (
            <footer className="disclosure">
              <div className="meta">Future Horizons · Powered by AunooAI · aunoo.ai</div>
              <em>The analysis is AI-generated from news coverage — AunooAI does not adjudicate truth. Verify claims against the cited sources.</em>
            </footer>
          )}
        </div>
      </main>
    </div>
  );
}

// ─── Content view ───────────────────────────────────────────────────────────

export function HorizonsView({ data }: { data: HorizonsResponse }) {
  const vm = useMemo(() => buildHorizonsVM(data), [data]);
  const chart = useMemo(() => buildChart(), []);
  const citations: CitationMap = useMemo(() => {
    const map: CitationMap = {};
    (data.articles || []).forEach((a) => {
      if (typeof a.citation_number === 'number') map[a.citation_number] = a;
    });
    return map;
  }, [data.articles]);

  const articles = useMemo(
    () => [...(data.articles || [])].sort((a, b) => (a.citation_number ?? 0) - (b.citation_number ?? 0)),
    [data.articles],
  );

  const colVar: Record<ColId, string> = {
    current: 'var(--h-current)',
    transition: 'var(--h-transition)',
    future: 'var(--h-future)',
  };

  return (
    <>
      {/* Three Horizons chart */}
      <section className="panel">
        <div className="panel-head">
          <span className="panel-title">Three Horizons Model</span>
        </div>
        <p className="panel-sub">
          Visualizing the transition from current systems (H1) through emerging innovations (H2) to future visions (H3). Hover or focus any label to read its full scenario.
        </p>
        <div className="hc-wrap">
          <div className="hc-stage">
            <svg
              className="hc-svg"
              viewBox={`0 0 ${VW} ${VH}`}
              preserveAspectRatio="none"
              role="img"
              aria-label="Three Horizons chart: the Current horizon declines while the Transition horizon peaks mid-timeline and the Future horizon rises."
            >
              {chart.gridXs.map((gx, i) => (
                <line key={i} x1={gx} y1={TOP} x2={gx} y2={BOT} stroke="var(--sidebar-border)" strokeWidth={1} />
              ))}
              <path d={chart.area.future} fill="var(--h-future)" fillOpacity={0.42} />
              <path d={chart.area.transition} fill="var(--h-transition)" fillOpacity={0.42} />
              <path d={chart.area.current} fill="var(--h-current)" fillOpacity={0.42} />
              <path d={chart.line.future} fill="none" stroke="var(--h-future)" strokeWidth={2.5} strokeLinejoin="round" />
              <path d={chart.line.transition} fill="none" stroke="var(--h-transition)" strokeWidth={2.5} strokeLinejoin="round" />
              <path d={chart.line.current} fill="none" stroke="var(--h-current)" strokeWidth={2.5} strokeLinejoin="round" />
            </svg>

            {(['current', 'transition', 'future'] as ColId[]).map((id) => (
              <span key={id} className="band-label" style={{ left: '1.6%', top: `${chart.badges[id]}%` }}>
                <span className="bd" style={{ background: colVar[id] }} />
                {id === 'current' ? 'Current' : id === 'transition' ? 'Transition' : 'Future'}
              </span>
            ))}

            {vm.callouts.map((c, i) => (
              <div
                key={i}
                className="hc-callout"
                style={{ left: `${c.x}%`, top: `${c.y}%`, borderLeftColor: colVar[c.colId] }}
                tabIndex={0}
                role="button"
              >
                <span className="ctitle">{c.title}</span>
                <div className={cn('hc-tip', c.hAlign, c.vAlign)} role="tooltip">
                  <div className="tip-eyebrow" style={{ color: colVar[c.colId] }}>
                    <span className="bd" style={{ background: colVar[c.colId] }} />
                    {c.eyebrow}
                  </div>
                  <div className="tip-title">{c.title}</div>
                  <p className="tip-body">{renderCitations(c.body, citations)}</p>
                  {c.meta ? <div className="tip-meta">{c.meta}</div> : null}
                </div>
              </div>
            ))}
          </div>
          <div className="hc-axis" aria-hidden="true">
            {vm.axisTicks.map((t, i) => (
              <div className="tick" key={i}>
                <span className="yr">{t.year}</span>
                <span className="ph">{t.phase}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Strategic consensus */}
      {vm.consCards.length > 0 && (
        <section className="panel">
          <div className="panel-head">
            <span className="panel-title" style={{ color: 'var(--accent)' }}>
              Strategic Consensus
            </span>
          </div>
          <div className="cons-grid">
            {vm.consCards.map((c, i) => (
              <div className="cons-card" key={i}>
                <div className="cons-top">
                  <div className="cons-title">{c.title}</div>
                  {c.consensusPct != null && (
                    <div className="cons-badge">
                      <div className="pc">{c.consensusPct}%</div>
                      <span className="lb">consensus</span>
                    </div>
                  )}
                </div>
                {c.body && <p className="cons-body">{renderCitations(c.body, citations)}</p>}
                {c.minority && <div className="minority">Minority view: {renderCitations(c.minority, citations)}</div>}
                {c.signal && (
                  <>
                    <div className="sig-label">Primary signal{c.consensusPct != null ? ` (${c.consensusPct}% consensus)` : ''}</div>
                    <p className="sig-body">{renderCitations(c.signal, citations)}</p>
                  </>
                )}
                {c.forks.length > 0 && (
                  <>
                    <div className="fork-label">Decision fork</div>
                    {c.forks.map((f, j) => (
                      <div className={cn('fork', f.kind)} key={j}>
                        {f.kind === 'pos' ? <CheckCircle2 /> : <AlertTriangle />}
                        <div>
                          <div className="f-title">{f.title}</div>
                          <div className="f-text">{f.text}</div>
                        </div>
                      </div>
                    ))}
                  </>
                )}
                {c.scenarios.length > 0 && (
                  <div className="based-on">
                    <div className="bo-label">
                      Based on {c.scenarios.length} underlying scenario{c.scenarios.length === 1 ? '' : 's'}
                    </div>
                    {c.scenarios.map((s, j) => (
                      <div className="bo-row" key={j}>
                        {s}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Scenarios by horizon */}
      <section className="panel">
        <div className="panel-head">
          <span className="panel-title" style={{ color: 'var(--m-deepresearch)' }}>
            Scenarios by Horizon
          </span>
        </div>
        <div className="cols-grid">
          {vm.columns.map((col) =>
            col.scenarios.length > 0 ? (
              <div className={cn('col', col.colId)} key={col.colId}>
                <div className="col-head">
                  <col.Icon />
                  <div>
                    <span className="ch-title">{col.title}</span>
                    <span className="ch-sub">{col.sub}</span>
                  </div>
                </div>
                <div className="col-body">
                  {col.scenarios.map((s, i) => (
                    <div className="scn-card" key={i}>
                      <div className="scn-eyebrow">
                        <span className="bd" style={{ background: colVar[col.colId] }} />
                        {col.eyebrow}
                      </div>
                      <div className="scn-title">{s.title}</div>
                      {s.body && <p className="scn-body">{renderCitations(s.body, citations)}</p>}
                      {s.geom.tl && <MiniTimeline geom={s.geom} axisTicks={vm.axisTicks} color={colVar[col.colId]} />}
                    </div>
                  ))}
                </div>
              </div>
            ) : null,
          )}
        </div>
      </section>

      {articles.length > 0 && (
        <details className="refs">
          <summary>
            Referenced Articles ({articles.length})
            <span className="ref-chev" aria-hidden="true">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </span>
          </summary>
          <div className="refs-body">
            <div className="refs-list">
              {articles.map((a, i) => (
                <div className="ref-row" key={a.citation_number ?? i}>
                  <span className="ref-num">[{a.citation_number}]</span>
                  <span className="ref-content">
                    {a.url ? (
                      <a href={a.url} className="ref-title" target="_blank" rel="nofollow noreferrer">
                        {a.title || a.url}
                      </a>
                    ) : (
                      <span className="ref-title">{a.title || 'Untitled'}</span>
                    )}
                    {a.source ? <span className="ref-src"> · {a.source}</span> : null}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </details>
      )}
    </>
  );
}

function MiniTimeline({
  geom,
  axisTicks,
  color,
}: {
  geom: { rangeLeft: number; rangeWidth: number; peakLeft: number | null };
  axisTicks: Array<{ year: number; phase: string }>;
  color: string;
}) {
  return (
    <div className="mini-tl" aria-hidden="true">
      <div className="mt-track" />
      {axisTicks.map((t, i) => (
        <span key={`t${i}`}>
          <span className="mt-tick" style={{ left: `${i * 25}%` }} />
          <span className="mt-yr" style={{ left: `${i * 25}%` }}>
            {t.year}
          </span>
        </span>
      ))}
      <span className="mt-range" style={{ left: `${geom.rangeLeft}%`, width: `${geom.rangeWidth}%`, background: color }} />
      {geom.peakLeft != null && <span className="mt-peak" style={{ left: `${geom.peakLeft}%`, background: color }} />}
    </div>
  );
}

/** Render plain text with [N] citation markers as linked .cite-chip spans. */
function renderCitations(text: string, citations: CitationMap): ReactNode {
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
