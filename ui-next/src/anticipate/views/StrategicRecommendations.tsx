import { Banner, Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, Grid, Icon, Panel, SettingRow, Stack, Text, type IconName } from '@aunoo/ui';
import { CitedText } from '../components/CitedText';
import { HorizonBar, HorizonIcon, type HorizonTone } from '../components/StrategyParts';
import { Disclosure } from '../components/Disclosure';
import { ViewState } from '../components/ViewState';
import { frameworkOf, horizonOf, nextStepsOf, type Horizon } from '../lib/model';
import type { ViewProps } from './types';

const HORIZONS: { key: 'near_term' | 'mid_term' | 'long_term'; title: string; icon: IconName; tone: HorizonTone }[] = [
  { key: 'near_term', title: 'Near-term', icon: 'Clock', tone: 'near' },
  { key: 'mid_term', title: 'Mid-term', icon: 'TrendUp', tone: 'mid' },
  { key: 'long_term', title: 'Long-term', icon: 'Target', tone: 'long' },
];

function HorizonCard({ title, icon, tone, horizon, axis }: { title: string; icon: IconName; tone: HorizonTone; horizon: Horizon; axis: { min: number; max: number } }) {
  return (
    <Panel headingLevel={3} title={<><HorizonIcon tone={tone}><Icon name={icon} size="sm" /></HorizonIcon> {title}</>} description={horizon.timeframe || undefined}>
      <Stack gap="md">
        {horizon.trends.length === 0 ? (
          <Text variant="hint">No trends in this horizon.</Text>
        ) : (
          <Stack as="ul" gap="sm" label={`${title} trends`}>
            {horizon.trends.map((t) => (
              <li key={t.name}>
                <Collapsible>
                  <SettingRow
                    title={t.name}
                    description={t.description ? <CitedText text={t.description} /> : undefined}
                    actionsPlacement="title"
                    actions={(t.keyDrivers.length > 0 || t.impact) && <CollapsibleTrigger variant="ghost" size="sm">More</CollapsibleTrigger>}
                  >
                    <Stack gap="sm">
                      {t.confidence && <Chip size="sm" tone="muted">Confidence: {t.confidence}</Chip>}
                      <CollapsibleContent>
                        <Stack gap="sm">
                          {t.keyDrivers.length > 0 && <Text variant="hint">Key drivers: {t.keyDrivers.join(', ')}</Text>}
                          {t.impact && <Text variant="hint">Potential impact: <CitedText text={t.impact} /></Text>}
                        </Stack>
                      </CollapsibleContent>
                    </Stack>
                  </SettingRow>
                </Collapsible>
              </li>
            ))}
          </Stack>
        )}
        {/* The old page drew fixed years here; these come from the horizon's own timeframe, in the horizon's colour */}
        {horizon.years && (
          <HorizonBar label={`${title} horizon`} start={horizon.years.start} end={horizon.years.end} min={axis.min} max={axis.max} tone={tone} />
        )}
      </Stack>
    </Panel>
  );
}

export function StrategicRecommendations({ analysis, tab }: ViewProps) {
  const data = analysis.data ?? {};
  const horizons = HORIZONS.map((h) => ({ ...h, horizon: horizonOf(data.strategic_recommendations?.[h.key]) }));
  const years = horizons.flatMap((h) => (h.horizon.years ? [h.horizon.years.start, h.horizon.years.end] : []));
  const axis = years.length ? { min: Math.min(...years), max: Math.max(...years) } : { min: 2025, max: 2040 };
  const framework = frameworkOf(data);
  const steps = nextStepsOf(data);
  return (
    <ViewState
      analysis={analysis}
      generateLabel="Generate analysis"
      empty={{ icon: tab.icon, title: 'No recommendations yet', text: 'Generate the analysis to get recommendations for this topic. It takes 30–60 seconds.' }}
    >
      <Banner
        headingLevel={2}
        title="Strategic Recommendations"
        description="What to do now, next and later, grouped by time horizon and backed by cited evidence from the analysed articles."
      />
      <Grid columns={3} gap="md">
        {horizons.map((h) => <HorizonCard key={h.key} title={h.title} icon={h.icon} tone={h.tone} horizon={h.horizon} axis={axis} />)}
      </Grid>
      {framework && (
        <Panel title={framework.title} description="Principles to apply across all horizons.">
          <Grid as="ul" columns={2} gap="sm" label="Principles">
            {framework.principles.map((p) => (
              <li key={p.name}>
                <SettingRow title={p.name} description={<CitedText text={p.description} />}>
                  {(p.rationale || p.implementation) && (
                    <Stack gap="sm">
                      {p.rationale && <Text variant="hint">Why: <CitedText text={p.rationale} /></Text>}
                      {p.implementation && <Text variant="hint">How: {p.implementation}</Text>}
                    </Stack>
                  )}
                </SettingRow>
              </li>
            ))}
          </Grid>
        </Panel>
      )}
      {steps.length > 0 && (
        <Panel title="Next Steps">
          <Grid as="ul" columns={2} gap="sm" label="Next steps">
            {steps.map((s, i) => (
              <li key={`${i}-${s.action}`}>
                <SettingRow
                  title={<>{i + 1}. <CitedText text={s.action} /></>}
                  description={[s.timeline, s.stakeholders.join(', ')].filter(Boolean).join(' · ') || undefined}
                  actions={s.priority && <Chip size="sm" tone={s.priority.toLowerCase() === 'high' ? 'warning' : 'neutral'}>{s.priority}</Chip>}
                  actionsPlacement="title"
                >
                  {s.metrics.length > 0 && <Text variant="caption">Success metrics: {s.metrics.join(', ')}</Text>}
                </SettingRow>
              </li>
            ))}
          </Grid>
        </Panel>
      )}
      <Disclosure
        dashboard="Strategic Recommendations"
        purpose="To synthesize actionable strategic insights from analyzed content"
        model={data.model_used}
        generatedAt={data.generated_at}
      />
    </ViewState>
  );
}
