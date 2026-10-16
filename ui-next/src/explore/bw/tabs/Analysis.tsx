import { useEffect, useMemo, useState } from 'react';
import {
  ActivityRow, ArticleCard, Banner, Button, Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, EmptyState, Eyebrow, Grid, Icon, LineChart,
  Panel, Select, SettingRow, Skeleton, Stack, StackedBars, Stat, Text, TextLink,
} from '@aunoo/ui';
import { generateCategoryInsight, getArticles, getSocialPosts, setFindingState, type BWArticle, type BWCategoryInsightResponse, type BWSocialPost } from '@monolith/brandWatcherApi';
import { errorText } from '../../../shell';
import { Markdown } from '../../../shell/Markdown';
import { cleanTitle, TitleLink } from '../../feed/api';
import type { BwContext } from '../context';
import { periodLabel } from '../context';
import { CompetitorView } from './analysis/CompetitorView';
import { InsightStrip } from './analysis/Report';
import { bucketCounts, bucketOf, netOf, plural, short, signed } from './analysis/shared';
import { useAnalysisData } from './analysis/useAnalysisData';
import { useNarrative } from './analysis/useNarrative';
import { brandOf } from './social/helpers';

/*
 * Brand analysis, as the old tab: a verdict line, then reputation, risk and compliance,
 * competitive position, workforce and coverage, each beside the matching section of the brand
 * report. Two buttons call the AI: writing the report and a category's insight.
 */

const SEVERITY_TONE: Record<string, 'error' | 'warning' | 'muted'> = { high: 'error', critical: 'error', medium: 'warning', low: 'muted' };
const CASE_STATES = ['new', 'reviewed', 'escalated', 'dismissed', 'false_positive'] as const;
const caseLabel = (s: string) => s.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
const MIN_SCORED = 3; // weeks with fewer scored items are noise, not signal

function Section({ title }: { title: string }) {
  return <Eyebrow as="h2">{title}</Eyebrow>;
}

/** Monday of the week, matching DATE_TRUNC('week') on the server */
function weekOf(ds: string) {
  const d = new Date(`${ds.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(+d)) return null;
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
  return d.toISOString().slice(0, 10);
}

export function Analysis(ctx: BwContext) {
  const { bw, selectedBrands, focusBrand, goTo, notify } = ctx;
  const brand = selectedBrands[0] ?? focusBrand;
  const days = bw.config.daysBack;
  const competitors = useMemo(() => bw.brands.filter((b) => b.enabled && b.id !== brand?.id), [bw.brands, brand?.id]);
  const d = useAnalysisData(brand?.id ?? null, days, competitors);
  const report = useNarrative(brand?.id ?? null, brand?.display_name, days, notify);
  const [competitorId, setCompetitorId] = useState('none');
  const [insight, setInsight] = useState<{ res: BWCategoryInsightResponse; articles: BWArticle[] } | null>(null);
  const [insightBusy, setInsightBusy] = useState<string | null>(null);
  const { fetchComparison, fetchShareOfVoice, fetchSocial } = bw;

  useEffect(() => {
    void fetchComparison();
    void fetchShareOfVoice();
    // The news-versus-social line needs this brand's social posts (on-brand, scored)
    void fetchSocial(0.4, undefined, false, 'selected');
  }, [fetchComparison, fetchShareOfVoice, fetchSocial, days, brand?.id]);
  useEffect(() => setCompetitorId('none'), [brand?.id]);
  // Every competitor's on-brand social posts, for the dashed "competitor average (social)" line, as the
  // old tab's benchmark snapshot. Reads stored posts only; skipped when there are no competitors.
  const [benchSocial, setBenchSocial] = useState<BWSocialPost[] | null>(null);
  useEffect(() => {
    if (!competitors.length) {
      setBenchSocial(null);
      return;
    }
    let stale = false;
    getSocialPosts(competitors.map((b) => `Brand Monitoring ${b.display_name}`), days, 0.4, undefined, false, { limit: 2000 }).then(
      (r) => !stale && setBenchSocial(r.posts ?? []),
      () => !stale && setBenchSocial(null),
    );
    return () => {
      stale = true;
    };
  }, [competitors, days]);

  const timeline = useMemo(() => {
    const wk: Record<string, { nPos: number; nNeg: number; nTot: number; sPos: number; sNeg: number; sTot: number }> = {};
    const bucket = (w: string) => (wk[w] ||= { nPos: 0, nNeg: 0, nTot: 0, sPos: 0, sNeg: 0, sTot: 0 });
    for (const t of d.weekly) {
      const w = (t.week || '').slice(0, 10);
      if (!w) continue;
      const b = bucket(w);
      for (const [s, n] of Object.entries(t.sentiments)) {
        const k = bucketOf(s);
        if (k === 'positive') b.nPos += n;
        else if (k === 'negative') b.nNeg += n;
        b.nTot += n;
      }
    }
    for (const p of bw.social?.posts ?? []) {
      if (p.review_status === 'false_positive') continue;
      const w = weekOf(p.publication_date ?? '');
      const s = (p.sentiment ?? '').toLowerCase();
      if (!w || !s) continue;
      const b = bucket(w);
      const k = bucketOf(s);
      if (k === 'positive') b.sPos++;
      else if (k === 'negative') b.sNeg++;
      b.sTot++;
    }
    const comp: Record<string, number[]> = {};
    for (const series of d.compWeekly) {
      for (const t of series) {
        const w = (t.week || '').slice(0, 10);
        const c = bucketCounts(t.sentiments);
        const tot = c.positive + c.neutral + c.negative;
        if (w && tot >= MIN_SCORED) (comp[w] ||= []).push(((c.positive - c.negative) / tot) * 100);
      }
    }
    // Competitor average for social: each competitor's weekly net, counted when it has enough scored posts
    const compSocCounts: Record<string, Record<string, { pos: number; neg: number; tot: number }>> = {};
    for (const p of benchSocial ?? []) {
      if (p.review_status === 'false_positive') continue;
      const w = weekOf(p.publication_date ?? '');
      const s = (p.sentiment ?? '').toLowerCase();
      if (!w || !s) continue;
      const c = ((compSocCounts[w] ||= {})[brandOf(p)] ||= { pos: 0, neg: 0, tot: 0 });
      const k = bucketOf(s);
      if (k === 'positive') c.pos++;
      else if (k === 'negative') c.neg++;
      c.tot++;
    }
    const compSoc: Record<string, number[]> = {};
    for (const [w, byBrand] of Object.entries(compSocCounts)) {
      for (const c of Object.values(byBrand)) if (c.tot >= MIN_SCORED) (compSoc[w] ||= []).push(((c.pos - c.neg) / c.tot) * 100);
    }
    const weeks = [...new Set([...Object.keys(wk), ...Object.keys(comp), ...Object.keys(compSoc)])].sort();
    const net = (p: number, n: number, t: number) => (t >= MIN_SCORED ? Math.round(((p - n) / t) * 100) : null);
    return {
      weeks,
      news: weeks.map((w) => (wk[w] ? net(wk[w].nPos, wk[w].nNeg, wk[w].nTot) : null)),
      social: weeks.map((w) => (wk[w] ? net(wk[w].sPos, wk[w].sNeg, wk[w].sTot) : null)),
      comp: weeks.map((w) => (comp[w]?.length ? Math.round(comp[w].reduce((a, b) => a + b, 0) / comp[w].length) : null)),
      compSocial: weeks.map((w) => (compSoc[w]?.length ? Math.round(compSoc[w].reduce((a, b) => a + b, 0) / compSoc[w].length) : null)),
    };
  }, [d.weekly, d.compWeekly, bw.social, benchSocial]);

  if (!brand) return <Panel title="Brand analysis"><EmptyState icon="Target">Pick a brand above to see its analysis.</EmptyState></Panel>;

  const competitor = competitors.find((b) => String(b.id) === competitorId);
  const compareSelect = competitors.length > 0 && (
    <Stack direction="row" justify="end" gap="sm">
      <Select
        label="Compare with"
        hideLabel
        options={[
          { value: 'none', label: `${brand.display_name} on its own` },
          ...competitors.map((b) => ({ value: String(b.id), label: `Compare with ${b.display_name}`, description: `${bw.comparison.find((c) => c.brand_id === b.id)?.total_articles ?? 0} articles` })),
        ]}
        value={competitorId}
        onValueChange={setCompetitorId}
      />
    </Stack>
  );
  if (competitor) {
    return (
      <>
        {compareSelect}
        <CompetitorView brand={brand} competitor={competitor} comparison={bw.comparison} ctx={ctx} />
      </>
    );
  }

  // ── Verdict ──
  const a = d.assessment;
  const issues = a?.active_issues ?? [];
  const spikes = a?.attention?.available ? a.attention.category_spikes ?? [] : [];
  const own = bw.comparison.find((c) => c.brand_id === brand.id);
  const newsNet = own ? netOf(own.sentiment_breakdown) : null;
  const compNets = bw.comparison.filter((c) => c.brand_id !== brand.id).map((c) => netOf(c.sentiment_breakdown)).filter((v): v is number => v != null);
  const compAvg = compNets.length ? Math.round(compNets.reduce((x, y) => x + y, 0) / compNets.length) : null;
  const highRisks = Object.values(d.riskSummary?.by_type ?? {}).reduce((s, t) => s + (t.high || 0), 0);
  const openInc = d.incidents.filter((i) => !['resolved', 'closed'].includes(i.status));
  const outlook = d.employee?.overview?.business_outlook_rating != null ? Math.round(d.employee.overview.business_outlook_rating * 100) : null;
  const facts: string[] = [];
  for (const i of issues.slice(0, 2)) facts.push(`${i.severity}-severity ${i.primary_type.replace(/_/g, ' ')} issue (${plural(i.articles, 'article')}, ${i.momentum})`);
  if (spikes.length) facts.push(`coverage at ${spikes[0].multiple} times normal in ${spikes[0].category}`);
  if (newsNet != null && compAvg != null && newsNet - compAvg <= -15) facts.push(`sentiment ${Math.abs(newsNet - compAvg)} points below the competitor average`);
  if (highRisks) facts.push(plural(highRisks, 'high-severity risk finding'));
  if (openInc.length) facts.push(plural(openInc.length, 'open incident'));
  if (outlook != null && outlook < 45) facts.push(`weak employee outlook (${outlook}% positive)`);
  const level = a?.risk_level ?? null;

  // ── Sentiment by category ──
  const byCat: Record<string, { p: number; u: number; n: number }> = {};
  for (const t of d.trends) {
    const c = (byCat[t.category] ||= { p: 0, u: 0, n: 0 });
    for (const [s, n] of Object.entries(t.sentiments)) {
      const k = bucketOf(s);
      if (k === 'positive') c.p += n;
      else if (k === 'negative') c.n += n;
      else c.u += n;
    }
  }
  const catRows = Object.entries(byCat).sort((x, y) => y[1].p + y[1].u + y[1].n - (x[1].p + x[1].u + x[1].n));

  // ── Category trends ──
  const topCats = bw.categories.filter((c) => c.article_count > 0).slice(0, 6).map((c) => c.category);
  const months = bw.temporalData.map((t) => t.month);
  const trendMax = Math.max(5, ...bw.temporalData.flatMap((t) => topCats.map((c) => t.by_category?.[c] ?? 0)));

  const runInsight = async (category: string) => {
    setInsightBusy(category);
    setInsight(null);
    try {
      const [res, arts] = await Promise.all([
        generateCategoryInsight({ brand_id: brand.id, category, days_back: days }),
        getArticles({ brand_ids: [brand.id], categories: [category], days_back: days, page: 1, per_page: 3 }).then((r) => r.articles, () => [] as BWArticle[]),
      ]);
      setInsight({ res, articles: arts });
    } catch (e) {
      notify(`The insight wasn’t written: ${errorText(e)}`);
    } finally {
      setInsightBusy(null);
    }
  };

  const setCase = (uri: string, riskType: string, status: string) =>
    setFindingState(uri, brand.id, status as (typeof CASE_STATES)[number]).then(
      () => d.setRiskSummary((prev) => (prev ? { ...prev, top_findings: prev.top_findings.map((f) => (f.uri === uri && f.risk_type === riskType ? { ...f, case_status: status } : f)) } : prev)),
      (e: unknown) => notify(`Not changed: ${errorText(e)}`),
    );

  const strip = (key: string, label: string) => <InsightStrip md={report.sections[key]} label={label} onFull={() => goTo('insights')} />;
  const exec = report.sections['executive summary'];
  const sovMax = Math.max(1, ...bw.shareOfVoice.map((s) => s.percentage));

  return (
    <>
      {compareSelect}

      <Panel
        title={`Brand risk: ${a === undefined ? 'checking…' : issues.length === 0 ? 'no active issues' : plural(issues.length, 'active issue')}${level ? `, ${level} severity` : ''}`}
        description={`${brand.display_name}: ${facts.length ? facts.join(' · ') : 'no raised signals in this period'}.`}
      >
        <Grid as="ul" columns={4} stackAt="small" gap="sm" label="Key figures">
          <li><Stat size="compact" surface="panel" label="News sentiment, net" value={signed(newsNet)} meta={compAvg != null ? `competitor average ${signed(compAvg)}` : undefined} tone={newsNet != null && newsNet < 0 ? 'error' : 'default'} /></li>
          <li><Stat size="compact" surface="panel" label="Attention" value={a?.attention?.available ? `${a.attention.overall_multiple ?? '–'}×` : '–'} meta="last 7 days against the weekly average" tone={spikes.length ? 'warning' : 'default'} /></li>
          <li><Stat size="compact" surface="panel" label="High-severity risks" value={highRisks} meta={`last ${d.riskSummary?.days_back ?? days} days`} tone={highRisks ? 'error' : 'default'} /></li>
          <li>
            <Stat size="compact" surface="panel" label="Open incidents" value={openInc.length} tone={openInc.length ? 'error' : 'default'}
              action={<Button variant="ghost" size="sm" onClick={() => goTo('incidents')}>Open</Button>} />
          </li>
          {outlook != null && (
            <li>
              <Stat size="compact" surface="panel" label="Employee outlook" value={`${outlook}%`} meta={d.employee?.overview?.rating != null ? `${d.employee.overview.rating}/5 on Glassdoor` : undefined}
                tone={outlook < 45 ? 'error' : 'default'} action={<Button variant="ghost" size="sm" onClick={() => goTo('workforce')}>Open</Button>} />
            </li>
          )}
        </Grid>
        <Text variant="caption">Attention is coverage volume, which is visibility, not risk; adverse events show up as issues.</Text>
      </Panel>

      <Panel
        title="Executive summary"
        description={report.narrative?.generated_at ? `From the brand report written ${new Date(report.narrative.generated_at).toLocaleDateString('en-GB')}` : undefined}
        headerAside={
          report.narrative ? (
            <Button variant="ghost" size="sm" iconEnd={<Icon name="ArrowRight" size="sm" />} onClick={() => goTo('insights')}>Full report</Button>
          ) : (
            <Button variant="secondary" size="sm" iconStart={<Icon name="Sparkle" size="sm" />} disabled={report.generating} onClick={() => void report.generate()}>
              {report.generating ? 'Writing…' : 'Write the report'}
            </Button>
          )
        }
      >
        {report.loading ? <Skeleton variant="text" lines={3} /> : report.generating && !report.narrative ? (
          <Text variant="caption"><span role="status">The AI is writing the brand report. This takes about a minute.</span></Text>
        ) : report.narrative ? (
          <Markdown text={exec || report.narrative.narrative} />
        ) : (
          <Text>No brand report yet. Writing one reads {periodLabel(days)} of coverage, risks, incidents, social posts and workforce data.</Text>
        )}
      </Panel>
      {strip('forward-looking concerns', 'forward-looking concerns')}

      <Section title="Reputation" />
      {strip('sentiment & reputation', 'sentiment and reputation')}
      {timeline.news.filter((v) => v != null).length + timeline.social.filter((v) => v != null).length >= 2 && (
        <Panel title="Sentiment over time: news and social" description={`Weekly net sentiment (positive − negative, as a share of scored items). Weeks with fewer than ${MIN_SCORED} scored items are left out. The dashed lines are the competitors’ averages for news and for social, from competitors with at least ${MIN_SCORED} scored items that week.`} headingLevel={3}>
          <LineChart
            title="Weekly net sentiment, news and social"
            categories={timeline.weeks.map((w) => w.slice(5))}
            categoryLabels={timeline.weeks.map((w) => `Week of ${w}`)}
            series={[
              { id: 'news', label: 'News', color: 1, values: timeline.news },
              { id: 'social', label: 'Social', color: 2, values: timeline.social },
              ...(timeline.comp.some((v) => v != null) ? [{ id: 'comp', label: 'Competitor average (news)', color: 'neutral' as const, dashed: true, values: timeline.comp }] : []),
              ...(timeline.compSocial.some((v) => v != null) ? [{ id: 'comp-social', label: 'Competitor average (social)', color: 2 as const, dashed: true, values: timeline.compSocial }] : []),
            ]}
            yDomain={[-100, 100]}
            yTicks={[-100, -50, 0, 50, 100]}
            baseline={0}
            formatValue={(v) => signed(v)}
          />
        </Panel>
      )}
      {catRows.length > 0 && (
        <Panel title="Sentiment by category" description="Which areas are souring, even when overall sentiment looks steady. Pick a category to open its articles." headingLevel={3}>
          <Stack gap="md">
            <StackedBars
              title="Sentiment by category"
              series={[{ id: 'p', label: 'Positive', color: 'positive' }, { id: 'u', label: 'Neutral', color: 'neutral' }, { id: 'n', label: 'Negative', color: 'negative' }]}
              rows={catRows.map(([cat, c]) => ({ id: cat, label: cat, values: [c.p, c.u, c.n] }))}
            />
            <Stack direction="row" gap="sm" label="Open a category’s articles">
              {catRows.map(([cat]) => (
                <Chip key={cat} tone="neutral" onClick={() => goTo('articles', { selectedCategories: [cat] })} label={`Open ${cat} articles`}>{short(cat)}</Chip>
              ))}
            </Stack>
          </Stack>
        </Panel>
      )}

      <Section title="Risk and compliance" />
      {strip('risk & compliance', 'risk and compliance')}
      <Grid columns={2} stackAt="wide" gap="md">
        <Panel
          title="Risk findings"
          description={`Adverse findings (legal, regulatory, financial distress, misconduct, workforce, ESG) in the last ${d.riskSummary?.days_back ?? days} days, one per article.`}
          headingLevel={3}
        >
          {!d.riskSummary ? <Skeleton variant="text" lines={4} /> : Object.keys(d.riskSummary.by_type).length === 0 ? <Text>No adverse findings in this period.</Text> : (
            <Stack gap="md">
              <Stack direction="row" gap="sm" label="Findings by type">
                {Object.entries(d.riskSummary.by_type).sort((x, y) => y[1].total - x[1].total).map(([t, c]) => (
                  <Chip key={t} size="sm" tone={c.high ? 'error' : c.medium ? 'warning' : 'muted'}>{t.replace(/_/g, ' ')}: {c.total}{c.high ? `, ${c.high} high` : ''}</Chip>
                ))}
              </Stack>
              <Stack as="ul" gap="sm" label="Top findings">
                {d.riskSummary.top_findings.slice(0, 6).map((f) => (
                  <li key={`${f.uri}|${f.risk_type}`}>
                    <Stack gap="sm">
                      <Stack direction="row" gap="sm">
                        <Chip size="sm" tone={SEVERITY_TONE[f.severity] ?? 'muted'}>{f.severity}</Chip>
                        <Chip size="sm" tone="muted">{f.risk_type.replace(/_/g, ' ')}</Chip>
                        <TextLink href={f.uri} external>{f.title}</TextLink>
                      </Stack>
                      <Select
                        label={`Case status for “${f.title}”`}
                        hideLabel
                        options={CASE_STATES.map((s) => ({ value: s, label: caseLabel(s) }))}
                        value={f.case_status}
                        onValueChange={(v) => void setCase(f.uri, f.risk_type, v)}
                      />
                    </Stack>
                  </li>
                ))}
              </Stack>
            </Stack>
          )}
        </Panel>
        <Panel
          title="Open incidents"
          description="Severity, status and owner are managed on the Incidents tab."
          headingLevel={3}
          headerAside={<Button variant="ghost" size="sm" iconEnd={<Icon name="ArrowRight" size="sm" />} onClick={() => goTo('incidents')}>Incidents</Button>}
        >
          {openInc.length === 0 ? <Text>No open incidents.</Text> : (
            <Stack as="ul" gap="sm" label="Open incidents">
              {openInc.slice(0, 6).map((i) => (
                <ActivityRow key={i.id} as="li" primary={i.title} secondary={`${i.severity} severity · ${i.status}`} dotTone={i.severity === 'high' || i.severity === 'critical' ? 'accent' : 'pending'} />
              ))}
            </Stack>
          )}
        </Panel>
      </Grid>
      {d.alerts.length > 0 && (
        <Panel title="Category spikes" description="Categories with far more coverage this week than usual. Open one to see the articles behind it." headingLevel={3}>
          <Stack gap="sm">
            {d.alerts.map((al) => (
              <Collapsible key={al.category}>
                <SettingRow
                  title={al.category}
                  description={`${al.current_count} this week against an average of ${al.average_count}`}
                  price={<Chip size="sm" tone={al.severity === 'high' ? 'error' : 'warning'}>{al.spike_ratio}× normal</Chip>}
                  actions={<CollapsibleTrigger variant="onSurface">Articles</CollapsibleTrigger>}
                >
                  <CollapsibleContent>
                    {(al.articles ?? []).length === 0 ? <Text variant="caption">No articles listed for this spike.</Text> : (
                      <Stack as="ul" gap="sm" label={`${al.category} spike articles`}>
                        {(al.articles ?? []).map((x) => (
                          <li key={x.uri}>
                            <Stack direction="row" gap="sm">
                              <TitleLink href={x.uri} onOpen={() => ctx.openArticle({ uri: x.uri, title: x.title })}>{cleanTitle(x.title)}</TitleLink>
                              {x.sentiment && <Chip size="sm" tone="muted">{x.sentiment}</Chip>}
                              {x.publication_date && <Text variant="caption" as="span">{x.publication_date.slice(0, 10)}</Text>}
                            </Stack>
                          </li>
                        ))}
                      </Stack>
                    )}
                  </CollapsibleContent>
                </SettingRow>
              </Collapsible>
            ))}
          </Stack>
        </Panel>
      )}

      <Section title="Competitive position" />
      {bw.shareOfVoice.length > 0 && (
        <Panel title="Share of voice" description="Coverage across the tracked brands." headingLevel={3}>
          <StackedBars
            title="Share of voice"
            series={[{ id: 'share', label: 'Share of coverage (%)', color: 1 }]}
            rows={bw.shareOfVoice.map((s) => ({ id: String(s.brand_id), label: `${s.brand_name}${s.brand_id === brand.id ? ' (this brand)' : ''} · ${s.mention_count.toLocaleString('en-GB')} articles`, values: [Math.round(s.percentage)] }))}
          />
          <Text variant="caption">Largest share: {Math.round(sovMax)}%.</Text>
        </Panel>
      )}

      <Section title="Workforce" />
      {strip('workforce signal', 'workforce signal')}
      {d.employee?.overview ? (
        <SettingRow
          title="Workforce signal"
          description={[
            d.employee.overview.rating != null ? `${d.employee.overview.rating}/5 on Glassdoor` : null,
            outlook != null ? `${outlook}% outlook` : null,
            d.employee.review_sentiment.scored > 0 ? `reviews ${d.employee.review_sentiment.pos} positive, ${d.employee.review_sentiment.neg} negative${d.employee.review_sentiment.net != null ? ` (net ${signed(d.employee.review_sentiment.net)})` : ''}` : null,
            d.employee.workforce_risks.length ? plural(d.employee.workforce_risks.length, 'workforce risk') : 'no workforce risks',
          ].filter(Boolean).join(' · ')}
          actions={<Button variant="ghost" size="sm" iconEnd={<Icon name="ArrowRight" size="sm" />} onClick={() => goTo('workforce')}>Workforce</Button>}
        />
      ) : (
        <Text variant="caption">{d.employee ? 'Glassdoor isn’t set up for this brand.' : 'Loading the workforce picture…'}</Text>
      )}

      <Section title="Coverage and sources" />
      {strip('category analysis', 'category analysis')}
      {months.length > 1 && topCats.length > 0 && (
        <Panel title="Category trends over time" description="Articles per month in the six biggest categories. Ask the AI about one with the buttons below." headingLevel={3}>
          <Stack gap="md">
            <LineChart
              title="Articles per month by category"
              categories={months.map((m) => m.slice(5))}
              categoryLabels={months}
              series={topCats.map((c, i) => ({ id: c, label: short(c), color: ((i % 5) + 1) as 1 | 2 | 3 | 4 | 5, values: bw.temporalData.map((t) => t.by_category?.[c] ?? 0) }))}
              yDomain={[0, trendMax]}
              yTicks={[0, Math.round(trendMax / 2), trendMax]}
            />
            <Stack direction="row" gap="sm" label="Ask the AI about a category">
              {topCats.map((c) => (
                <Button key={c} variant="secondary" size="sm" iconStart={<Icon name="Sparkle" size="sm" />} disabled={!!insightBusy} onClick={() => void runInsight(c)}>
                  {insightBusy === c ? 'Writing…' : `${short(c)} (${bw.categories.find((x) => x.category === c)?.article_count ?? 0})`}
                </Button>
              ))}
            </Stack>
          </Stack>
        </Panel>
      )}
      {insight && (
        <Panel
          title={`${insight.res.category}: AI insight`}
          description={`${insight.res.article_count} articles, ${insight.res.percentage}% of coverage, trend ${insight.res.trend}`}
          headingLevel={3}
          headerAside={<Button variant="ghost" size="sm" onClick={() => setInsight(null)}>Close</Button>}
        >
          <Stack gap="md">
            <Markdown text={insight.res.insight} />
            {insight.articles.length > 0 && (
              <Stack as="ul" gap="sm" label="Recent articles in this category">
                {insight.articles.map((x) => (
                  <ArticleCard key={x.uri} as="li" variant="row" headingLevel={4} meta={x.publication_date?.slice(0, 10)}
                    title={<TitleLink href={x.uri} onOpen={() => ctx.openArticle({ uri: x.uri, title: x.title })}>{cleanTitle(x.title)}</TitleLink>} />
                ))}
              </Stack>
            )}
          </Stack>
        </Panel>
      )}
      {d.riskSummary && Object.keys(d.riskSummary.official_sources).length > 0 && (
        <Panel title="Official and scholarly records" description={`Filings, court records, regulations and papers in the last ${d.riskSummary.days_back} days.`} headingLevel={3}>
          <Stack direction="row" gap="sm" label="Records by source">
            {Object.entries(d.riskSummary.official_sources).sort((x, y) => y[1] - x[1]).map(([ns, n]) => <Chip key={ns} size="sm" tone="info">{ns}: {n}</Chip>)}
          </Stack>
        </Panel>
      )}
      {a?.escalation_tier && <Banner tone="warning" title={a.escalation_tier.label} description={`Set by your rules, triggered by: ${a.escalation_tier.triggered.join('; ')}`} />}
    </>
  );
}
