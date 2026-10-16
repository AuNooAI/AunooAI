import { useEffect, useState } from 'react';
import { ReportSections } from '../common/ReportSections';
import type { Confirm } from '@aunoo/shell';
import { Banner, Button, Chip, EmptyState, Grid, Icon, Panel, Skeleton, Stack, Stat, Text } from '@aunoo/ui';
import { generateNarrative, getLatestNarrative, type NarrativeResponse } from '@monolith/scienceFundingApi';
import { errorText } from '../../../shell';
import { download } from '../../feed/api';
import { fmtDateTime, periodText, SCIENCE_TOPIC } from './labels';

/*
 * Insights: the AI-written science funding report, as the old ScienceInsightsTab. On open it shows
 * the last saved report (a plain read). Writing a new one calls the AI and only runs from the
 * button. The old tab also wrote a new report whenever the header's Refresh was pressed while this
 * tab was open; Refresh now only reloads data. The old footer named a model ("GPT-4.1-mini") that
 * wasn't the one used; the Explore page's own disclosure covers this tab instead.
 */

interface Report extends NarrativeResponse {
  saved?: boolean;
  days_back?: number | null;
}

const top = (rec: Record<string, number> | undefined, n: number) => Object.entries(rec || {}).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).slice(0, n);

function toMarkdown(r: Report) {
  const list = (rec: Record<string, number> | undefined, n = 99) => top(rec, n).map(([k, v]) => `- **${k}:** ${v}`).join('\n') || '- none';
  return [
    '# ScienceWatch report',
    '',
    `**Written:** ${fmtDateTime(r.generated_at)}`,
    `**Articles from:** ${r.data_summary.date_range.start} to ${r.data_summary.date_range.end}`,
    `**Articles read:** ${r.data_summary.total_categorized}`,
    '',
    '---',
    '',
    r.narrative,
    '',
    '---',
    '',
    '## Figures behind the report',
    '',
    '### Categories',
    list(r.data_summary.categories),
    '',
    '### Top themes',
    list(r.data_summary.top_themes, 5),
    '',
    '### Escalation language',
    list(r.data_summary.escalation),
    '',
    '_Written by AI from the collected articles. It may contain errors; check the sources before acting on it._',
  ].join('\n');
}

export function Insights({ daysBack, model, notify, askConfirm }: { daysBack: number; model: string; notify: (m: string) => void; askConfirm: (c: Confirm) => void }) {
  const [report, setReport] = useState<Report | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getLatestNarrative(SCIENCE_TOPIC).then(
      (s) => live && setReport(s ? { narrative: s.narrative, generated_at: s.generated_at, data_summary: s.data_summary, saved: true, days_back: s.days_back } : null),
      (e) => {
        if (!live) return;
        setError(errorText(e));
        setReport(null);
      },
    );
    return () => {
      live = false;
    };
  }, []);

  const write = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await generateNarrative({ topic: SCIENCE_TOPIC, days_back: daysBack, model });
      setReport({ ...r, saved: true, days_back: daysBack });
      notify('Report written and saved');
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const ask = () =>
    askConfirm({
      title: report ? 'Write a new report?' : 'Write the report?',
      message: `The AI (${model || 'the default model'}) reads the categorised articles from ${periodText(daysBack)}, with their category, theme and escalation counts, and writes a report. It is saved, and earlier reports stay in the history.`,
      action: 'Write the report',
      onConfirm: () => void write(),
    });

  const s = report?.data_summary;
  return (
    <Panel
      title="Science funding report"
      description="An AI-written reading of the categorised articles: trends, themes, escalation and what to watch."
      headerAside={
        <Stack direction="row" gap="sm">
          {report && <Button variant="secondary" iconStart={<Icon name="DownloadSimple" size="sm" />} onClick={() => download(`sciencewatch-report-${report.generated_at.slice(0, 10)}.md`, toMarkdown(report))}>Download</Button>}
          {report !== undefined && (
            <Button iconStart={<Icon name="Sparkle" size="sm" />} disabled={busy} onClick={ask}>{busy ? 'Writing…' : report ? 'Write a new report' : 'Write the report'}</Button>
          )}
        </Stack>
      }
    >
      <Stack gap="lg">
        {error && <Banner tone="error" title="Something went wrong" description={error} />}
        {busy && <Banner tone="info" title="Writing the report" description="This usually takes under a minute." />}
        {report === undefined ? <Skeleton variant="text" lines={8} /> : !report ? (
          <EmptyState icon="FileText" title="No report yet">
            Write one to get a reading of the categorised articles: what changed, the themes behind it, signs of escalation and what to watch next. It needs categorised articles to work from.
          </EmptyState>
        ) : (
          <>
            <Stack direction="row" gap="sm">
              {report.saved && <Chip tone="muted" size="sm">Saved</Chip>}
              <Text as="span" variant="caption">{`Written ${fmtDateTime(report.generated_at)}${report.days_back != null ? `, covering ${periodText(report.days_back)}` : ''}`}</Text>
            </Stack>
            {s && (
              <Grid columns={3} gap="md">
                <Stat label="Articles read" value={s.total_categorized.toLocaleString()} meta={`From ${s.date_range.start} to ${s.date_range.end}`} />
                <Stat
                  label="Top categories"
                  size="compact"
                  wrapValue
                  value={top(s.categories, 3).map(([k, v]) => `${k} (${v})`).join(', ') || 'None'}
                />
                <Stat
                  label="Escalation language"
                  value={Object.values(s.escalation || {}).reduce((a, b) => a + b, 0).toLocaleString()}
                  meta={top(s.escalation, 2).map(([k, v]) => `${k}: ${v}`).join(', ') || undefined}
                />
              </Grid>
            )}
            <ReportSections idPrefix="science-report" markdown={report.narrative} />
          </>
        )}
      </Stack>
    </Panel>
  );
}
