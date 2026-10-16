import { Button, Chip, EmptyState, Eyebrow, Grid, Icon, Panel, Skeleton, Stack, Text } from '@aunoo/ui';
import type { BwContext } from '../context';
import { periodLabel } from '../context';
import { ReportExport, ReportSections } from './analysis/Report';
import { useNarrative } from './analysis/useNarrative';

/*
 * The brand intelligence report (GET /narrative/latest; "Write" = POST /generate-narrative, which
 * calls the AI) and the brand's profile, as the old Insights tab.
 */

export function Insights({ bw, selectedBrands, focusBrand, notify }: BwContext) {
  const brand = selectedBrands[0] ?? focusBrand;
  const days = bw.config.daysBack;
  const r = useNarrative(brand?.id ?? null, brand?.display_name, days, notify);
  if (!brand) return <Panel title="Insights"><EmptyState icon="Target">Pick a brand above to see its report.</EmptyState></Panel>;
  const n = r.narrative;
  const meta = [
    n?.generated_at ? `Written ${new Date(n.generated_at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })}` : 'Not written yet',
    n?.data_summary?.total_articles != null ? `${n.data_summary.total_articles.toLocaleString('en-GB')} articles read` : null,
    n?.days_back != null ? `covering ${periodLabel(n.days_back)}` : null,
  ].filter(Boolean).join(' · ');

  const keywordGroups: [string, string[] | null | undefined][] = [
    ['Brand keywords', brand.brand_keywords], ['Products', brand.product_keywords], ['People', brand.people_keywords], ['Competitors', brand.competitor_keywords],
  ];

  return (
    <>
      <Panel
        title={`Brand intelligence report: ${n?.brand_name || brand.display_name}`}
        description={meta}
        headerAside={
          <Stack direction="row" gap="sm">
            {n && <ReportExport narrative={n} brandName={n.brand_name || brand.display_name} notify={notify} />}
            <Button variant="secondary" size="sm" iconStart={<Icon name="Sparkle" size="sm" />} disabled={r.generating} onClick={() => void r.generate()}>
              {r.generating ? 'Writing…' : n ? 'Write a new report' : 'Write the report'}
            </Button>
          </Stack>
        }
      >
        {r.loading ? <Skeleton variant="text" lines={8} /> : r.generating && !n ? (
          <Text variant="caption"><span role="status">The AI is reading this period’s articles, risks, incidents, social posts and workforce data. This takes about a minute.</span></Text>
        ) : n ? (
          <ReportSections narrative={n} sections={r.sections} />
        ) : (
          <EmptyState icon="FileText" title="No report yet">
            The report reads {periodLabel(days)} of articles, risk findings, incidents, social posts and workforce signal for {brand.display_name}, and writes it up as an analyst would.
          </EmptyState>
        )}
        {r.generating && n && <Text variant="caption"><span role="status">Writing a new report…</span></Text>}
      </Panel>

      <Panel title={brand.display_name} description={brand.description ?? undefined} headerAside={brand.is_primary ? <Chip tone="accent" icon={<Icon name="Star" size="sm" />}>Primary</Chip> : undefined}>
        <Grid columns={2} stackAt="small" gap="md">
          {keywordGroups.filter(([, kws]) => kws?.length).map(([label, kws]) => (
            <Stack key={label} gap="sm">
              <Eyebrow as="h3">{label}</Eyebrow>
              <Stack as="ul" direction="row" gap="sm" label={label}>
                {kws!.map((k) => <li key={k}><Chip size="sm" tone="neutral">{k}</Chip></li>)}
              </Stack>
            </Stack>
          ))}
        </Grid>
      </Panel>
    </>
  );
}
