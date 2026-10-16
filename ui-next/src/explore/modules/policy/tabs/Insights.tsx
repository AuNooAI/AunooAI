import { useCallback, useEffect, useState } from 'react';
import { ReportSections } from '../../common/ReportSections';
import { Banner, Button, Chip, EmptyState, Grid, Icon, IconButton, Panel, Stack, Stat, Text } from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import { generateNarrative, getLatestNarrative, type NarrativeResponse } from '@monolith/policyTrackerApi';
import { errorText } from '../../../../shell';
import { download } from '../../../feed/api';
import { aiDays, fmtDate, periodText } from '../api';
import { Loading } from '../parts';
import type { PolicyTracker } from '../usePolicyTracker';

/*
 * The old PolicyInsightsTab: the AI's written report on the tracker data. Opening the tab reads the
 * last saved report (no AI). Writing one is a button, and writing over a report asks first.
 *
 * Changed from the old tab: its Refresh button quietly wrote a new report with the AI whenever this
 * tab was open; Refresh now only reloads the figures. Its disclosure named "GPT-4.1-mini" whatever
 * model ran; the report now goes to the model picked in the Explore filter bar, and the Explore
 * disclosure at the foot names it.
 */

const top = (r: Record<string, number> | undefined, n: number) => Object.entries(r ?? {}).sort((a, b) => b[1] - a[1]).slice(0, n);

export function Insights({ pt, model, notify, askConfirm }: { pt: PolicyTracker; model: string; notify: (m: string) => void; askConfirm: (c: Confirm) => void }) {
  const { topic, daysBack } = pt.config;
  const [report, setReport] = useState<(NarrativeResponse & { saved?: boolean }) | null>(null);
  const [loading, setLoading] = useState(true);
  const [writing, setWriting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setLoading(true);
    getLatestNarrative(topic).then(
      (s) => live && setReport(s ? { narrative: s.narrative, generated_at: s.generated_at, data_summary: s.data_summary, saved: true } : null),
      () => live && setReport(null),
    ).finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [topic]);

  const write = useCallback(async () => {
    setWriting(true);
    setError(null);
    try {
      const r = await generateNarrative({ topic, days_back: aiDays(daysBack), model });
      setReport({ ...r, saved: true });
      notify('Report written');
    } catch (e) {
      setError(errorText(e));
    } finally {
      setWriting(false);
    }
  }, [topic, daysBack, model, notify]);

  const span = daysBack === 0 ? 'the last two years (the longest the report can cover)' : periodText(aiDays(daysBack));
  const ask = () => {
    if (!report) return void write();
    askConfirm({
      title: 'Write a new report?',
      message: `The AI (${model}) reads the tracker figures for ${span} and writes a new report. It replaces the one shown here as the latest; older reports stay saved on the server.`,
      action: 'Write the report',
      onConfirm: () => void write(),
    });
  };

  const exportMd = () => {
    if (!report) return;
    const d = report.data_summary;
    const list = (r: Record<string, number> | undefined, n = 20) => top(r, n).map(([k, v]) => `- **${k}:** ${v}`).join('\n');
    download(
      `crisis-tracker-report-${new Date().toISOString().slice(0, 10)}.md`,
      `# US Crisis Tracker report\n\n**Written:** ${new Date(report.generated_at).toLocaleString('en-GB')}\n**Period:** ${d.date_range.start} to ${d.date_range.end}\n**Articles read:** ${d.total_articles} (${d.total_categorized} with categories)\n\n---\n\n${report.narrative}\n\n---\n\n## Figures behind the report\n\n### Categories\n${list(d.categories)}\n\n### Top themes\n${list(d.top_themes, 5)}\n\n### Escalation language\n${list(d.escalation)}\n\n*Written by AI from the collected articles. It may contain errors; check the sources before relying on it.*\n`,
    );
  };

  const d = report?.data_summary;
  return (
    <Panel
      title="Written report"
      headingLevel={3}
      description="An AI-written reading of the tracker’s figures: the trends, the themes, the escalation language and what to watch."
      headerAside={
        <Stack direction="row" gap="sm">
          {report && <IconButton icon={<Icon name="DownloadSimple" size="sm" />} label="Download the report as Markdown" onClick={exportMd} />}
          {(report || !loading) && (
            <Button iconStart={<Icon name="Sparkle" size="sm" />} disabled={writing || loading} onClick={ask}>
              {writing ? 'Writing…' : report ? 'Write a new report' : 'Write a report'}
            </Button>
          )}
        </Stack>
      }
    >
      <Stack gap="lg">
        {error && <Banner tone="error" title="The report wasn’t written" description={error} />}
        {writing && <Banner tone="info" title="The AI is writing the report" description="This usually takes under a minute." />}
        {loading ? <Loading lines={8} /> : !report ? (
          <EmptyState icon="FileText" title="No report yet">
            {`Write a report to have the AI (${model}) read the tracker figures for ${span}: the categories, themes, escalation language and institutions named. It needs classified articles to work from.`}
          </EmptyState>
        ) : (
          <>
            {report.saved && <Text variant="caption">{`Saved report, written ${fmtDate(report.generated_at)}.`}</Text>}
            {d && (
              <Grid columns={4} gap="sm" as="ul" label="Figures behind the report">
                <Stat as="li" label="Articles read" value={d.total_articles.toLocaleString()} />
                <Stat as="li" label="With categories" value={d.total_categorized.toLocaleString()} />
                <Stat as="li" label="Period" value={`${d.date_range.start} to ${d.date_range.end}`} wrapValue size="compact" />
                <Stat as="li" label="Categories present" value={String(Object.keys(d.categories ?? {}).length)} />
              </Grid>
            )}
            {d && (
              <Grid columns={3} gap="sm">
                {([['Largest categories', d.categories], ['Largest themes', d.top_themes], ['Escalation language', d.escalation]] as const).map(([label, r]) => (
                  <Stack key={label} gap="sm">
                    <Text variant="label">{label}</Text>
                    <Stack direction="row" gap="sm">
                      {top(r, 3).length ? top(r, 3).map(([k, v]) => <Chip key={k} tone="neutral" size="sm">{`${k}: ${v}`}</Chip>) : <Text variant="caption">none</Text>}
                    </Stack>
                  </Stack>
                ))}
              </Grid>
            )}
            <ReportSections idPrefix="policy-report" markdown={report.narrative} />
          </>
        )}
      </Stack>
    </Panel>
  );
}
