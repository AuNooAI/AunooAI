import { useEffect, useState } from 'react';
import {
  ActivityRow, Banner, Button, Chip, EmptyState, Grid, Icon, LineChart, Panel, Select, Skeleton, Stack, Stat, Table, Text, TextField, TextLink,
} from '@aunoo/ui';
import {
  getEmployeeRisk, pollOfficialSourcesNow, setFindingState, updateBrandConfig, type BWEmployeeRisk, type BWGlassdoorOverview,
} from '@monolith/brandWatcherApi';
import { errorText } from '../../../shell';
import type { BwContext } from '../context';
import { GroupedBars, RatingBar } from '../charts';

/*
 * Employee signal for one brand (old Workforce tab): Glassdoor ratings and their history,
 * competitors' ratings, recent employee reviews and workforce risk findings, from
 * GET /api/brand-watcher/brands/{id}/employee-risk. The server keeps Glassdoor figures for 24 hours;
 * "Refresh from Glassdoor" forces a new paid lookup, so it is a button.
 */

type SubKey = keyof BWGlassdoorOverview;
const SUBS: { label: string; key: SubKey }[] = [
  { label: 'Work-life balance', key: 'work_life_balance_rating' },
  { label: 'Culture and values', key: 'culture_and_values_rating' },
  { label: 'Pay and benefits', key: 'compensation_and_benefits_rating' },
  { label: 'Senior management', key: 'senior_management_rating' },
  { label: 'Career opportunities', key: 'career_opportunities_rating' },
  { label: 'Diversity and inclusion', key: 'diversity_and_inclusion_rating' },
];
const STATES = ['new', 'reviewed', 'escalated', 'dismissed', 'false_positive'];
const STATE_LABEL: Record<string, string> = { new: 'New', reviewed: 'Reviewed', escalated: 'Escalated', dismissed: 'Dismissed', false_positive: 'False positive' };

const pct = (v?: number | null) => (v == null ? null : Math.round(v * 100));
const num = (v: unknown): v is number => typeof v === 'number';

/** "Glassdoor review (4/5): headline" plus "Role: … | Pros: … | Cons: …" in the summary */
function parseReview(r: { title: string; summary?: string | null }) {
  const m = r.title.match(/^Glassdoor review(?: \((\d)\/5\))?: (.*)$/);
  const seg = (name: string) => (r.summary ?? '').match(new RegExp(`${name}: ([^|]*)(\\||$)`))?.[1].trim() ?? null;
  return { rating: m?.[1] ? parseInt(m[1], 10) : null, headline: m?.[2] || r.title, role: seg('Role'), pros: seg('Pros'), cons: seg('Cons') };
}

export function Workforce(ctx: BwContext) {
  const { bw, focusBrand: brand, notify } = ctx;
  const [er, setEr] = useState<BWEmployeeRisk | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [companyId, setCompanyId] = useState('');

  const load = async (refresh = false) => {
    if (!brand) return;
    setLoading(true);
    setError(null);
    try {
      setEr(await getEmployeeRisk(brand.id, bw.config.daysBack, refresh));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    setEr(null);
    void load(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [brand?.id, bw.config.daysBack]);

  if (!brand) return <EmptyState icon="Users" title="No brand">Pick a brand to see its workforce picture.</EmptyState>;
  if (error) return <Banner tone="error" title="Workforce data didn’t load" description={error} action={<Button size="sm" variant="secondary" onClick={() => void load(false)}>Try again</Button>} />;
  if (!er) return <Skeleton variant="block" size="card" />;

  if (!er.glassdoor_enabled) {
    return (
      <EmptyState icon="Users" title="Glassdoor isn’t on for this brand">
        Turn on Glassdoor for {brand.display_name} under “Official and scholarly sources” (the book button at the top of Brand Watcher). Ratings and reviews arrive with the next daily poll.
      </EmptyState>
    );
  }

  const applyCompanyId = async () => {
    const m = companyId.match(/-E(\d+)\b/) || companyId.match(/^\s*(\d+)\s*$/);
    if (!m) {
      notify('No company ID found. Paste the Glassdoor reviews link or just the number after “-E”.');
      return;
    }
    setLoading(true);
    try {
      await updateBrandConfig(brand.id, { glassdoor_company_id: Number(m[1]) });
      await pollOfficialSourcesNow(brand.id);
      setEr(await getEmployeeRisk(brand.id, bw.config.daysBack, true));
      notify('Glassdoor company set');
    } catch (e) {
      notify(`Not applied: ${errorText(e)}`);
    } finally {
      setLoading(false);
    }
  };

  const ov = er.overview;
  if (!ov && !er.reviews.length && !er.history.length) {
    return (
      <Panel title="No Glassdoor profile found" description={`Glassdoor is on, but no employer page matched “${brand.display_name}”. Smaller companies often have none. If this one does, give its company ID: the number after “-E” in its reviews link.`}>
        <Stack gap="sm">
          <TextField label="Glassdoor reviews link or company ID" placeholder="https://www.glassdoor.com/Reviews/Wiley-Reviews-E1551.htm" value={companyId} onChange={setCompanyId} />
          <div><Button disabled={loading || !companyId.trim()} onClick={() => void applyCompanyId()}>{loading ? 'Looking it up…' : 'Set company'}</Button></div>
          <Text variant="caption">This fetches the profile from Glassdoor straight away.</Text>
        </Stack>
      </Panel>
    );
  }

  const comps = er.competitors;
  const compAvg = (key: SubKey) => {
    const vals = comps.map((c) => c.overview[key]).filter(num);
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  };
  // Biggest sub-rating gap against any competitor: the takeaway line
  let gap: { sub: string; delta: number; vs: string } | null = null;
  if (ov) {
    for (const s of SUBS) {
      const own = ov[s.key];
      if (!num(own)) continue;
      for (const c of comps) {
        const cv = c.overview[s.key];
        if (!num(cv)) continue;
        if (!gap || Math.abs(own - cv) > Math.abs(gap.delta)) gap = { sub: s.label.toLowerCase(), delta: own - cv, vs: c.brand_name };
      }
    }
  }

  // Change against the oldest snapshot within about 35 days
  const hist = er.history;
  const change = (key: 'rating' | 'business_outlook_rating' | 'ceo_rating' | 'recommend_to_friend_rating', asPct: boolean) => {
    if (hist.length < 2) return '';
    const latest = hist[hist.length - 1];
    const cutoff = new Date(new Date(`${latest.date}T00:00:00Z`).getTime() - 35 * 86400000).toISOString().slice(0, 10);
    const base = hist.find((h) => h.date >= cutoff) ?? hist[0];
    const a = base[key];
    const b = latest[key];
    if (base.date === latest.date || !num(a) || !num(b) || Math.abs(b - a) < (asPct ? 0.005 : 0.05)) return '';
    const v = asPct ? `${Math.abs(Math.round((b - a) * 100))} points` : Math.abs(b - a).toFixed(1);
    return ` · ${b < a ? 'down' : 'up'} ${v} since ${base.date}`;
  };
  const tone = (v: number | null, good: number, bad: number) => (v == null ? 'default' : v >= good ? 'success' : v < bad ? 'error' : 'default');

  const pts = hist.filter((h) => h.rating != null || h.business_outlook_rating != null);
  const rs = er.review_sentiment;
  const brandsTable = ov ? [{ brand_id: brand.id, brand_name: brand.display_name, overview: ov }, ...comps] : comps;

  return (
    <>
      <Panel
        title={`Glassdoor: ${ov?.name || brand.display_name}`}
        description={[ov?.review_count ? `${ov.review_count.toLocaleString('en-GB')} reviews` : null, ov?.industry].filter(Boolean).join(' · ') || undefined}
        headerAside={<Button size="sm" variant="secondary" iconStart={<Icon name="ArrowClockwise" size="sm" />} disabled={loading} onClick={() => void load(true)}>{loading ? 'Refreshing…' : 'Refresh from Glassdoor'}</Button>}
      >
        <Grid as="ul" columns={4} stackAt="small" gap="sm" label="Glassdoor ratings">
          <li><Stat surface="panel" label="Overall rating" value={ov?.rating != null ? `${ov.rating}/5` : '–'} meta={`${ov?.company_size ?? ''}${change('rating', false)}`} tone={tone(ov?.rating ?? null, 3.5, 3)} /></li>
          <li><Stat surface="panel" label="CEO approval" value={pct(ov?.ceo_rating) != null ? `${pct(ov?.ceo_rating)}%` : '–'} meta={`${ov?.ceo ?? ''}${change('ceo_rating', true)}`} tone={tone(pct(ov?.ceo_rating), 70, 50)} /></li>
          <li><Stat surface="panel" label="Positive business outlook" value={pct(ov?.business_outlook_rating) != null ? `${pct(ov?.business_outlook_rating)}%` : '–'} meta={change('business_outlook_rating', true).replace(/^ · /, '') || undefined} tone={tone(pct(ov?.business_outlook_rating), 60, 45)} /></li>
          <li><Stat surface="panel" label="Would recommend to a friend" value={pct(ov?.recommend_to_friend_rating) != null ? `${pct(ov?.recommend_to_friend_rating)}%` : '–'} meta={change('recommend_to_friend_rating', true).replace(/^ · /, '') || undefined} tone={tone(pct(ov?.recommend_to_friend_rating), 70, 50)} /></li>
        </Grid>
      </Panel>

      {ov && (
        <Grid columns={2} stackAt="wide" gap="md">
          <Panel title="Sub-ratings" description={comps.length ? `Out of 5, against the average of ${comps.map((c) => c.brand_name).join(', ')}.` : 'Out of 5.'} headingLevel={3}>
            <Stack as="ul" gap="sm" label="Sub-ratings">
              {SUBS.map((s) => {
                const own = ov[s.key];
                if (!num(own)) return null;
                return (
                  <li key={s.key}>
                    <RatingBar label={s.label} value={own} avg={compAvg(s.key)} />
                  </li>
                );
              })}
            </Stack>
            {comps.length > 0 && <Text variant="caption">The dark tick on each bar is the competitors’ average.</Text>}
          </Panel>
          <Panel title="Employer ratings against competitors" headingLevel={3}>
            {comps.length === 0 ? <Text>No competitor Glassdoor data yet. Turn on Glassdoor for competitor brands under sources.</Text> : (
              <Stack gap="md">
                <Table
                  caption="Employer ratings by brand"
                  hideCaption
                  rows={brandsTable}
                  rowKey={(c) => String(c.brand_id)}
                  columns={[
                    { key: 'brand', header: 'Brand', rowHeader: true, render: (c) => c.brand_name },
                    { key: 'rating', header: 'Overall', align: 'end', render: (c) => (c.overview.rating != null ? `${c.overview.rating}/5` : '–') },
                    { key: 'outlook', header: 'Outlook', align: 'end', render: (c) => (pct(c.overview.business_outlook_rating) != null ? `${pct(c.overview.business_outlook_rating)}%` : '–') },
                    { key: 'ceo', header: 'CEO', align: 'end', render: (c) => (pct(c.overview.ceo_rating) != null ? `${pct(c.overview.ceo_rating)}%` : '–') },
                    { key: 'recommend', header: 'Recommend', align: 'end', render: (c) => (pct(c.overview.recommend_to_friend_rating) != null ? `${pct(c.overview.recommend_to_friend_rating)}%` : '–') },
                    ...SUBS.map((s) => ({ key: s.key as string, header: s.label, align: 'end' as const, render: (c: (typeof brandsTable)[number]) => { const v = c.overview[s.key]; return num(v) ? v.toFixed(1) : '–'; } })),
                  ]}
                />
                {/* The old tab drew the sub-ratings side by side for every brand, in brand colours */}
                <GroupedBars
                  title="Sub-ratings by brand, out of 5"
                  max={5}
                  groups={SUBS.filter((s) => brandsTable.some((c) => num(c.overview[s.key]))).map((s) => ({ id: String(s.key), label: s.label }))}
                  series={brandsTable.map((c, i) => ({
                    id: String(c.brand_id),
                    label: c.brand_name,
                    color: ctx.bw.brands.find((b) => b.id === c.brand_id)?.color || `var(--viz-series-${(i % 5) + 1})`,
                  }))}
                  values={brandsTable.map((c) => SUBS.filter((s) => brandsTable.some((x) => num(x.overview[s.key]))).map((s) => { const v = c.overview[s.key]; return num(v) ? v : null; }))}
                />
                {gap && Math.abs(gap.delta) >= 0.3 && (
                  <Text tone={gap.delta < 0 ? 'error' : 'default'}>
                    {gap.delta < 0 ? `${brand.display_name} trails ${gap.vs} by ${Math.abs(gap.delta).toFixed(1)} on ${gap.sub}.` : `${brand.display_name} leads ${gap.vs} by ${gap.delta.toFixed(1)} on ${gap.sub}.`}
                  </Text>
                )}
              </Stack>
            )}
          </Panel>
        </Grid>
      )}

      {pts.length >= 2 ? (
        <Grid columns={2} stackAt="wide" gap="md">
          <Panel title="Overall rating over time" description="Daily snapshots, out of 5." headingLevel={3}>
            <LineChart
              title="Overall Glassdoor rating over time"
              categories={pts.map((h) => h.date.slice(5))}
              categoryLabels={pts.map((h) => h.date)}
              series={[{ id: 'rating', label: 'Overall rating', color: 1, values: pts.map((h) => h.rating ?? null) }]}
              yDomain={[0, 5]}
              yTicks={[0, 1, 2, 3, 4, 5]}
            />
          </Panel>
          <Panel title="Approval over time" description="Daily snapshots, in percent." headingLevel={3}>
            <LineChart
              title="Glassdoor approval percentages over time"
              categories={pts.map((h) => h.date.slice(5))}
              categoryLabels={pts.map((h) => h.date)}
              series={[
                { id: 'outlook', label: 'Positive outlook', color: 2, values: pts.map((h) => pct(h.business_outlook_rating)) },
                { id: 'ceo', label: 'CEO approval', color: 3, values: pts.map((h) => pct(h.ceo_rating)) },
                { id: 'recommend', label: 'Would recommend', color: 4, values: pts.map((h) => pct(h.recommend_to_friend_rating)) },
              ]}
              yDomain={[0, 100]}
              yTicks={[0, 25, 50, 75, 100]}
              formatValue={(v) => `${v}%`}
            />
          </Panel>
        </Grid>
      ) : ov ? (
        <Text variant="caption">
          {pts.length === 1 ? `Ratings tracked since ${pts[0].date}; the trend appears after a few daily snapshots.` : 'Snapshots start with the next Glassdoor refresh.'} An alert fires when the overall rating drops by 0.2 or more, or the outlook by 10 points or more, within about a month.
        </Text>
      ) : null}

      <Grid columns={2} stackAt="wide" gap="md">
        <Panel
          title="Recent employee reviews"
          description={rs && rs.scored > 0 ? `${rs.pos} positive, ${rs.neu} neutral, ${rs.neg} negative${rs.net != null ? `; net ${rs.net > 0 ? '+' : ''}${rs.net}` : ''}` : undefined}
          headingLevel={3}
        >
          {er.reviews.length === 0 ? <Text>No reviews yet. The daily poll pulls the latest ones.</Text> : (
            <Stack as="ul" gap="md" label="Employee reviews">
              {er.reviews.map((r) => {
                const p = parseReview(r);
                return (
                  <li key={r.uri}>
                    <Stack gap="sm">
                      <Stack direction="row" gap="sm" wrap={false}>
                        {p.rating != null && <Chip size="sm" tone={p.rating >= 4 ? 'success' : p.rating <= 2 ? 'error' : 'muted'}>{p.rating} of 5</Chip>}
                        <TextLink href={r.uri} external>{p.headline}</TextLink>
                      </Stack>
                      <Text variant="caption">{[p.role, r.publication_date?.slice(0, 10)].filter(Boolean).join(' · ')}</Text>
                      {p.pros && <Text variant="description"><strong>Pros:</strong> {p.pros.slice(0, 180)}</Text>}
                      {p.cons && <Text variant="description"><strong>Cons:</strong> {p.cons.slice(0, 180)}</Text>}
                    </Stack>
                  </li>
                );
              })}
            </Stack>
          )}
        </Panel>
        <Panel title="Workforce risk findings" description="Strikes, disputes, layoffs and tribunals." headingLevel={3}>
          {er.workforce_risks.length === 0 ? <Text>No workforce risk findings.</Text> : (
            <Stack as="ul" gap="md" label="Workforce risk findings">
              {er.workforce_risks.map((w) => (
                <li key={w.uri}>
                  <Stack gap="sm">
                    <Stack direction="row" gap="sm" wrap={false}>
                      <Chip size="sm" tone={w.severity === 'high' ? 'error' : w.severity === 'medium' ? 'warning' : 'muted'}>{w.severity}</Chip>
                      <TextLink href={w.uri} external>{w.title}</TextLink>
                    </Stack>
                    <Stack direction="row" gap="sm">
                      <Text variant="caption" as="span">{[w.news_source, w.publication_date?.slice(0, 10)].filter(Boolean).join(' · ')}</Text>
                      <Select
                        label={`Case state for “${w.title}”`}
                        hideLabel
                        options={STATES.map((s) => ({ value: s, label: STATE_LABEL[s] }))}
                        value={w.case_status}
                        onValueChange={(st) =>
                          void setFindingState(w.uri, brand.id, st as 'new').then(
                            () => setEr((prev) => (prev ? { ...prev, workforce_risks: prev.workforce_risks.map((x) => (x.uri === w.uri ? { ...x, case_status: st } : x)) } : prev)),
                            (e: unknown) => notify(`Not saved: ${errorText(e)}`),
                          )
                        }
                      />
                    </Stack>
                  </Stack>
                </li>
              ))}
            </Stack>
          )}
        </Panel>
      </Grid>
      {loading && <ActivityRow primary="Updating workforce data…" dotTone="pending" />}
    </>
  );
}
