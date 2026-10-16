import { useMemo, useRef, useState } from 'react';
import {
  Button, Chip, EmptyState, Grid, Icon, IconButton, Menu, Meter, Panel, RadarChart, ScatterChart, SegmentedControl, Stack, Table, Text, TextLink,
  type ChartColor,
} from '@aunoo/ui';
import { downloadElementPng, downloadPdf } from '../../explore/shared/exports';
import { errorText } from '../../shell/api';
import { FIELDS, FIELD_LABEL, agreementByField, pct, rankModels, resultsCsvUrl, resultsMarkdown, type ArenaResults, type MatrixRow } from './api';
import './arena.css';

/*
 * One evaluation's results, as the old page's results section: the rankings, four charts, the
 * outlier analysis and the field-by-field answer matrix, with PDF, image and CSV exports.
 */

const COLORS: ChartColor[] = [1, 2, 3, 4, 5];
/** The old page's thresholds: above 30% disagreement is high, above 15% medium */
const outlierTone = (r: number): 'error' | 'warning' | 'success' => (r > 0.3 ? 'error' : r > 0.15 ? 'warning' : 'success');

function biasTone(bias: string): 'info' | 'neutral' | 'warning' | 'error' | 'success' {
  const b = bias.toLowerCase();
  if (b.includes('conspiracy') || b.includes('pseudo') || b.includes('questionable')) return 'error';
  if (b.includes('satire')) return 'warning';
  if (b.includes('least biased') || b.includes('pro-science')) return 'success';
  return 'info';
}
function factualTone(f: string): 'success' | 'warning' | 'error' | 'neutral' {
  const s = f.toLowerCase();
  if (s.includes('very high') || (s.includes('high') && !s.includes('very low'))) return 'success';
  if (s.includes('mostly')) return 'neutral';
  if (s.includes('mixed')) return 'warning';
  if (s.includes('low')) return 'error';
  return 'neutral';
}

function ArticleCell({ row, index }: { row: MatrixRow; index: number }) {
  const details = [
    row.news_source && `Publication: ${row.news_source}`,
    row.mbfc_credibility_rating && `Credibility: ${row.mbfc_credibility_rating}`,
    row.bias_country && `Country: ${row.bias_country}`,
    row.press_freedom && `Press freedom: ${row.press_freedom}`,
    row.media_type && `Media type: ${row.media_type}`,
  ].filter(Boolean).join(' · ');
  return (
    <Stack gap="sm">
      <TextLink href={row.article_uri} external>{`Article ${index + 1}`}</TextLink>
      <Text variant="caption">{row.article_title ? (row.article_title.length > 70 ? `${row.article_title.slice(0, 70)}…` : row.article_title) : 'No title available'}</Text>
      {(row.bias || row.factual_reporting) && (
        <Stack direction="row" gap="sm">
          {row.bias && <Chip size="sm" tone={biasTone(row.bias)} label={`Political bias: ${row.bias}`}>{row.bias}</Chip>}
          {row.factual_reporting && <Chip size="sm" tone={factualTone(row.factual_reporting)} label={`Factual reporting: ${row.factual_reporting}`}>{row.factual_reporting}</Chip>}
        </Stack>
      )}
      {details && <Text variant="fine">{details}</Text>}
    </Stack>
  );
}

export function Results({ results, onClose, notify }: { results: ArenaResults; onClose: () => void; notify: (m: string) => void }) {
  const run = results.run_details;
  const ranked = useMemo(() => rankModels(results), [results]);
  const agreement = useMemo(() => agreementByField(results), [results]);
  const scores = results.outlier_analysis?.model_outlier_scores ?? {};
  const outliers = results.outlier_analysis?.outlier_models ?? {};
  const matrices = results.matrix_data?.field_matrices ?? {};
  const fields = FIELDS.filter((f) => matrices[f]);
  const [field, setField] = useState<string>(fields[0] ?? 'sentiment');
  const root = useRef<HTMLDivElement>(null);
  const models = Object.keys(results.statistics ?? {});

  const exportAs = async (id: string) => {
    try {
      if (id === 'pdf') await downloadPdf({ filename: `model-bias-arena-${run.id}.pdf`, title: `Model Bias Arena: ${run.name}`, subtitle: run.description ?? undefined, markdown: resultsMarkdown(results) });
      else if (id === 'png' && root.current) await downloadElementPng(root.current, `model-bias-arena-${run.id}.png`);
      else if (id === 'csv') window.location.href = resultsCsvUrl(run.id);
    } catch (e) {
      notify(`Export failed: ${errorText(e)}`);
    }
  };

  const fm = matrices[field];
  const isOutlier = (model: string, uri: string) => (outliers[field]?.[model] ?? []).some((o) => o.article_uri === uri);

  return (
    <Stack gap="lg">
      <Panel
        title={`Results: ${run.name}`}
        description={`Benchmark ${run.benchmark_model}, compared with ${run.selected_models.join(', ')}. ${run.article_count} articles, ${run.rounds} round${run.rounds === 1 ? '' : 's'}.`}
        headerAside={
          <Stack direction="row" gap="sm">
            <Menu
              label="Export"
              align="end"
              trigger={<Button variant="secondary" iconStart={<Icon name="DownloadSimple" size="sm" />} iconEnd={<Icon name="CaretDown" size="sm" />}>Export</Button>}
              items={[
                { id: 'pdf', label: 'Report (PDF)', icon: 'FileText' },
                { id: 'png', label: 'These results as an image (PNG)', icon: 'ChartBar' },
                { id: 'csv', label: 'Every answer, with the analysis (CSV)', icon: 'Table' },
              ]}
              onSelect={(id) => void exportAs(id)}
            />
            <IconButton icon={<Icon name="X" size="sm" />} label="Close the results" onClick={onClose} />
          </Stack>
        }
      >
        <Text variant="caption">Lower score is better. It weighs how often a model disagrees with the others (40%), how often it failed to answer (30%) and how long it took (30%, with 10 seconds counting as 1).</Text>
      </Panel>

      <div ref={root} className="arena-export">
        <Stack gap="lg">
          <Panel title="Model rankings" headingLevel={3}>
            <Table
              caption="Model rankings"
              hideCaption
              rows={ranked}
              rowKey={(r) => r.name}
              emptyText="No model data in this evaluation."
              columns={[
                { key: 'rank', header: 'Rank', render: (r) => `#${r.rank}` },
                { key: 'name', header: 'Model', rowHeader: true, render: (r) => `${r.name}${r.name === run.benchmark_model ? ' (benchmark)' : ''}` },
                { key: 'responseTime', header: 'Response time (ms)', align: 'end', render: (r) => r.responseTime.toLocaleString() },
                { key: 'successRate', header: 'Success rate', align: 'end', render: (r) => pct(r.successRate) },
                { key: 'outlierRate', header: 'Outlier rate', align: 'end', render: (r) => pct(r.outlierRate) },
                { key: 'evaluations', header: 'Answers' },
                { key: 'score', header: 'Score', align: 'end', render: (r) => r.score.toFixed(3) },
              ]}
            />
          </Panel>

          <Grid columns={2} stackAt="small" gap="md">
            <Panel title="Average response time" headingLevel={3}>
              <Stack as="ul" gap="sm" label="Average response time by model">
                {(() => {
                  const max = Math.max(1, ...models.map((m) => results.statistics[m].mean_response_time || 0));
                  return models.map((m) => (
                    <li key={m} className="arena-bar">
                      <Text variant="label" as="span">{m}</Text>
                      <Meter label={`${m} average response time`} value={results.statistics[m].mean_response_time || 0} max={max} valueText={`${Math.round(results.statistics[m].mean_response_time || 0).toLocaleString()} ms`} />
                    </li>
                  ));
                })()}
              </Stack>
            </Panel>
            <Panel title="Success rate against outlier rate" headingLevel={3}>
              <ScatterChart
                title="Success rate against outlier rate"
                xLabel="Success rate (%)"
                yLabel="Outlier rate (%)"
                points={models.map((m, i) => ({ id: m, label: m, x: (results.statistics[m].success_rate || 0) * 100, y: (scores[m]?.outlier_rate || 0) * 100, color: ((i % 5) + 1) as 1 | 2 | 3 | 4 | 5 }))}
                formatValue={(v) => `${v.toFixed(0)}%`}
              />
              <Text variant="caption">Best is bottom right: answers every time and rarely disagrees with the others.</Text>
            </Panel>
            <Panel title="Agreement with the benchmark, by field" headingLevel={3}>
              {agreement.length ? (
                <RadarChart
                  title="Agreement with the benchmark, by field"
                  axes={FIELDS.map((f) => FIELD_LABEL[f])}
                  series={agreement.map((a, i) => ({ id: a.model, label: a.model, color: COLORS[i % COLORS.length], values: a.values }))}
                  formatValue={(v) => `${v.toFixed(0)}%`}
                />
              ) : <Text>No field answers to compare.</Text>}
              <Text variant="caption">Share of each model’s answers that match the benchmark’s, errors left out.</Text>
            </Panel>
            <Panel title="Outlier rate by model" headingLevel={3}>
              <Stack as="ul" gap="sm" label="Outlier rate by model">
                {models.map((m) => {
                  const r = scores[m]?.outlier_rate ?? 0;
                  return (
                    <li key={m} className="arena-bar">
                      <Text variant="label" as="span">{m}</Text>
                      <Meter label={`${m} outlier rate`} value={r * 100} max={100} tone={outlierTone(r)} valueText={pct(r)} />
                    </li>
                  );
                })}
              </Stack>
              <Text variant="caption">Red above 30%, amber above 15%.</Text>
            </Panel>
          </Grid>

          <Panel title="Model outlier analysis" headingLevel={3} description="How often each model disagrees with the majority across all fields. A high rate means a model often answers differently from most of the others.">
            {Object.keys(scores).length === 0 ? <Text>No outlier analysis for this evaluation.</Text> : (
              <Stack gap="md">
                <Grid columns={3} stackAt="small" gap="md">
                  {Object.entries(scores).sort((a, b) => b[1].outlier_rate - a[1].outlier_rate).map(([m, s]) => (
                    <Stack key={m} gap="sm" className="arena-card">
                      <Stack direction="row" justify="between" gap="sm">
                        <Text variant="label" as="span">{`${m}${m === run.benchmark_model ? ' (benchmark)' : ''}`}</Text>
                        <Chip size="sm" tone={outlierTone(s.outlier_rate)}>{`${pct(s.outlier_rate)} outlier`}</Chip>
                      </Stack>
                      <Text variant="caption">{`${s.outlier_count} disagreements over ${s.total_articles} articles. ${s.is_outlier ? 'Flagged as an outlier.' : 'Not flagged as an outlier.'}`}</Text>
                    </Stack>
                  ))}
                </Grid>
                {Object.entries(outliers).some(([, v]) => Object.keys(v).length) && (
                  <Stack gap="sm">
                    <Text variant="label">Disagreements by field</Text>
                    {Object.entries(outliers).filter(([, v]) => Object.keys(v).length).map(([f, v]) => (
                      <Text key={f} variant="caption">{`${FIELD_LABEL[f] ?? f}: ${Object.entries(v).map(([m, list]) => `${m} (${list.length})`).join(', ')}`}</Text>
                    ))}
                  </Stack>
                )}
              </Stack>
            )}
          </Panel>
        </Stack>
      </div>

      <Panel title="Answers by field" headingLevel={3} description="Each model’s answer for each article, next to the benchmark’s. Green matches the benchmark, red disagrees with the majority, grey is an error or no answer.">
        {!fields.length ? <EmptyState icon="Table" title="No answer matrix">This evaluation has no field-by-field answers.</EmptyState> : (
          <Stack gap="md">
            <div className="arena-scroll">
              <SegmentedControl label="Field" options={fields.map((f) => ({ value: f, label: FIELD_LABEL[f] }))} value={field} onValueChange={setField} />
            </div>
            {fm && (
              <Table
                caption={`Answers for ${FIELD_LABEL[field]}`}
                hideCaption
                scroll
                rows={fm.matrix.map((r, i) => ({ ...r, _i: i }))}
                rowKey={(r) => `${r.article_uri}:${r._i}`}
                columns={[
                  { key: 'article', header: 'Article', rowHeader: true, wrap: true, render: (r) => <ArticleCell row={r} index={r._i} /> },
                  { key: 'benchmark', header: `Benchmark (${run.benchmark_model})`, wrap: true, render: (r) => r.benchmark_value || 'Not set' },
                  ...fm.models.map((m) => ({
                    key: m, header: m, wrap: true,
                    render: (r: MatrixRow & { _i: number }) => {
                      const c = r.model_values?.[m];
                      if (!c || c.has_error) return <Chip size="sm" tone="muted">Error</Chip>;
                      const tone = isOutlier(m, r.article_uri) ? 'error' : c.value === r.benchmark_value ? 'success' : 'neutral';
                      return (
                        <Stack gap="sm">
                          <Chip size="sm" tone={tone}>{c.value || 'No answer'}</Chip>
                          {c.explanation && <Text variant="fine">{c.explanation}</Text>}
                        </Stack>
                      );
                    },
                  })),
                ]}
              />
            )}
          </Stack>
        )}
      </Panel>
    </Stack>
  );
}
