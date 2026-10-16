import { useEffect, useState } from 'react';
import { FilterChipRow, Panel, Stack, Text, TextLink, Chip } from '@aunoo/ui';
import { getCoverageSplit, type Brand, type BWCoverageBucket, type BWCoverageSplit } from '@monolith/brandWatcherApi';
import { errorText } from '../../../../shell';

/*
 * How one brand's articles were labelled (docs/BRAND_RELEVANCE_SPEC.md), ported from
 * ui/src/components/newsfeed/BrandWatcherCoverage.tsx. Each article counts once; picking a
 * bucket lists its articles with the reason. Missing measurements show as unavailable, never zero.
 */

const BUCKETS: { key: BWCoverageBucket; label: string }[] = [
  { key: 'earned', label: 'Earned coverage' },
  { key: 'owned', label: 'Brand’s own content' },
  { key: 'fan', label: 'Fan and recipe sites' },
  { key: 'sector', label: 'Sector stories' },
  { key: 'passing', label: 'Passing mentions' },
  { key: 'other', label: 'Not coverage' },
  { key: 'deferred', label: 'Waiting' },
  { key: 'unavailable', label: 'Judgment unavailable' },
  { key: 'unlabelled', label: 'Decided before labels' },
  { key: 'invalid', label: 'Invalid label' },
];
const FIELD: Record<string, string> = { title: 'headline', summary: 'summary', text: 'article text' };

export function Coverage({ brand, daysBack }: { brand: Brand | null; daysBack: number }) {
  const [split, setSplit] = useState<BWCoverageSplit | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [bucket, setBucket] = useState<BWCoverageBucket | null>(null);
  const [rows, setRows] = useState<BWCoverageSplit['rows']>([]);

  useEffect(() => {
    if (!brand) return;
    let stale = false;
    setSplit(null);
    setError(null);
    setBucket(null);
    getCoverageSplit(brand.id, daysBack).then((s) => !stale && setSplit(s), (e: unknown) => !stale && setError(errorText(e)));
    return () => {
      stale = true;
    };
  }, [brand, daysBack]);

  useEffect(() => {
    if (!brand || !bucket) return;
    let stale = false;
    getCoverageSplit(brand.id, daysBack, bucket).then((s) => !stale && setRows(s.rows), (e: unknown) => !stale && setError(errorText(e)));
    return () => {
      stale = true;
    };
  }, [brand, daysBack, bucket]);

  if (!brand || (!split && !error)) return null;
  const title = `Coverage breakdown for ${brand.display_name}`;
  if (error) return <Text variant="caption">Coverage breakdown unavailable: {error}</Text>;
  if (!split!.available) return <Text variant="caption">Coverage breakdown unavailable: {split!.reason}</Text>;
  const present = BUCKETS.filter((b) => (split!.counts[b.key] ?? 0) > 0);
  if (!present.length) return <Text variant="caption">No articles were decided for {brand.display_name} in this period.</Text>;

  return (
    <Panel title={title} description={split!.note ?? 'Only earned coverage counts in the metrics and alerts.'} headingLevel={3}>
      <Stack gap="md">
        {present.length === 1 && present[0].key === 'unlabelled' && (
          <Text variant="caption">These articles were decided before brand labels existed. New articles get a breakdown as they arrive.</Text>
        )}
        <FilterChipRow
          label="Buckets"
          allLabel="None"
          options={present.map((b) => ({ value: b.key, label: `${b.label} (${split!.counts[b.key]})` }))}
          selected={bucket ? [bucket] : []}
          onChange={(v) => setBucket((v.filter((x) => x !== bucket)[0] as BWCoverageBucket | undefined) ?? null)}
          maxVisible={10}
        />
        {bucket && (
          rows.length === 0 ? <Text variant="caption">No articles in this bucket.</Text> : (
            <Stack as="ul" gap="sm" label="Articles in this bucket">
              {rows.map((r) => (
                <li key={r.uri}>
                  <Stack gap="sm">
                    <TextLink href={r.uri} external>{r.title || r.uri}</TextLink>
                    <Stack direction="row" gap="sm">
                      {r.source && <Text variant="caption" as="span">{r.source}</Text>}
                      {r.source_relation === 'owned' && <Chip size="sm" tone="accent">Brand’s own site</Chip>}
                      {r.source_relation === 'unknown' && <Chip size="sm" tone="muted">Publisher unknown</Chip>}
                      {r.limited_evidence && <Chip size="sm" tone="warning">Headline only</Chip>}
                      {r.matched && <Text variant="caption" as="span">Named as “{r.matched}” in the {FIELD[r.evidence_field ?? ''] ?? r.evidence_field ?? 'text'}</Text>}
                    </Stack>
                    {r.reason && <Text variant="caption">{r.reason}</Text>}
                  </Stack>
                </li>
              ))}
            </Stack>
          )
        )}
      </Stack>
    </Panel>
  );
}
