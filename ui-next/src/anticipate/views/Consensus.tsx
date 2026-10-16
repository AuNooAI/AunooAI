import { useMemo, useState } from 'react';
import {
  ActivityRow, Banner, Button, Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, Eyebrow, Grid, Icon, LineItems, Meter, Panel,
  SegmentedControl, SettingRow, Stack, Stat, Text, TextField, TextLink,
} from '@aunoo/ui';
import { CitedText, stripCitations } from '../components/CitedText';
import { ConsensusTimeline, SentimentPie, TimingColumns } from '../components/ConsensusCharts';
import { Disclosure } from '../components/Disclosure';
import { ViewState } from '../components/ViewState';
import { downloadFile } from '../lib/download';
import { themesOf, type Payload, type Theme } from '../lib/model';
import type { ViewProps } from './types';

/** Themes below this agreement count as divergent ("worth attention"). */
const DIVERGENT_BELOW = 75;

/** The theme's projected milestones (9_timeframe_analysis.key_milestones), by year */
function milestonesOf(t: Theme): { year: number; milestone: string; significance?: string }[] {
  const raw = (t.timeframe as { key_milestones?: unknown } | undefined)?.key_milestones;
  return (Array.isArray(raw) ? raw : [])
    .map((m: Payload) => ({ year: Number(m?.year), milestone: String(m?.milestone ?? ''), significance: m?.significance ? String(m.significance) : undefined }))
    .filter((m) => Number.isFinite(m.year) && m.milestone)
    .sort((a, b) => a.year - b.year);
}

/** Where the theme peaks: the middle milestone inside its window, else the window's middle (as the old page) */
function peakOf(t: Theme): number | undefined {
  if (!t.timing) return undefined;
  const inside = milestonesOf(t).map((m) => m.year).filter((y) => y >= t.timing!.start && y <= t.timing!.end);
  return inside.length ? inside[Math.floor(inside.length / 2)] : Math.round((t.timing.start + t.timing.end) / 2);
}

const isDivergent = (t: Theme) => t.agreement != null && t.agreement < DIVERGENT_BELOW;

const sentimentTone = (s?: string) => {
  const v = (s ?? '').toLowerCase();
  return v.includes('pos') ? 'success' : v.includes('neg') || v.includes('crit') ? 'error' : 'neutral';
};

function Outlier({ o, tone }: { o: Payload; tone: 'success' | 'warning' }) {
  return (
    <Banner
      tone={tone}
      headingLevel={4}
      title={`${o.scenario ?? 'Scenario'}${o.year ? ` · ${o.year}` : ''}`}
      description={<CitedText text={o.details} />}
    />
  );
}

function ThemeDetails({ t }: { t: Theme }) {
  return (
    <Stack gap="lg">
      <Text variant="description"><CitedText text={t.description} /></Text>
      <LineItems
        label={`${t.title} consensus`}
        items={[
          ...(t.summary ? [{ id: 'type', label: 'Consensus type', amount: t.summary }] : []),
          ...(t.agreement != null ? [{ id: 'agreement', label: 'Majority agreement', amount: `${t.agreement}%` }] : []),
          ...(t.strength ? [{ id: 'strength', label: 'Strength', amount: t.strength }] : []),
          ...(t.evidence ? [{ id: 'evidence', label: 'Evidence quality', amount: `${t.evidence} · ${t.articles} articles` }] : []),
          ...(t.timing?.label ? [{ id: 'window', label: 'Consensus window', amount: t.timing.label }] : []),
        ]}
      />
      {(t.sentiment || t.timingDistribution.length > 0) && (
        <Grid columns={2} stackAt="small" gap="md">
          {t.sentiment && (
            <Stack gap="sm">
              <Eyebrow as="h4">Sentiment distribution</Eyebrow>
              <SentimentPie title={`${stripCitations(t.title)}: sentiment distribution`} sentiment={t.sentiment} articles={t.articles} />
            </Stack>
          )}
          {t.timingDistribution.length > 0 && (
            <Stack gap="sm">
              <Eyebrow as="h4">When sources expect it</Eyebrow>
              <TimingColumns title={`${stripCitations(t.title)}: when sources expect it`} buckets={t.timingDistribution} consensusLabel={t.timing?.label} />
            </Stack>
          )}
        </Grid>
      )}
      {t.implications && (
        <Stack gap="sm">
          <Eyebrow as="h4">Strategic implications</Eyebrow>
          <Text variant="description"><CitedText text={t.implications} /></Text>
        </Stack>
      )}
      {t.timeframe && (
        <LineItems
          label="What to do when"
          items={[
            ...(t.timeframe.immediate ? [{ id: 'now', label: 'Immediate', amount: String(t.timeframe.immediate) }] : []),
            ...(t.timeframe.short_term ? [{ id: 'short', label: 'Short-term', amount: String(t.timeframe.short_term) }] : []),
            ...(t.timeframe.mid_term ? [{ id: 'mid', label: 'Mid-term', amount: String(t.timeframe.mid_term) }] : []),
          ]}
        />
      )}
      {milestonesOf(t).length > 0 && (
        <Stack gap="sm">
          <Eyebrow as="h4">Projected milestones</Eyebrow>
          <Stack as="ul" gap="sm" label={`${stripCitations(t.title)} projected milestones`}>
            {milestonesOf(t).map((m, i) => (
              <ActivityRow key={`${m.year}-${i}`} as="li" primary={`${m.year} · ${m.milestone}`} secondary={m.significance} dotTone="pending" dotLabel={String(m.year)} />
            ))}
          </Stack>
        </Stack>
      )}
      {(t.optimistic.length > 0 || t.pessimistic.length > 0) && (
        <Grid columns={2} stackAt="small" gap="sm">
          <Stack gap="sm">
            <Eyebrow as="h4">Optimistic outliers</Eyebrow>
            {t.optimistic.map((o, i) => <Outlier key={i} o={o} tone="success" />)}
          </Stack>
          <Stack gap="sm">
            <Eyebrow as="h4">Pessimistic outliers</Eyebrow>
            {t.pessimistic.map((o, i) => <Outlier key={i} o={o} tone="warning" />)}
          </Stack>
        </Grid>
      )}
      {/* The old page never showed the decision windows the prompt produces */}
      {t.decisionWindows.length > 0 && (
        <Stack gap="sm">
          <Eyebrow as="h4">Decision windows</Eyebrow>
          <Stack as="ul" gap="sm" label="Decision windows">
            {t.decisionWindows.map((w, i) => (
              <ActivityRow
                key={i}
                as="li"
                primary={`${w.window ?? ''}${w.urgency ? ` · ${w.urgency}` : ''}: ${w.action ?? ''}`}
                secondary={[w.rationale, w.owner && `Owner: ${w.owner}`].filter(Boolean).join(' · ') || undefined}
                dotTone={(w.urgency ?? '').toLowerCase().startsWith('crit') ? 'accent' : 'pending'}
                dotLabel={w.urgency ?? 'Window'}
              />
            ))}
          </Stack>
        </Stack>
      )}
      {t.keyArticles.length > 0 && (
        <Stack gap="sm">
          <Eyebrow as="h4">Key supporting articles</Eyebrow>
          <Stack as="ul" gap="sm" label="Key supporting articles">
            {t.keyArticles.map((a, i) => (
              <li key={`${i}-${a.title}`}>
                <Stack gap="sm">
                  <Stack direction="row" wrap={false} gap="sm">
                    {a.sentiment && <Chip size="sm" tone={sentimentTone(a.sentiment)}>{a.sentiment}</Chip>}
                    {a.url ? <TextLink href={a.url} external>{a.title}</TextLink> : <Text as="span">{a.title}</Text>}
                  </Stack>
                  {a.summary && <Text variant="caption">{a.summary}</Text>}
                </Stack>
              </li>
            ))}
          </Stack>
        </Stack>
      )}
    </Stack>
  );
}

const scoreTone = (t: Theme) => (t.agreement == null ? 'neutral' : t.agreement >= 85 ? 'success' : t.agreement >= DIVERGENT_BELOW ? 'info' : 'warning');

/** The year most theme windows include. */
function peakYear(themes: Theme[]) {
  const count = new Map<number, number>();
  themes.forEach((t) => {
    if (!t.timing) return;
    for (let y = t.timing.start; y <= t.timing.end; y++) count.set(y, (count.get(y) ?? 0) + 1);
  });
  let best: [number, number] | null = null;
  count.forEach((n, y) => {
    if (!best || n > best[1]) best = [y, n];
  });
  return best as [number, number] | null;
}

export function Consensus({ analysis, tab, config, notify }: ViewProps) {
  const [view, setView] = useState('list');
  const [query, setQuery] = useState('');
  const data = analysis.data ?? {};
  const themes = useMemo(() => themesOf(data), [data]);
  const q = query.trim().toLowerCase();
  const shown = themes.filter((t) => !q || t.title.toLowerCase().includes(q) || t.description.toLowerCase().includes(q));
  const peak = peakYear(themes);
  const divergent = themes.filter((t) => t.agreement != null && t.agreement < DIVERGENT_BELOW).length;
  // One year axis for every theme's timeline, covering the consensus windows and the outliers
  const years = themes.flatMap((t) => [
    ...(t.timing ? [t.timing.start, t.timing.end] : []),
    ...[t.optimistic[0]?.year, t.pessimistic[0]?.year].map(Number).filter((y) => y > 1900 && y < 2200),
  ]);
  const axis = years.length ? { min: Math.min(...years), max: Math.max(Math.max(...years), Math.min(...years) + 5) } : null;
  const articles = data.articles_analyzed || data.total_articles_found || 0;
  const insights: Payload[] = (Array.isArray(data.key_insights) ? data.key_insights : []).filter((k: Payload) => k && k.quote);

  return (
    <ViewState
      analysis={analysis}
      generateLabel="Generate analysis"
      empty={{ icon: tab.icon, title: 'No consensus analysis yet', text: 'Generate the analysis to find where sources agree on this topic.' }}
    >
      <Panel
        title="Consensus Analysis"
        description={`${config.topic}: where sources agree, how strongly, and when.`}
        headerAside={
          data.analysis_id && (
            <Button
              variant="secondary"
              size="sm"
              iconStart={<Icon name="DownloadSimple" size="sm" />}
              onClick={() =>
                downloadFile(`/api/trend-convergence/consensus/${encodeURIComponent(data.analysis_id)}/download.html`, `consensus-analysis-${config.topic}.html`).catch((e) =>
                  notify(`Download failed: ${e instanceof Error ? e.message : e}`),
                )
              }
            >
              Interactive HTML
            </Button>
          )
        }
      >
        <Grid as="ul" columns={4} stackAt="small" gap="sm" label="Overview">
          <li><Stat label="Themes" value={themes.length} meta={`${themes.filter((t) => (t.strength ?? '').toLowerCase() === 'strong').length} strong`} /></li>
          <li><Stat label="Peak year" value={peak ? peak[0] : '—'} meta={peak ? `${peak[1]} theme(s) expect it` : 'No clear peak'} /></li>
          <li><Stat label="Divergent themes" value={divergent} meta={divergent ? `Below ${DIVERGENT_BELOW}% agreement` : 'Broad alignment'} /></li>
          <li><Stat label="Source articles" value={articles} meta={data.timeframe_days ? `Past ${data.timeframe_days} days` : 'Analysis window'} /></li>
        </Grid>
      </Panel>

      {insights.length > 0 && (
        <Panel title="Key insights" description="The findings the analysis singled out across all themes.">
          <Collapsible>
            <CollapsibleTrigger variant="secondary">{`Show the ${insights.length} key insight${insights.length === 1 ? '' : 's'}`}</CollapsibleTrigger>
            <CollapsibleContent>
              <Stack as="ul" gap="md" label="Key insights">
                {insights.map((k, i) => (
                  <li key={i}>
                    <Stack gap="sm">
                      <Text><CitedText text={String(k.quote ?? '')} /></Text>
                      {(k.relevance || k.source) && (
                        <Text variant="caption">{[k.relevance && `Why it matters: ${k.relevance}`, k.source].filter(Boolean).join(' · ')}</Text>
                      )}
                    </Stack>
                  </li>
                ))}
              </Stack>
            </CollapsibleContent>
          </Collapsible>
        </Panel>
      )}

      <Panel
        title="Consensus Themes"
        headerAside={
          <SegmentedControl
            label="Layout"
            value={view}
            onValueChange={setView}
            options={[
              { value: 'list', label: 'List view', icon: 'ListBullets', iconOnly: true },
              { value: 'grid', label: 'Grid view', icon: 'SquaresFour', iconOnly: true },
            ]}
          />
        }
      >
        <Stack gap="md">
          {themes.length > 3 && <TextField label="Search themes" hideLabel type="search" placeholder="Search themes…" value={query} onChange={setQuery} />}
          {shown.length === 0 && <Text>No themes match.</Text>}
          {view === 'grid' ? (
            <Grid as="ul" columns={2} gap="sm" label="Consensus themes">
              {shown.map((t) => (
                <li key={t.id}>
                  <SettingRow title={t.title} description={`${t.articles} articles${t.strength ? ` · ${t.strength}` : ''}${isDivergent(t) ? ' · High divergence' : ''}`}>
                    {t.agreement != null && <Meter label={`${t.title} agreement`} value={t.agreement} valueText={`${t.agreement}% agreement`} tone={t.agreement >= 85 ? 'success' : 'warning'} />}
                  </SettingRow>
                </li>
              ))}
            </Grid>
          ) : (
            <Stack as="ul" gap="sm" label="Consensus themes">
              {shown.map((t, i) => (
                <li key={t.id}>
                  <Collapsible defaultOpen={i === 0}>
                    <SettingRow
                      title={t.title}
                      description={`${t.articles} articles${t.summary ? ` · ${t.summary}` : ''}`}
                      actionsPlacement="title"
                      actions={
                        <>
                          {isDivergent(t) && <Chip size="sm" tone="warning">High divergence</Chip>}
                          {t.agreement != null && <Chip size="sm" tone={scoreTone(t)}>{`${t.agreement}%${t.strength ? ` ${t.strength.toLowerCase()}` : ''}`}</Chip>}
                          <CollapsibleTrigger variant="onSurface" size="sm">Details</CollapsibleTrigger>
                        </>
                      }
                    >
                      <Stack gap="md">
                        {axis && (t.timing || t.optimistic.length > 0 || t.pessimistic.length > 0) && (
                          <ConsensusTimeline title={stripCitations(t.title)} window={t.timing} peak={peakOf(t)} optimistic={t.optimistic[0]} pessimistic={t.pessimistic[0]} axis={axis} />
                        )}
                        <CollapsibleContent>
                          <ThemeDetails t={t} />
                        </CollapsibleContent>
                      </Stack>
                    </SettingRow>
                  </Collapsible>
                </li>
              ))}
            </Stack>
          )}
        </Stack>
      </Panel>

      <Disclosure
        dashboard="Consensus Analysis"
        purpose="To analyze convergent themes across multiple sources and identify areas of agreement, emerging consensus, and divergent viewpoints"
        model={data.model_used}
        generatedAt={data.generated_at}
      />
    </ViewState>
  );
}
