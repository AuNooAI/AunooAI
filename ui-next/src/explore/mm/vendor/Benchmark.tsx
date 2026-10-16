import { useEffect, useState } from 'react';
import { Banner, Collapsible, CollapsibleContent, CollapsibleTrigger, Panel, Skeleton, Stack, Text } from '@aunoo/ui';
import { getVendorBenchmarks, type VendorBenchmark, type VendorBenchmarks } from '@monolith/marketMonitorApi';
import { errorText } from '../../../shell';
import './vendor.css';

/*
 * One vendor against the market it was measured in, as the old MarketVendorBenchmark. Each row
 * knows when not to draw a number: a vendor with no valid value says why instead of a bar at zero; a
 * market with too few measured peers shows nothing to compare against; a percentage against a median
 * of zero isn't shown. No red or green: more posts, funding or open roles are activity and scale,
 * and whether that's good depends on things this page can't see.
 */

function fmt(v: number | null | undefined, unit: string) {
  if (v === null || v === undefined) return '—';
  if (unit === 'percent') return `${v > 0 ? '+' : ''}${v}%`;
  if (unit === 'musd') return v >= 1000 ? `$${(v / 1000).toFixed(2)}B` : `$${Math.round(v)}M`;
  return Number.isInteger(v) ? String(v) : String(Math.round(v * 10) / 10);
}

/** Says which clock the metric runs on: "32 open roles" and "32 roles posted this month" are different claims */
function clockOf(b: VendorBenchmark, days: number) {
  return b.metric.window === 'period'
    ? `Over the last ${days} days`
    : `As of ${b.as_of ? new Date(b.as_of).toLocaleDateString('en-GB') : 'the latest run'}${b.metric.as_of_note ? `: ${b.metric.as_of_note}` : ''}`;
}

/** The comparative follows the unit, so a level isn't described as a pace */
function aheadOf(unit: string) {
  if (unit === 'people') return 'larger than';
  if (unit === 'musd') return 'better funded than';
  if (unit === 'index') return 'busier than';
  if (unit === 'percent') return 'grew faster than';
  return 'ahead of';
}

const flatZero = (b: VendorBenchmark) => !b.suppressed && b.vendor_value === 0 && (b.market_median ?? 0) === 0 && (b.top_median ?? 0) === 0;

function Plot({ b, color }: { b: VendorBenchmark; color?: string | null }) {
  const pts = [b.vendor_value, b.market_median, b.market_average, b.top_median, b.top_q3].filter((n): n is number => n !== null && n !== undefined);
  if (!pts.length) return null;
  const lo = Math.min(0, ...pts);
  const span = Math.max(...pts) - lo || 1;
  const at = (n: number) => 2 + ((n - lo) / span) * 96;
  return (
    <svg className="mm-bench" viewBox="0 0 100 28" preserveAspectRatio="none" role="img" aria-label={`${b.metric.label}: this vendor ${fmt(b.vendor_value, b.metric.unit)}, market median ${fmt(b.market_median, b.metric.unit)}`}>
      <rect className="mm-bench__track" x="0" y="4" width="100" height="20" rx="2" />
      {b.top_q1 !== null && b.top_q3 !== null && <rect className="mm-bench__band" x={at(b.top_q1)} y="4" width={Math.max(0.5, at(b.top_q3) - at(b.top_q1))} height="20" />}
      {b.market_median !== null && <line className="mm-bench__median" x1={at(b.market_median)} x2={at(b.market_median)} y1="4" y2="24" vectorEffect="non-scaling-stroke" />}
      {b.market_average !== null && <line className="mm-bench__average" x1={at(b.market_average)} x2={at(b.market_average)} y1="7" y2="21" vectorEffect="non-scaling-stroke" />}
      {b.vendor_value !== null && <rect className="mm-bench__vendor" x={at(b.vendor_value) - 0.75} y="1" width="1.5" height="26" rx="0.5" style={color ? { fill: color } : undefined} />}
    </svg>
  );
}

function Row({ b, days, color }: { b: VendorBenchmark; days: number; color?: string | null }) {
  const unit = b.metric.unit;
  const head = (value: string, sub?: string) => (
    <Stack direction="row" justify="between" gap="sm">
      <Stack gap="sm">
        <Text as="span" variant="label">{b.metric.label}</Text>
        <Text as="span" variant="caption">{clockOf(b, days)}</Text>
      </Stack>
      <Stack gap="sm">
        <Text as="span" variant="label">{value}</Text>
        {sub && <Text as="span" variant="caption">{sub}</Text>}
      </Stack>
    </Stack>
  );
  if (flatZero(b)) {
    return (
      <Stack gap="sm">
        {head('0')}
        <Text variant="caption">
          None for this vendor, and none at the market median or the {b.top_label?.toLowerCase()} median either: {b.measured_count} of {b.eligible_count} vendors measured,
          most of them at zero. There is nothing to rank here yet.
        </Text>
      </Stack>
    );
  }
  const sub = b.vendor_percentile === null ? undefined
    // A zero isn't ahead of anyone; it shares the floor
    : b.vendor_value === 0 && (b.tied_count ?? 0) > 1
      ? `level with ${(b.tied_count ?? 1) - 1} other vendors at none, of the ${b.measured_count} measured`
      : `${aheadOf(unit)} ${b.vendor_percentile}% of the ${b.measured_count} vendors measured`;
  const pct = (v: number | null) => (v !== null ? ` (${v > 0 ? '+' : ''}${v}%)` : '');
  return (
    <Stack gap="sm">
      {head(b.vendor_value === null ? 'not measured' : fmt(b.vendor_value, unit), b.vendor_value === null ? b.vendor_unmeasured_because ?? undefined : sub)}
      {b.suppressed ? <Text variant="caption">{b.notes[0]}</Text> : (
        <>
          <Plot b={b} color={color} />
          <Text variant="caption">
            Market median {fmt(b.market_median, unit)} (solid line) · average {fmt(b.market_average, unit)} (dashed) · {b.top_label} median {fmt(b.top_median, unit)}, average{' '}
            {fmt(b.top_average, unit)}; the shaded band is the middle half of the {b.top_label?.toLowerCase()}.
          </Text>
          {b.vendor_value !== null && (
            <Text variant="caption">
              {fmt(b.delta_from_market_median, unit)} against the market median{pct(b.percentage_delta_from_market_median)}. {fmt(b.delta_from_top_median, unit)} against the{' '}
              {b.top_label?.toLowerCase()} median{pct(b.percentage_delta_from_top_median)}.
            </Text>
          )}
          <Text variant="hint">
            {b.measured_count} of {b.eligible_count} vendors measured{b.collection?.label ? ` · ${b.collection.label}` : ''}{b.as_of ? ` · as of ${new Date(b.as_of).toLocaleDateString('en-GB')}` : ''}
          </Text>
        </>
      )}
      {b.notes.filter((n) => !b.suppressed || n !== b.notes[0]).map((n, i) => <Banner key={i} tone="warning" title="Read with care" description={n} />)}
      {b.cohort && b.cohort.length > 0 && (
        <Collapsible>
          <CollapsibleTrigger variant="ghost" size="sm">{b.top_label ?? 'Top vendors'}</CollapsibleTrigger>
          <CollapsibleContent>
            <ol className="mm-plainlist">
              {b.cohort.map((c) => <li key={c.brand_id}><Text as="span" variant="caption">{`${c.vendor ?? 'Vendor'}: ${fmt(c.value, unit)}`}</Text></li>)}
            </ol>
          </CollapsibleContent>
        </Collapsible>
      )}
    </Stack>
  );
}

export function Benchmark({ marketId, brandId, color, days = 30 }: { marketId: number; brandId: number; color?: string | null; days?: number }) {
  const [data, setData] = useState<VendorBenchmarks | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    setData(null);
    setError(null);
    getVendorBenchmarks(marketId, brandId, days).then((d) => live && setData(d), (e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, [marketId, brandId, days]);

  return (
    <Panel
      title="Benchmark"
      description="This vendor against every other vendor in the market with a valid value for the same metric, and against the leading measured vendors on it. The vendor is left out of both comparisons, so “above the market median” isn’t partly a statement about itself. The median leads because headcount, funding and attention are skewed: one large vendor moves an average and leaves a median alone."
    >
      {error ? <Banner tone="error" title="The benchmark didn’t load" description={error} /> : !data ? <Skeleton variant="text" lines={6} /> : (
        <Stack gap="lg">
          {data.metrics.map((b) => <Row key={b.metric.key} b={b} days={data.period_days} color={color} />)}
          <Text variant="hint">{data.note}</Text>
        </Stack>
      )}
    </Panel>
  );
}
