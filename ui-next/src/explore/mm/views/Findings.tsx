import { useEffect, useMemo, useState } from 'react';
import { ArticleCard, Banner, Checkbox, Chip, EmptyState, FilterChipRow, Panel, Select, Skeleton, Stack, Text, TextLink } from '@aunoo/ui';
import { getMarketFindings, type MarketFinding, type MarketFindings } from '@monolith/marketMonitorApi';
import { errorText } from '../../../shell';
import type { MmContext } from '../context';
import { DataStateBadge, UnmeasuredNotice } from '../shared/metric';
import { headlineOf, hostOf, MATERIALITY_LABEL, meetsMateriality, saidBy, whenOf } from './findings/helpers';
import { VendorChip } from './findings/VendorChip';

/*
 * Findings: what changed in this market, as a list a reader can act on (old MarketFindingsView.tsx,
 * /api/market-monitor/markets/{id}/findings). A finding is a deduplicated change with its evidence
 * attached. Every row says who is saying it (the vendor about itself, or somebody else) and how much
 * it matters. Neither is coloured good or bad: a launch isn't good news and a hiring spike isn't bad
 * news.
 */

const MATERIALITY_OPTIONS = [
  { value: 'all', label: 'Any materiality' },
  { value: 'high', label: 'Material only' },
  { value: 'medium', label: 'Notable and above' },
];

function FindingCard({ f, ctx }: { f: MarketFinding; ctx: MmContext }) {
  const by = saidBy(f);
  const ev = f.strongest_evidence;
  const host = hostOf(ev?.uri);
  const meta = [by.label, whenOf(f), f.status === 'watch' ? 'Watching' : null, f.has_contradiction ? 'Sources disagree' : null, f.evidence_count > 1 ? `${f.evidence_count} pieces of evidence` : null]
    .filter(Boolean)
    .join(' · ');
  const details = f.why_it_matters || f.summary || ev?.uri || f.limitations.length ? (
    <Stack gap="sm">
      {f.why_it_matters && <Text>{f.why_it_matters}</Text>}
      {f.summary && <Text variant="caption">{f.summary}</Text>}
      {ev?.uri && <TextLink href={ev.uri} external>{host ? `Strongest evidence on ${host}` : 'Strongest evidence'}</TextLink>}
      {f.limitations.length > 0 && (
        <ul className="mm-plainlist">
          {f.limitations.map((l, i) => <li key={i}><Text as="span" variant="caption">{l}</Text></li>)}
        </ul>
      )}
    </Stack>
  ) : undefined;
  return (
    <ArticleCard
      as="li"
      variant="row"
      headingLevel={3}
      title={headlineOf(f)}
      meta={meta}
      flag={
        <Chip size="sm" tone={f.materiality === 'high' ? 'neutral' : 'muted'} variant={f.materiality === 'high' ? 'fill' : 'outline'} label={f.materiality_reason ?? undefined}>
          {MATERIALITY_LABEL[f.materiality] ?? f.materiality}
        </Chip>
      }
      tags={f.vendors.length ? (
        <Stack direction="row" gap="sm">
          {f.vendors.map((v) => <VendorChip key={v.brand_id} id={v.brand_id} name={v.vendor} color={ctx.colours.byId(v.brand_id)} onOpen={ctx.openVendor} />)}
        </Stack>
      ) : undefined}
      details={details}
    />
  );
}

export function Findings(ctx: MmContext) {
  const { marketId, periodDays: days, overview, pulse } = ctx;
  const [data, setData] = useState<MarketFindings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [themes, setThemes] = useState<string[]>([]);
  const [onlyIndependent, setOnlyIndependent] = useState(false);
  const [materiality, setMateriality] = useState('all');

  useEffect(() => {
    let live = true;
    setError(null);
    getMarketFindings(marketId, { days, pageSize: 500 }).then((r) => live && setData(r), (e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, [marketId, days]);

  const all = useMemo(() => data?.data ?? [], [data]);
  const themeNames = useMemo(() => Object.keys(data?.by_theme ?? {}), [data]);
  const shown = useMemo(
    () => all.filter((f) => (!themes.length || themes.includes(f.theme)) && (!onlyIndependent || f.non_vendor_source_count > 0) && meetsMateriality(f, materiality)),
    [all, themes, onlyIndependent, materiality],
  );
  const grouped = useMemo(() => {
    const order = themeNames.length ? themeNames : [...new Set(shown.map((f) => f.theme))];
    return order.map((t) => [t, shown.filter((f) => f.theme === t)] as const).filter(([, rows]) => rows.length > 0);
  }, [shown, themeNames]);

  if (error) return <Banner tone="error" title="Findings didn’t load" description={error} />;
  if (!data) return <Skeleton variant="block" size="card" />;
  const metric = data.meta.metric;
  if (metric && !metric.measured) return <Panel title="Findings"><UnmeasuredNotice meta={metric} /></Panel>;

  const independent = all.filter((f) => f.non_vendor_source_count > 0).length;
  const material = all.filter((f) => f.materiality === 'high').length;
  // What the collected channels recorded in the same period. Summed over measured vendors, so a
  // channel that wasn't measured for a vendor adds nothing rather than a zero.
  const totals = (overview?.most_active ?? []).reduce((a, v) => ({ posts: a.posts + (v.posts || 0), jobs: a.jobs + (v.jobs || 0), earned: a.earned + (v.earned || 0) }), { posts: 0, jobs: 0, earned: 0 });
  const synthesis = data.meta.synthesis;
  const executive = data.executive.filter((f) => f.non_vendor_source_count > 0 || f.materiality === 'high');

  return (
    <>
      <Panel
        title={`${all.length} finding${all.length === 1 ? '' : 's'} in the last ${days} days`}
        description={`${independent} reported by someone other than the vendor · ${material} material`}
        headerAside={<DataStateBadge meta={metric} />}
      >
        <Stack gap="sm">
          {overview && (
            <Text variant="caption">
              {`${totals.posts} posts the vendors published · ${totals.earned} articles about them by somebody else · ${totals.jobs} open roles observed`}
              {pulse ? ` · ${pulse.headcount_movers.length} headcount move${pulse.headcount_movers.length === 1 ? '' : 's'} with two readings` : ''}
              {` · ${overview.quiet_vendors} of ${overview.coverage.vendors} vendors with nothing observed`}
            </Text>
          )}
          {synthesis && synthesis.state !== 'ready' && synthesis.detail && <Text variant="caption">{synthesis.detail}</Text>}
          {all.length > 0 && independent === 0 && (
            <Text variant="caption">
              Every finding in this period comes from a vendor describing itself. That is what the collected evidence contains, not a verdict on the vendors.
              Third-party coverage is matched to vendors on each scan of the collected articles, and findings drawn from it appear once they are written up.
            </Text>
          )}
        </Stack>
      </Panel>

      {executive.length > 0 && (
        <Panel title="Needs attention" description="Material findings, and anything someone other than the vendor reported.">
          <Stack as="ul" gap="sm" label="Findings that need attention">
            {executive.map((f) => <FindingCard key={`x-${f.finding_id}`} f={f} ctx={ctx} />)}
          </Stack>
        </Panel>
      )}

      <Panel title="All findings">
        <Stack gap="md">
          {/* Theme chips carry their counts, so an empty theme shows as empty rather than missing */}
          {themeNames.length > 0 && (
            <FilterChipRow
              label="Themes"
              options={themeNames.map((t) => ({ value: t, label: t, count: data.by_theme[t]?.length ?? 0 }))}
              selected={themes}
              onChange={setThemes}
              total={all.length}
            />
          )}
          <Stack direction="row" gap="md">
            <Checkbox label="Only findings someone other than the vendor reported" checked={onlyIndependent} onCheckedChange={setOnlyIndependent} />
            <Select label="Materiality" hideLabel options={MATERIALITY_OPTIONS} value={materiality} onValueChange={setMateriality} />
          </Stack>
          {shown.length === 0 ? (
            <EmptyState icon="ListBullets" title={all.length === 0 ? 'No findings in this period' : 'Nothing matches these filters'}>
              {all.length === 0 ? 'Collection worked, and nothing in the period met the bar for a finding.' : 'Clear a filter to see more.'}
            </EmptyState>
          ) : (
            grouped.map(([t, rows]) => (
              <Stack key={t} gap="sm">
                <Text variant="label">{`${t} · ${rows.length} · ${rows.filter((f) => f.non_vendor_source_count > 0).length} reported independently`}</Text>
                <Stack as="ul" gap="sm" label={`${t} findings`}>
                  {rows.map((f) => <FindingCard key={f.finding_id} f={f} ctx={ctx} />)}
                </Stack>
              </Stack>
            ))
          )}
        </Stack>
      </Panel>
    </>
  );
}
