import '../shared/mm.css';
import { useEffect, useMemo, useState } from 'react';
import { Banner, Button, EmptyState, Grid, Icon, Panel, SegmentedControl, Skeleton, Stack, Table, Text } from '@aunoo/ui';
import { computeMarketHorizon, getMarketHorizon, type HorizonCuts, type HorizonVendor, type MarketHorizon } from '@monolith/marketMonitorApi';
import { errorText } from '../../../shell';
import type { MmContext } from '../context';
import { VendorLink } from '../shared/SortTable';
import { HorizonChart, MARKER_KEYS, STAGE_KEYS, type MarkerKey } from './horizon/HorizonChart';
import { StatusPanel } from './horizon/StatusPanel';

/*
 * Market Maturity Map, as the old MarketHorizonView.tsx: every rated vendor on a map of scale
 * against momentum. It isn't a quadrant of judgement. Both axes are weighted percentile ranks of
 * readings we collect, the weights are printed under the chart, and a vendor is on the map only when
 * every required input was measured. The rest are listed with the reading each one lacks, which is
 * also the collection to-do. Each computation is stored, so the page can say who moved.
 *
 * Loading only reads the stored map. Computing a new one is a button (it's local arithmetic over
 * stored readings, no AI and no paid calls, but it stores a new map).
 */

const SHAPE_KEY = 'mm-horizon-view';
const MARKER_LABEL: Record<MarkerKey, string> = { innovating: 'Innovating', hiring: 'Hiring', funded: 'Funded' };

function loadShape(): 'arc' | 'grid' {
  try {
    return localStorage.getItem(SHAPE_KEY) === 'grid' ? 'grid' : 'arc';
  } catch {
    return 'arc';
  }
}

const signed = (n: number) => `${n > 0 ? '+' : ''}${n}`;

/** The short notes beside a vendor in its stage list */
function vendorNotes(r: HorizonVendor, hasPrevious: boolean): string[] {
  const out: string[] = [`${Math.round(r.scale)} scale / ${Math.round(r.momentum)} momentum`];
  if (r.moved && r.previous) out.push(`moved from ${r.previous.tier} (was ${Math.round(r.previous.scale)} / ${Math.round(r.previous.momentum)})`);
  if (r.big_move && r.shift) {
    const parts = [Math.abs(r.shift.scale) >= 1 ? `${signed(r.shift.scale)} scale` : '', Math.abs(r.shift.momentum) >= 1 ? `${signed(r.shift.momentum)} momentum` : ''].filter(Boolean);
    if (parts.length) out.push(`large move: ${parts.join(', ')}`);
  }
  if (!r.previous && hasPrevious) out.push('new on this map');
  if (r.innovating) out.push('innovating');
  if (r.hiring && r.hiring_detail) out.push(`hiring (${r.hiring_detail.open_roles} open roles, ${Math.round(r.hiring_detail.per_100)} per 100 staff)`);
  if (r.funded) out.push(`funded (${r.funded.round ?? 'round not stated'}, ${r.funded.date})`);
  if (r.multipliers || r.analyst_note) {
    const w = r.multipliers ? `weights ${Object.entries(r.multipliers).map(([k, m]) => `${k} ×${m}`).join(', ')}` : '';
    out.push(`adjusted by an analyst${[w, r.analyst_note ?? ''].filter(Boolean).length ? `: ${[w, r.analyst_note ?? ''].filter(Boolean).join('; ')}` : ''}`);
  }
  return out;
}

export function Horizon(ctx: MmContext) {
  const { marketId } = ctx;
  // undefined while loading, null when no map has been computed yet (the server answers 404)
  const [horizon, setHorizon] = useState<MarketHorizon | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [computing, setComputing] = useState(false);
  const [shape, setShape] = useState<'arc' | 'grid'>(loadShape);
  const [highlight, setHighlight] = useState<MarkerKey | null>(null);

  useEffect(() => {
    let live = true;
    setHorizon(undefined);
    setError(null);
    getMarketHorizon(marketId).then((h) => live && setHorizon(h), (e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, [marketId]);

  const pickShape = (v: string) => {
    const s = v === 'grid' ? 'grid' : 'arc';
    setShape(s);
    try {
      localStorage.setItem(SHAPE_KEY, s);
    } catch {
      // remembered for this visit only
    }
  };

  const compute = async () => {
    setComputing(true);
    setError(null);
    try {
      setHorizon(await computeMarketHorizon(marketId));
      ctx.notify('Market Maturity Map recomputed');
    } catch (e) {
      setError(errorText(e));
    } finally {
      setComputing(false);
    }
  };

  // The not-rated list grouped by what's missing, so the to-do reads "47 lack a disclosed funding
  // total" rather than 47 lines
  const gaps = useMemo(() => {
    const by: Record<string, { label: string; vendors: string[] }> = {};
    for (const nr of horizon?.not_rated ?? []) for (const g of nr.missing) (by[g.key] ??= { label: g.label, vendors: [] }).vendors.push(nr.vendor);
    return Object.values(by).sort((a, b) => b.vendors.length - a.vendors.length);
  }, [horizon]);

  if (horizon === undefined && !error) return <Skeleton variant="block" size="card" />;

  const cuts: HorizonCuts = horizon?.config.tiers ?? { stage_cuts: [25, 50, 75], band_cuts: [33, 67] };
  const stageCuts = [...(cuts.stage_cuts ?? [25, 50, 75])].sort((a, b) => a - b);
  const bandCuts = [...(cuts.band_cuts ?? [33, 67])].sort((a, b) => a - b);
  const stageNames = Object.fromEntries(Object.entries(horizon?.tiers ?? {}).map(([k, v]) => [k, v.label]));
  const bandNames = Object.fromEntries(Object.entries(horizon?.bands ?? {}).map(([k, v]) => [k, v.label]));
  const hasPrevious = !!horizon?.previous_at;
  const vlink = (id: number, name: string) => <VendorLink id={id} name={name} color={ctx.colours.byId(id)} onOpen={ctx.openVendor} />;

  return (
    <>
      <Panel
        title="Market Maturity Map"
        description="A map of scale against momentum, built from readings we collect. It doesn't rate product quality, customer satisfaction or strategy. A vendor is on the map only when every required input was measured."
        headerAside={
          <Button variant="secondary" iconStart={<Icon name="ArrowClockwise" size="sm" />} busy={computing} disabled={computing} onClick={() => void compute()}>
            {horizon ? 'Recompute from today’s readings' : 'Compute the first map'}
          </Button>
        }
      >
        <Stack gap="md">
          {error && <Banner tone="error" title="The map didn’t load" description={error} />}
          {horizon && (
            <Text variant="caption">
              Computed {horizon.computed_at.slice(0, 10)} over the last {horizon.days} days · {horizon.counts.rated} of {horizon.counts.eligible} vendors rated
              {horizon.previous_at ? ` · previous map ${horizon.previous_at.slice(0, 10)}` : ''}
            </Text>
          )}
          {horizon === null && (
            <EmptyState icon="ChartScatter" title="No map yet for this market">
              Computing one ranks every vendor with enough readings. It uses stored readings only; nothing is collected or sent to an AI model.
            </EmptyState>
          )}
          {horizon && horizon.rated.length > 0 && (
            <>
              <Stack direction="row" gap="md">
                <SegmentedControl label="Map shape" options={[{ value: 'arc', label: 'Arc' }, { value: 'grid', label: 'Grid' }]} value={shape} onValueChange={pickShape} />
                <SegmentedControl
                  className="mm-segmented-scroll"
                  label="Highlight"
                  options={[
                    { value: '', label: 'No highlight' },
                    ...MARKER_KEYS.map((k) => ({ value: k, label: `${MARKER_LABEL[k]} (${horizon.rated.filter((r) => !!r[k]).length})` })),
                  ]}
                  value={highlight ?? ''}
                  onValueChange={(v) => setHighlight((v || null) as MarkerKey | null)}
                />
              </Stack>
              <HorizonChart
                shape={shape}
                rated={horizon.rated}
                cuts={cuts}
                stageNames={stageNames}
                bandNames={bandNames}
                largeShift={horizon.large_shift ?? 10}
                highlight={highlight}
                onVendor={ctx.openVendor}
              />
              <Text variant="caption">Point at a dot to see the readings behind it; click it to open the vendor’s page.</Text>
            </>
          )}
          {horizon && horizon.rated.length === 0 && <Text>No vendor has every required reading yet, so nobody is on the map. The list below says what’s missing.</Text>}
        </Stack>
      </Panel>

      {horizon && (
        <>
          <Grid columns={2}>
            {[...STAGE_KEYS].reverse().map((tier) => {
              const info = horizon.tiers[tier];
              const rows = horizon.rated.filter((r) => r.tier === tier);
              return (
                <Panel key={tier} title={`${info?.label ?? tier} (${rows.length})`} description={info?.means} headingLevel={3}>
                  {rows.length === 0 ? <Text variant="caption">None.</Text> : (
                    <ul className="hz-list">
                      {rows.map((r) => (
                        <li key={r.brand_id}>
                          <span className={`hz-swatch hz-tier-${tier}`} aria-hidden />
                          {vlink(r.brand_id, r.vendor)}
                          <Text as="span" variant="caption">{vendorNotes(r, hasPrevious).join(' · ')}</Text>
                        </li>
                      ))}
                    </ul>
                  )}
                </Panel>
              );
            })}
          </Grid>

          {horizon.innovating.length > 0 && (
            <Panel
              title={`Innovating (${horizon.innovating.length})`}
              description="A marker across every stage: the top third by launches, corroborated launches, research posts and engineering hiring."
              headingLevel={3}
            >
              <Text>{horizon.innovating.join(', ')}</Text>
            </Panel>
          )}

          {(horizon.moves?.length ?? 0) > 0 && (
            <Panel
              title={`Moved (${horizon.moves!.length})`}
              description={`${horizon.large_shift ?? 10} or more points on an axis since the map of ${horizon.previous_at?.slice(0, 10) ?? 'last time'}.`}
              headingLevel={3}
            >
              <ul className="hz-list">
                {horizon.moves!.map((m) => (
                  <li key={m.brand_id}>
                    {vlink(m.brand_id, m.vendor)}
                    <Text as="span" variant="caption">
                      {([['scale', m.scale], ['momentum', m.momentum]] as [string, number][]).filter(([, d]) => Math.abs(d) >= 1).map(([a, d]) => `${signed(d)} ${a}`).join(', ')}
                      {m.previous_tier !== m.tier ? `; ${horizon.tiers[m.previous_tier]?.label ?? m.previous_tier} → ${horizon.tiers[m.tier]?.label ?? m.tier}` : ''}
                    </Text>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          {(horizon.markers?.hiring.length ?? 0) > 0 && (
            <Panel
              title={`Hiring (${horizon.markers!.hiring.length})`}
              description={`A marker across every stage: the top third of rated vendors by open roles per 100 staff, with at least ${horizon.markers!.min_open_roles} roles open${horizon.markers!.hiring_bar != null ? ` (the bar is ${Math.round(horizon.markers!.hiring_bar)} per 100)` : ''}.`}
              headingLevel={3}
            >
              <ul className="hz-list">
                {horizon.markers!.hiring.map((h) => (
                  <li key={h.brand_id}>
                    {vlink(h.brand_id, h.vendor)}
                    <Text as="span" variant="caption">{h.open_roles} open roles, {Math.round(h.per_100)} per 100 staff{h.rated ? '' : ' · not on the map'}</Text>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          {(horizon.markers?.funded.length ?? 0) > 0 && (
            <Panel
              title={`Funded (${horizon.markers!.funded.length})`}
              description={`A round dated in the last ${horizon.markers!.funded_days} days, from the vendor’s own post, a matched news event or the Crunchbase news list.`}
              headingLevel={3}
            >
              <ul className="hz-list">
                {horizon.markers!.funded.map((f) => (
                  <li key={f.brand_id}>
                    {vlink(f.brand_id, f.vendor)}
                    <Text as="span" variant="caption">{f.round ?? 'round not stated'}, {f.date} · {f.source}{f.rated ? '' : ' · not on the map'} · {f.title}</Text>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          <StatusPanel ctx={ctx} horizon={horizon} onRecompute={compute} />

          {horizon.acquisition_hints.length > 0 && (
            <Banner
              tone="warning"
              title="Possibly acquired, not yet marked"
              description={
                <>
                  Confirm on the vendor page:{' '}
                  {horizon.acquisition_hints.map((h, i) => (
                    <span key={h.brand_id}>{i > 0 ? '; ' : ''}{vlink(h.brand_id, h.vendor)} ({h.why})</span>
                  ))}
                </>
              }
            />
          )}

          {horizon.not_rated.length > 0 && (
            <Panel title={`Not rated (${horizon.not_rated.length})`} description="Each of these lacks at least one required reading. This is the collection to-do." headingLevel={3}>
              <ul className="hz-list">
                {gaps.map((g) => (
                  <li key={g.label}>
                    <Text as="span" variant="label">{g.vendors.length} lack {g.label.toLowerCase()}:</Text>
                    <Text as="span" variant="caption">{g.vendors.join(', ')}</Text>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          <Panel
            title="How the map is built"
            description={`Each input is a percentile rank among the rated vendors, and an axis is the weighted mean of its inputs. On the arc, the angle is the stage, by scale, left to right: ${stageNames.emerging ?? 'Emerging'} under ${stageCuts[0]}, ${stageNames.established ?? 'Building'} from ${stageCuts[0]}, ${stageNames.innovators ?? 'Scaling'} from ${stageCuts[1]}, ${stageNames.executors ?? 'Executing'} from ${stageCuts[2]}. The distance from the base is momentum: holding under ${bandCuts[0]}, growing from ${bandCuts[0]}, accelerating from ${bandCuts[1]}. A vendor moves right as it grows and outward as it speeds up. The cuts are set in app/config/market_horizon.json.`}
            headingLevel={3}
          >
            <Table
              caption="Inputs and weights"
              hideCaption
              rows={Object.entries(horizon.config.inputs).map(([k, i]) => ({ k, ...i }))}
              rowKey={(r) => r.k}
              columns={[
                { key: 'label', header: 'Input', rowHeader: true, wrap: true, render: (r) => `${r.label}${r.optional ? ' (optional)' : ''}${r.note ? `: ${r.note}` : ''}` },
                { key: 'axis', header: 'Axis' },
                { key: 'weight', header: 'Weight', align: 'end', render: (r) => r.weight.toFixed(2) },
              ]}
            />
          </Panel>
        </>
      )}
    </>
  );
}
