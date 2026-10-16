import { useEffect, useMemo, useState } from 'react';
import {
  ActivityRow, Banner, Button, Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, Grid, Icon, LineChart, Menu, Panel, Skeleton, Stack, Stat, Text, TextField, TextLink,
} from '@aunoo/ui';
import { getVendorDetail, setVendorIdentifier, startRun, type VendorDetail } from '@monolith/marketMonitorApi';
import { errorText } from '../../../shell';
import type { MmContext } from '../context';
import { VendorSwatch } from '../shared/colours';
import { Missing } from '../shared/SortTable';
import { VendorHorizonControls } from '../views/horizon/VendorHorizonControls';
import { Benchmark } from './Benchmark';
import { Provenance } from './Provenance';
import './vendor.css';

/*
 * One vendor's page, as the old MarketVendorPage: the resolved profile and where each figure came
 * from, the benchmark against its market, the analyst's Maturity Map controls, then the readings
 * themselves (headcount, Crunchbase funding, identifiers, announcements, site changes, jobs, posts,
 * coverage). The frame keeps it in the URL as ?vendor=.
 */

/** Everything Bright Data can pull for one vendor on demand. A source with no matching identifier closes as a quiet no-op on the server */
const FETCH_NOW_SOURCES = ['linkedin_company_post', 'linkedin_company_profile', 'linkedin_jobs', 'crunchbase_company', 'pitchbook_company', 'zoominfo_company', 'indeed_jobs'];

/** PitchBook and ZoomInfo ids can't be guessed from a company name, so a person pastes them */
const MANUAL_KINDS: { kind: 'pitchbook_url' | 'zoominfo_url'; label: string }[] = [
  { kind: 'pitchbook_url', label: 'PitchBook URL' },
  { kind: 'zoominfo_url', label: 'ZoomInfo URL' },
];

const VERDICT_WORD: Record<string, string> = { signal: 'announcements', commentary: 'opinion', noise: 'promotion' };
const SEVERITY_TONE: Record<string, 'error' | 'warning' | 'info'> = { high: 'error', medium: 'warning', low: 'info' };

function Facts({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <dl className="mm-dl">
      {rows.map(([k, v]) => (
        <Stack key={k} direction="row" justify="between" gap="sm">
          <Text as="span" variant="caption">{k}</Text>
          <Text as="span">{v}</Text>
        </Stack>
      ))}
    </dl>
  );
}

/** Round, spaced ticks for a headcount line */
function niceScale(values: number[]): { domain: [number, number]; ticks: number[] } {
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const raw = (hi - lo || Math.max(1, hi * 0.1)) / 4;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const start = Math.floor(lo / step) * step;
  const end = Math.ceil(hi / step) * step;
  const ticks: number[] = [];
  for (let t = start; t <= end + step / 2; t += step) ticks.push(Math.round(t));
  return { domain: [start, end], ticks };
}

export function VendorPage({ ctx, brandId, onBack }: { ctx: MmContext; brandId: number; onBack: () => void }) {
  const { marketId, notify, askConfirm } = ctx;
  const linkedinEnabled = ctx.health?.providers.brightdata_linkedin_enabled ?? false;
  const [v, setV] = useState<VendorDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fetching, setFetching] = useState(false);
  const [fetchNote, setFetchNote] = useState<string | null>(null);
  const [adding, setAdding] = useState<'pitchbook_url' | 'zoominfo_url' | null>(null);
  const [addValue, setAddValue] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let live = true;
    setV(null);
    setError(null);
    getVendorDetail(marketId, brandId).then((d) => live && setV(d), (e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, [marketId, brandId]);

  const series = useMemo(
    () => (v?.profile_series ?? []).filter((p) => p.employee_count !== null).map((p) => ({ date: p.observed_at.slice(0, 10), staff: Number(p.employee_count) })),
    [v],
  );

  const fetchNow = () =>
    askConfirm({
      title: `Fetch ${v?.display_name ?? 'this vendor'} now?`,
      message: 'This queues a paid Bright Data pull of the LinkedIn profile, posts and jobs, Crunchbase, PitchBook, ZoomInfo and Indeed, ahead of the next scheduled run. Sources with nothing on file for this vendor are skipped.',
      action: 'Fetch now',
      onConfirm: async () => {
        setFetching(true);
        setFetchNote(null);
        try {
          await Promise.all(FETCH_NOW_SOURCES.map((s) => startRun(marketId, s, brandId)));
          setFetchNote('Queued. Bright Data runs in batches, so new posts, profile, job listings and funding data arrive here within a few minutes.');
        } catch (e) {
          setFetchNote(`Couldn’t queue a fetch: ${errorText(e)}`);
        } finally {
          setFetching(false);
        }
      },
    });

  const saveIdentifier = async () => {
    if (!adding || !addValue.trim()) return;
    setSaving(true);
    try {
      await setVendorIdentifier(marketId, brandId, adding, addValue.trim());
      setAdding(null);
      setAddValue('');
      setV(await getVendorDetail(marketId, brandId));
      notify('Saved. The next collection run uses it.');
    } catch (e) {
      notify(`Couldn’t save that URL: ${errorText(e)}`);
    } finally {
      setSaving(false);
    }
  };

  const back = <Button variant="ghost" iconStart={<Icon name="CaretLeft" size="sm" />} onClick={onBack}>Back to the market</Button>;
  if (error) return <Stack gap="md">{back}<Banner tone="error" title="This vendor didn’t load" description={error} /></Stack>;
  if (!v) return <Stack gap="md">{back}<Skeleton variant="block" size="card" /></Stack>;

  const base = v.baseline ?? {};
  const fund = base.funding_baseline ?? {};
  const baselineStaff = base.metrics?.employee_count ?? null;
  const cb = (v.funding ?? {}) as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  const live = v.identifiers.filter((i) => i.live);
  const superseded = v.identifiers.filter((i) => !i.live);
  const latest = v.profile_series[v.profile_series.length - 1];
  const color = v.color ?? ctx.colours.byId(brandId);
  const acquiredBy = typeof cb.acquired_by === 'string' ? cb.acquired_by : cb.acquired_by?.acquirer;

  let headcount: React.ReactNode;
  if (series.length === 0) headcount = <Text>No LinkedIn reading yet.</Text>;
  else if (series.length === 1) {
    // One point isn't a trend: say when the next lands rather than drawing a flat line
    const s = series[0];
    headcount = (
      <Stack gap="sm">
        <Stat label={`LinkedIn headcount on ${s.date}`} value={s.staff.toLocaleString()} meta={baselineStaff != null ? `Imported baseline ${baselineStaff}${Number(baselineStaff) !== s.staff ? `, change ${s.staff > Number(baselineStaff) ? '+' : ''}${s.staff - Number(baselineStaff)}` : ''}` : undefined} />
        <Text variant="caption">One reading so far. Collected weekly.</Text>
      </Stack>
    );
  } else {
    const vals = series.map((s) => s.staff).concat(baselineStaff != null ? [Number(baselineStaff)] : []);
    const { domain, ticks } = niceScale(vals);
    headcount = (
      <LineChart
        title={`${v.display_name} LinkedIn headcount`}
        categories={series.map((s) => s.date.slice(5))}
        categoryLabels={series.map((s) => s.date)}
        yDomain={domain}
        yTicks={ticks}
        series={[
          { id: 'staff', label: 'LinkedIn headcount', color: 1, markers: true, values: series.map((s) => s.staff) },
          ...(baselineStaff != null ? [{ id: 'baseline', label: `Imported baseline (${baselineStaff})`, color: 'neutral' as const, dashed: true, values: series.map(() => Number(baselineStaff)) }] : []),
        ]}
      />
    );
  }

  return (
    <Stack gap="lg">
      {back}
      <Panel
        title={<><VendorSwatch color={color} />{v.display_name}</>}
        description={[base.taxonomy?.sub_category, base.hq_country, base.founded_year ? `founded ${base.founded_year}` : null].filter(Boolean).join(' · ') || undefined}
        headerAside={
          <Stack direction="row" gap="sm">
            <Menu
              label="Download this vendor"
              align="end"
              trigger={<Button variant="secondary" iconStart={<Icon name="DownloadSimple" size="sm" />}>Download</Button>}
              items={[
                { id: 'md', label: 'Markdown', icon: 'FileText' },
                { id: 'csv', label: 'CSV', icon: 'Table' },
                { id: 'pdf', label: 'PDF', icon: 'FileText' },
                { id: 'html', label: 'HTML', icon: 'FileText' },
              ]}
              onSelect={(f) => { window.location.href = `/api/market-monitor/markets/${marketId}/vendors/${brandId}/export?fmt=${f}`; }}
            />
            <Button
              variant="secondary"
              iconStart={<Icon name="ArrowsClockwise" size="sm" />}
              busy={fetching}
              disabled={fetching || !linkedinEnabled}
              onClick={fetchNow}
            >
              Fetch now
            </Button>
          </Stack>
        }
      >
        <Stack gap="sm">
          <Stack direction="row" gap="sm">
            <Chip size="sm" tone="muted">{v.role}</Chip>
            <Chip size="sm" tone={v.collection_enabled ? 'success' : 'muted'}>{v.collection_enabled ? 'watched' : 'not watched'}</Chip>
            {v.is_public && <Chip size="sm" tone="info">published</Chip>}
          </Stack>
          {!linkedinEnabled && <Text variant="caption">Fetch now is off because Bright Data collection isn’t set up on this site.</Text>}
          {fetchNote && <Banner tone="info" title="Fetch" description={fetchNote} />}
        </Stack>
      </Panel>

      {v.review_tasks.map((t) => <Banner key={t.id} tone={SEVERITY_TONE[t.severity] ?? 'info'} title={`Needs review: ${t.kind.replace(/_/g, ' ')}`} description={t.message} />)}

      <Provenance marketId={marketId} brandId={brandId} baseline={v.baseline} />
      <Benchmark marketId={marketId} brandId={brandId} color={color} />
      <VendorHorizonControls marketId={marketId} brandId={brandId} notify={notify} />

      <Grid columns={2}>
        <Panel title="Headcount" description="LinkedIn employee count. The dashed line is the imported baseline, a separate measurement taken at a different time.">
          <Stack gap="sm">
            {headcount}
            {latest?.followers != null && <Text variant="caption">Followers: {Number(latest.followers).toLocaleString()}</Text>}
          </Stack>
        </Panel>

        <Panel title="Funding" description="From Crunchbase, whose public record doesn’t carry round amounts.">
          <Stack gap="md">
            <Facts
              rows={[
                ['Registry status', `${fund.status ?? '—'}${fund.total_musd != null ? ` · $${fund.total_musd}M` : ''}`],
                ['Rounds', cb.num_funding_rounds ?? '—'],
                ['Last round', cb.last_funding_type?.replace(/_/g, ' ') ?? '—'],
                ['Status', [cb.operating_status, cb.ipo_status].filter(Boolean).join(' · ') || '—'],
                // growth_trend and heat_trend are left out: Crunchbase doesn't say what they count
                ...(cb.growth_score != null || cb.cb_rank != null
                  ? [['Crunchbase', [cb.growth_score != null && `growth ${cb.growth_score}`, cb.heat_score != null && `heat ${cb.heat_score}`, cb.cb_rank != null && `rank ${Number(cb.cb_rank).toLocaleString()}`].filter(Boolean).join(' · ')] as [string, string]]
                  : []),
                ...(Array.isArray(cb.founders) && cb.founders.length ? [['Founders', cb.founders.join(', ')] as [string, string]] : []),
                ...(acquiredBy ? [['Acquired by', acquiredBy] as [string, string]] : []),
              ]}
            />
            {(cb.lead_investors?.length ?? 0) > 0 && (
              <Stack gap="sm">
                <Text variant="label">Lead investors</Text>
                <Stack direction="row" gap="sm">{cb.lead_investors.map((i: string) => <Chip key={i} size="sm" tone="neutral">{i}</Chip>)}</Stack>
              </Stack>
            )}
            {(cb.investors?.length ?? 0) > 0 && (
              <Stack gap="sm">
                <Text variant="label">{`All investors (${cb.investors.length})`}</Text>
                <Stack direction="row" gap="sm">{cb.investors.map((i: string) => <Chip key={i} size="sm" tone="muted" variant="outline">{i}</Chip>)}</Stack>
              </Stack>
            )}
            {Array.isArray(cb.recent_news) && cb.recent_news.length > 0 && (
              <Stack gap="sm">
                <Text variant="label">Recent news, according to Crunchbase</Text>
                {cb.recent_news.slice(0, 6).map((n: { title?: string; publisher?: string; date?: string }, i: number) => (
                  <Text key={i} variant="caption">{[n.title, n.publisher, n.date ? String(n.date).slice(0, 10) : null].filter(Boolean).join(' · ')}</Text>
                ))}
              </Stack>
            )}
          </Stack>
        </Panel>
      </Grid>

      <Panel title="Identifiers" description="Used to match this vendor across sources.">
        <Stack gap="md">
          {live.length === 0 ? <Text>None on file.</Text> : (
            <Stack as="ul" gap="sm" label="Identifiers on file">
              {live.map((i) => (
                <li key={i.kind + i.normalized_value}>
                  <Stack direction="row" gap="sm">
                    <Text as="span" variant="caption">{i.kind.replace(/_/g, ' ')}</Text>
                    {i.display_value && /^https?:/.test(i.display_value) ? <TextLink href={i.display_value} external>{i.display_value}</TextLink> : <Text as="span">{i.display_value ?? i.normalized_value}</Text>}
                    <Chip size="sm" tone={i.verified ? 'success' : 'muted'}>{i.verified ? 'verified' : 'unverified'}</Chip>
                  </Stack>
                </li>
              ))}
            </Stack>
          )}
          {/* Corrected identifiers are kept: they're part of how the registry got here */}
          {superseded.length > 0 && (
            <Collapsible>
              <CollapsibleTrigger variant="ghost" size="sm">{`${superseded.length} corrected`}</CollapsibleTrigger>
              <CollapsibleContent>
                <Stack gap="sm">
                  {superseded.map((i) => (
                    <Text key={i.normalized_value} variant="caption">{`${i.display_value ?? i.normalized_value} (replaced: ${String((i.provenance as { superseded_reason?: string })?.superseded_reason ?? 'corrected')})`}</Text>
                  ))}
                </Stack>
              </CollapsibleContent>
            </Collapsible>
          )}
          <Stack direction="row" gap="sm">
            {MANUAL_KINDS.filter((k) => !live.some((i) => i.kind === k.kind)).map((k) =>
              adding === k.kind ? (
                <Stack key={k.kind} direction="row" gap="sm">
                  <TextField label={k.label} type="url" placeholder={`Paste the ${k.label}`} value={addValue} onChange={setAddValue} onSubmit={() => void saveIdentifier()} />
                  <Button busy={saving} disabled={saving || !addValue.trim()} onClick={() => void saveIdentifier()}>Save</Button>
                  <Button variant="ghost" onClick={() => { setAdding(null); setAddValue(''); }}>Cancel</Button>
                </Stack>
              ) : (
                <Button key={k.kind} variant="secondary" size="sm" iconStart={<Icon name="Plus" size="sm" />} onClick={() => { setAdding(k.kind); setAddValue(''); }}>Add {k.label}</Button>
              ),
            )}
          </Stack>
        </Stack>
      </Panel>

      <Panel title="Announcements" description="Posts naming something that happened: a launch, a raise, a customer, a hire. Everything else this vendor posted is further down.">
        {v.announcements.length === 0 ? (
          <Text>{Object.keys(v.post_verdicts ?? {}).length === 0 ? 'No posts have been read yet.' : 'Nothing this vendor posted stated a fact.'}</Text>
        ) : (
          <Stack gap="md">
            <Stack direction="row" gap="sm">
              {(['signal', 'commentary', 'noise'] as const).map((k) => (v.post_verdicts?.[k] ? <Chip key={k} size="sm" tone="muted">{`${VERDICT_WORD[k]}: ${v.post_verdicts[k]}`}</Chip> : null))}
            </Stack>
            <Stack as="ul" gap="sm" label="Announcements">
              {v.announcements.map((a) => (
                <ActivityRow
                  key={a.uri}
                  as="li"
                  primary={<TextLink href={a.url ?? a.uri} external>{a.title}</TextLink>}
                  secondary={[a.review_kind, a.review_reason].filter(Boolean).join(': ') || undefined}
                  timestamp={a.publication_date?.slice(0, 10) ?? undefined}
                />
              ))}
            </Stack>
          </Stack>
        )}
      </Panel>

      <Grid columns={2}>
        <Panel title="Site changes" description="Watched pages and their most recent change.">
          {v.pages.length === 0 ? <Text>No watched pages.</Text> : (
            <Stack as="ul" gap="md" label="Watched pages">
              {v.pages.map((p) => (
                <li key={p.url}>
                  <Stack gap="sm">
                    <Stack direction="row" justify="between" gap="sm">
                      <TextLink href={p.url} external>{p.title || p.kind || 'page'}</TextLink>
                      <Text as="span" variant="caption">{p.observed_at.slice(0, 10)}</Text>
                    </Stack>
                    {p.diff?.material && (
                      <Stack gap="sm">
                        {/* The counts say how much moved; the lines are only a sample of it */}
                        <Text variant="caption">{`${p.diff.added_count ?? p.diff.added.length} lines added, ${p.diff.removed_count ?? p.diff.removed.length} removed. A sample:`}</Text>
                        <pre className="mm-diff">{[...p.diff.added.slice(0, 3).map((l) => `+ ${l}`), ...p.diff.removed.slice(0, 2).map((l) => `− ${l}`)].join('\n')}</pre>
                      </Stack>
                    )}
                  </Stack>
                </li>
              ))}
            </Stack>
          )}
        </Panel>

        <Panel title="Job postings" description={`Open roles from LinkedIn, collected twice a week.${v.jobs.length > 10 ? ` Showing 10 of ${v.jobs.length}.` : ''}`}>
          {v.jobs.length === 0 ? <Text>No postings collected.</Text> : (
            <Stack as="ul" gap="sm" label="Job postings">
              {v.jobs.slice(0, 10).map((j, i) => (
                <ActivityRow key={i} as="li" primary={j.url ? <TextLink href={j.url} external>{j.title}</TextLink> : j.title} secondary={[j.seniority, j.location].filter(Boolean).join(' · ') || undefined} />
              ))}
            </Stack>
          )}
        </Panel>
      </Grid>

      <Grid columns={2}>
        <Panel title="LinkedIn posts" description="The 10 most recent.">
          {v.posts.length === 0 ? <Text>No posts collected.</Text> : (
            <Stack as="ul" gap="sm" label="LinkedIn posts">
              {v.posts.map((p) => <ActivityRow key={p.uri} as="li" primary={<TextLink href={p.url ?? p.uri} external>{p.title}</TextLink>} timestamp={p.publication_date?.slice(0, 10) ?? undefined} />)}
            </Stack>
          )}
        </Panel>

        <Panel title="Coverage" description="Articles by other people attributed to this vendor.">
          <Stack gap="md">
            {v.coverage_by_category.length === 0 ? <Text>No articles attributed.</Text> : (
              <Stack direction="row" gap="sm">{v.coverage_by_category.map((c) => <Chip key={c.category} size="sm" tone="muted">{`${c.category}: ${c.n}`}</Chip>)}</Stack>
            )}
            {v.recent_coverage.length > 0 && (
              <Stack as="ul" gap="sm" label="Recent coverage">
                {v.recent_coverage.slice(0, 5).map((a) => (
                  <ActivityRow key={a.uri} as="li" primary={<TextLink href={a.url ?? a.uri} external>{a.title}</TextLink>} secondary={a.news_source ?? undefined} timestamp={a.publication_date?.slice(0, 10) ?? undefined} />
                ))}
              </Stack>
            )}
            {v.recent_coverage.length === 0 && v.coverage_by_category.length > 0 && <Missing>No recent articles to list.</Missing>}
          </Stack>
        </Panel>
      </Grid>
    </Stack>
  );
}
