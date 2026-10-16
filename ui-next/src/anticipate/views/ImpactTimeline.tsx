import { Banner, Collapsible, CollapsibleContent, CollapsibleTrigger, Grid, Panel, Stack, StatusDot, Text, TextLink } from '@aunoo/ui';
import { CitedText } from '../components/CitedText';
import { Disclosure } from '../components/Disclosure';
import { ImpactTimelineChart } from '../components/ImpactTimelineChart';
import { ViewState } from '../components/ViewState';
import type { Payload } from '../lib/model';
import type { ViewProps } from './types';

const labelOf = (s: unknown) => String(s ?? '').replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

function Sources({ citations, name }: { citations: Payload[]; name: string }) {
  if (!citations.length) return null;
  return (
    <Collapsible>
      <CollapsibleTrigger variant="ghost" size="sm">{`Sources (${citations.length})`}</CollapsibleTrigger>
      <CollapsibleContent>
        <Stack as="ul" gap="sm" label={`${name} sources`}>
          {citations.map((c, i) => (
            <li key={`${i}-${c.url}`}>{c.url ? <TextLink href={c.url} external>{c.title || c.url}</TextLink> : <Text as="span">{c.title}</Text>}</li>
          ))}
        </Stack>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function ImpactTimeline({ analysis, tab }: ViewProps) {
  const data = analysis.data ?? {};
  const items: Payload[] = (Array.isArray(data.impact_timeline) ? data.impact_timeline : []).filter((x: unknown) => x && typeof x === 'object');
  const insights: Payload[] = Array.isArray(data.key_insights) ? data.key_insights : [];
  // One axis for every row, from the analysis's own years and milestones (the old card fixed it at 2025–2040)
  const years = items
    .flatMap((i) => [Number(i.timeline_start), Number(i.timeline_end), ...(Array.isArray(i.tooltip_positions) ? i.tooltip_positions.map((m: Payload) => Number(m?.year)) : [])])
    .filter((y) => Number.isFinite(y) && y > 1900 && y < 2200);
  const min = years.length ? Math.min(...years) : new Date().getFullYear();
  const max = Math.max(years.length ? Math.max(...years) : min + 10, min + 1);
  return (
    <ViewState
      analysis={analysis}
      generateLabel="Generate analysis"
      empty={{ icon: tab.icon, title: 'No timeline yet', text: 'Generate the analysis to build the impact timeline for this topic.' }}
    >
      <Banner headingLevel={2} title="Impact Timeline" description="When each development is expected to bite, with the milestones along the way." />
      {items.length > 0 && (
        <Panel title="Timeline" description={`Expected window of impact, ${min}–${max}.`}>
          <Stack as="ul" gap="lg" label="Impact timeline">
            {items.map((it, i) => {
              const name = String(it.title || it.name || `Item ${i + 1}`);
              const start = Number(it.timeline_start) || min;
              const end = Number(it.timeline_end) || start;
              const marks: Payload[] = Array.isArray(it.tooltip_positions) ? it.tooltip_positions : [];
              return (
                <li key={`${i}-${name}`}>
                  <Stack gap="sm">
                    <Text variant="label" as="div">{name}</Text>
                    <Text variant="description" as="div"><CitedText text={it.description} /></Text>
                    <ImpactTimelineChart
                      name={name}
                      start={start}
                      end={end}
                      milestones={marks.map((m) => ({ year: Number(m.year), label: String(m.label ?? '') }))}
                      axis={{ min, max }}
                      color={i + 1}
                    />
                    <Sources citations={Array.isArray(it.citations) ? it.citations : []} name={name} />
                  </Stack>
                </li>
              );
            })}
          </Stack>
        </Panel>
      )}
      {insights.length > 0 && (
        <Panel title="Key Insights from Evidence Synthesis">
          <Grid as="ul" columns={2} gap="md" label="Key insights">
            {insights.map((k, i) => (
              <li key={i}>
                <Stack direction="row" wrap={false} gap="sm">
                  <StatusDot tone="accent" />
                  <Stack gap="sm">
                    {k.category && <Text variant="caption" as="div">{labelOf(k.category)}</Text>}
                    <Text variant="description" as="div"><strong><CitedText text={k.insight || k.quote} /></strong></Text>
                    {(k.relevance || k.source) && <Text variant="caption" as="div">{k.relevance || k.source}</Text>}
                    <Sources citations={Array.isArray(k.citations) ? k.citations : k.citation ? [k.citation] : []} name={`Insight ${i + 1}`} />
                  </Stack>
                </Stack>
              </li>
            ))}
          </Grid>
        </Panel>
      )}
      <Disclosure dashboard="Impact Timeline" purpose="To project temporal sequences of anticipated impacts" model={data.model_used} generatedAt={data.generated_at} />
    </ViewState>
  );
}
