import { useEffect, useState } from 'react';
import { ArticleCard, Banner, Button, Chip, Eyebrow, Grid, Icon, Panel, RangeBar, SettingRow, Stack, Text } from '@aunoo/ui';
import { generateHorizonsExecutiveSummary, getFutureHorizonsRaw, getHorizonsExecutiveSummary } from '@monolith/api';
import { api, errorText } from '../../shell';
import { CitedText, stripCitations } from '../components/CitedText';
import { Disclosure } from '../components/Disclosure';
import { ThreeHorizonsChart } from '../components/HorizonsCharts';
import { ViewState } from '../components/ViewState';
import { downloadFile } from '../lib/download';
import { execSummariesOf, scenariosOf, type Band, type ExecSummary, type Payload, type Scenario } from '../lib/model';
import type { ViewProps } from './types';

const BANDS: { id: Band; label: string; column: string; color: 1 | 2 | 3 }[] = [
  { id: 'h1', label: 'Horizon 1', column: 'Current / Declining', color: 1 },
  { id: 'h2', label: 'Horizon 2', column: 'Transition / Innovation', color: 2 },
  { id: 'h3', label: 'Horizon 3', column: 'Future / Emerging Vision', color: 3 },
];

/** Scenarios from the tab's run, or (as on the old page) the topic's latest stored horizons run. */
function useScenarios(data: Payload | null, topic: string) {
  const own = scenariosOf(data?.scenarios);
  const [fallback, setFallback] = useState<{ runId: string; scenarios: Scenario[] } | null>(null);
  useEffect(() => {
    setFallback(null);
    if (!topic || own.length > 0) return;
    let alive = true;
    api<{ run_id: string }>(`/api/forecast/topics/${encodeURIComponent(topic)}/latest-run`)
      .then((r) => getFutureHorizonsRaw(r.run_id).then((raw) => ({ runId: r.run_id, raw })))
      .then(({ runId, raw }) => {
        const out = typeof raw?.raw_output === 'string' ? JSON.parse(raw.raw_output) : raw?.raw_output;
        const scenarios = scenariosOf(out?.scenarios);
        if (alive && scenarios.length) setFallback({ runId, scenarios });
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topic, own.length]);
  return own.length > 0 ? { runId: (data?.analysis_id as string) ?? null, scenarios: own, fromFallback: false } : fallback ? { ...fallback, fromFallback: true } : null;
}

/**
 * The fields the shared summary model leaves out, read from the raw summary as the old page did
 * (foresightAdapters.toHorizonsResponse): the consensus share, which fork branch is the positive one
 * (condition A) and which the warning (condition B), and the minority view's share of sources.
 */
function rawExtras(raw: Payload | undefined) {
  const pctRaw = raw?.consensus_percentage ?? raw?.consensus_pct;
  const pct = pctRaw != null && Number.isFinite(Number(pctRaw)) ? Math.round(Number(pctRaw)) : null;
  const fork = raw?.decision_fork ?? {};
  const kinds: ('pos' | 'warn')[] = [];
  if (fork?.condition_a && (fork.condition_a.condition || fork.condition_a.outcome)) kinds.push('pos');
  if (fork?.condition_b && (fork.condition_b.condition || fork.condition_b.outcome)) kinds.push('warn');
  return { pct, kinds, minorityRange: raw?.minority_view?.percentage_range ? String(raw.minority_view.percentage_range) : null };
}

function SummaryCard({ s, raw }: { s: ExecSummary; raw?: Payload }) {
  const x = rawExtras(raw);
  return (
    <SettingRow
      title={s.title}
      description={s.horizonLabel}
      actionsPlacement="title"
      actions={x.pct != null ? <Chip size="sm" tone={x.pct >= 70 ? 'success' : x.pct >= 50 ? 'warning' : 'muted'}>{`${x.pct}% consensus`}</Chip> : undefined}
    >
      <Stack gap="sm">
        <Text variant="description"><CitedText text={s.statement} /></Text>
        {s.primarySignal && <Text><strong>{`Primary signal${x.pct != null ? ` (${x.pct}% consensus)` : ''}:`}</strong> <CitedText text={s.primarySignal} /></Text>}
        {s.minority && <Text variant="hint">Minority view{x.minorityRange ? ` (${x.minorityRange} of sources)` : ''}: <CitedText text={s.minority} /></Text>}
        {s.forks.length > 0 && (
          <Stack gap="sm">
            <Eyebrow as="h4">Decision fork</Eyebrow>
            {s.forks.map((f, i) => {
              const kind = x.kinds[i] ?? (i === 0 ? 'pos' : 'warn');
              return (
                <div key={i} className={`h3-fork h3-fork--${kind}`}>
                  <Icon name={kind === 'pos' ? 'CheckCircle' : 'Warning'} size="sm" />
                  <Text variant="description">
                    <strong>{f.condition}</strong> → {f.outcome}
                  </Text>
                </div>
              );
            })}
          </Stack>
        )}
        {s.windows.length > 0 && <Text variant="caption">Your window: {s.windows.map((w) => `${w.timeframe} to ${w.action}`).join('; ')}</Text>}
        {s.sources.length > 0 && <Text variant="caption">Based on: {s.sources.join(' · ')}</Text>}
      </Stack>
    </SettingRow>
  );
}

export function FutureHorizons({ analysis, tab, config, notify }: ViewProps) {
  const data = analysis.data;
  const run = useScenarios(data, config.topic);
  const [summaries, setSummaries] = useState<ExecSummary[] | null>(null);
  const [rawSummaries, setRawSummaries] = useState<Payload[]>([]);
  const [summaryBusy, setSummaryBusy] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  // A stored summary is shown only when it was made for this run and this topic
  useEffect(() => {
    setSummaries(null);
    setSummaryError(null);
    if (!run?.runId) return;
    let alive = true;
    getHorizonsExecutiveSummary(run.runId).then(
      (r) => {
        const e = r?.executive_summary;
        if (alive && e && (!e.topic || e.topic === config.topic)) {
          setSummaries(execSummariesOf(e.summaries));
          setRawSummaries(Array.isArray(e.summaries) ? e.summaries : []);
        }
      },
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, [run?.runId, config.topic]);

  const generateSummary = async () => {
    if (!run?.runId) return;
    setSummaryBusy(true);
    setSummaryError(null);
    try {
      const raw = run.scenarios.map((s) => ({ type: s.band, title: s.title, description: s.description, timeframe: s.timeframe, sentiment: s.sentiment }));
      const r = await generateHorizonsExecutiveSummary(run.runId, raw, config.topic, config.model, config.profileId ?? undefined);
      setSummaries(execSummariesOf(r?.executive_summary?.summaries));
      setRawSummaries(Array.isArray(r?.executive_summary?.summaries) ? r.executive_summary.summaries : []);
      notify('Executive summary generated');
    } catch (e) {
      setSummaryError(errorText(e));
    } finally {
      setSummaryBusy(false);
    }
  };

  // With a fallback run there's something to show even when this tab has no analysis
  const effective = run?.fromFallback && analysis.status === 'empty' ? { ...analysis, status: 'ready' as const } : analysis;
  const scenarios = run?.scenarios ?? [];
  const years = scenarios.flatMap((s) => (s.years ? [s.years.start, s.years.end] : []));
  const axis = years.length ? { min: Math.min(...years), max: Math.max(Math.max(...years), Math.min(...years) + 1) } : null;

  return (
    <ViewState
      analysis={effective}
      generateLabel="Generate analysis"
      empty={{ icon: tab.icon, title: 'No horizons yet', text: 'Generate the analysis to synthesise Three Horizons scenarios for this topic.' }}
    >
      <Panel
        title={`Future Horizons — ${config.topic}`}
        description={`${data?.articles_analyzed ? `Analyzed ${data.articles_analyzed} articles · ` : ''}Three Horizons scenario synthesis${run?.fromFallback ? ' · from the latest stored forecast run' : ''}`}
        headerAside={
          run?.runId && (
            <Button
              variant="secondary"
              size="sm"
              iconStart={<Icon name="DownloadSimple" size="sm" />}
              onClick={() =>
                downloadFile(`/api/trend-convergence/horizons/${encodeURIComponent(run.runId!)}/download.html`, `future-horizons-${config.topic}.html`).catch((e) =>
                  notify(`Download failed: ${errorText(e)}`),
                )
              }
            >
              Interactive HTML
            </Button>
          )
        }
      />

      {scenarios.length > 0 && (
        <Panel title="Three Horizons Model" description="From current systems (Horizon 1) through emerging innovations (Horizon 2) to future visions (Horizon 3). Each number is a scenario, placed on its horizon's curve at its middle year.">
          <ThreeHorizonsChart scenarios={scenarios} />
        </Panel>
      )}

      {/* Each scenario's own years, under the chart */}
      {axis && (
        <Panel title="Scenarios over time" description={`Where each scenario sits, ${axis.min}–${axis.max}.`}>
          <Stack gap="lg">
            {BANDS.map((b) => {
              const list = scenarios.filter((s) => s.band === b.id && s.years);
              if (!list.length) return null;
              return (
                <Stack key={b.id} gap="sm">
                  <Eyebrow as="h3">{`${b.label} — ${b.column}`}</Eyebrow>
                  {list.map((s, i) => (
                    <div key={s.id}>
                      <Text variant="hint">{`${stripCitations(s.title)} · ${s.years!.start}–${s.years!.end}`}</Text>
                      {/* One scale under the last bar of the band, not under every bar */}
                      <RangeBar label={stripCitations(s.title)} min={axis.min} max={axis.max} start={s.years!.start} end={s.years!.end} color={b.color} showScale={i === list.length - 1} />
                    </div>
                  ))}
                </Stack>
              );
            })}
          </Stack>
        </Panel>
      )}

      <Panel
        title="Strategic Consensus"
        description="Executive summary across the scenarios."
        headerAside={
          !summaries?.length &&
          run?.runId && (
            <Button size="sm" iconStart={<Icon name="Sparkle" size="sm" />} busy={summaryBusy} onClick={generateSummary}>
              {summaryBusy ? 'Generating…' : 'Generate executive summary'}
            </Button>
          )
        }
      >
        {summaryError && <Banner tone="error" icon="WarningCircle" title="Summary not generated" description={summaryError} />}
        {summaries?.length ? (
          <Grid as="ul" columns={2} gap="sm" label="Executive summaries">
            {summaries.map((s, i) => <li key={s.title}><SummaryCard s={s} raw={rawSummaries[i]} /></li>)}
          </Grid>
        ) : (
          !summaryError && <Text variant="hint">{summaryBusy ? 'Writing the summary — about a minute.' : 'No executive summary for this run yet.'}</Text>
        )}
      </Panel>

      <Panel title="Scenarios by Horizon">
        <Grid columns={3} gap="md">
          {BANDS.map((b) => (
            <Stack key={b.id} gap="sm">
              <Stack direction="row" gap="sm" wrap={false}>
                <Icon name={b.id === 'h1' ? 'ArrowDown' : b.id === 'h2' ? 'Lightning' : 'TrendUp'} size="sm" />
                <Text variant="label" as="div">{`${b.label} — ${b.column}`}</Text>
              </Stack>
              <Stack as="ul" gap="sm" label={b.column}>
                {scenarios.filter((s) => s.band === b.id).map((s) => (
                  <ArticleCard
                    key={s.id}
                    as="li"
                    variant="row"
                    meta={[s.timeframe, s.sentiment].filter(Boolean).join(' · ') || undefined}
                    title={s.title}
                    summary={<CitedText text={s.description} />}
                    flag={s.sentiment ? <Chip size="sm" tone={/neg/i.test(s.sentiment) ? 'warning' : /pos/i.test(s.sentiment) ? 'success' : 'neutral'}>{s.sentiment}</Chip> : undefined}
                  />
                ))}
              </Stack>
            </Stack>
          ))}
        </Grid>
      </Panel>

      <Disclosure dashboard="Future Horizons" purpose="To explore long-term implications and future scenarios" model={data?.model_used} generatedAt={data?.generated_at} />
    </ViewState>
  );
}
