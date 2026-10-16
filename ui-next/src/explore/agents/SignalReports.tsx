import { useCallback, useEffect, useState } from 'react';
import type { Confirm } from '@aunoo/shell';
import { Banner, Button, Collapsible, CollapsibleContent, CollapsibleTrigger, EmptyState, Icon, IconButton, Panel, Skeleton, Stack, Text, TextLink } from '@aunoo/ui';
import { deleteSignalReport, getSignalReportById, getSignalReports, type SignalReport } from '@monolith/researchAgentsApi';
import { errorText } from '../../shell';
import { Markdown } from '../../shell/Markdown';
import { download } from '../feed/api';
import { downloadPdf } from '../shared/exports';
import { speakable, VoiceDialog } from './VoiceDialog';
import './agents.css';

/*
 * Reports the observer agents wrote, as the old Saved tab's SignalReportsTab. Loading the list and
 * opening a report only read; deleting asks first. Exported so the Saved tab can show it too.
 */

const fmt = (iso: string) => new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });

// A run with a voice set appends its audio link to the report; reuse it rather than paying again
const audioIn = (md?: string | null) => (md?.match(/\((\S+\.(?:mp3|wav|m4a))\)/i)?.[1] ?? null);

// A site writes a report a day per agent, so the list starts at the newest ten
const PAGE = 10;

export function SignalReports({ topic, notify, askConfirm, headingLevel = 2 }: { topic?: string; notify: (m: string) => void; askConfirm: (c: Confirm) => void; headingLevel?: 2 | 3 }) {
  const [reports, setReports] = useState<SignalReport[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [full, setFull] = useState<Record<number, SignalReport | 'loading' | 'failed'>>({});

  const load = useCallback(async () => {
    setError(null);
    try {
      const r = await getSignalReports({ topic, limit: 100 });
      setReports(r.reports || []);
    } catch (e) {
      setError(errorText(e));
      setReports((p) => p ?? []);
    }
  }, [topic]);
  useEffect(() => {
    setReports(null);
    void load();
  }, [load]);

  const open = async (id: number) => {
    if (full[id] && full[id] !== 'failed') return;
    setFull((f) => ({ ...f, [id]: 'loading' }));
    try {
      const r = await getSignalReportById(id);
      setFull((f) => ({ ...f, [id]: r.report }));
    } catch {
      setFull((f) => ({ ...f, [id]: 'failed' }));
    }
  };

  const remove = (r: SignalReport) =>
    askConfirm({
      title: `Delete “${r.name}”?`,
      message: 'The report is removed for everyone on this site. The agent’s matches stay.',
      action: 'Delete report',
      onConfirm: () => {
        deleteSignalReport(r.id).then(
          () => {
            setReports((p) => (p ?? []).filter((x) => x.id !== r.id));
            notify('Report deleted');
          },
          (e) => notify(`Not deleted: ${errorText(e)}`),
        );
      },
    });

  const exportPdf = (r: SignalReport) =>
    downloadPdf({ filename: `${r.name.replace(/[^a-z0-9]/gi, '_')}.pdf`, title: r.name, subtitle: [r.instruction_name, fmt(r.created_at)].filter(Boolean).join(' · '), markdown: r.report_content || 'This report has no text.' })
      .catch((e) => notify(`PDF not made: ${errorText(e)}`));
  const exportMd = (r: SignalReport) => download(`${r.name.replace(/[^a-z0-9]/gi, '_')}.md`, r.report_content || '');

  const [shown, setShown] = useState(PAGE);
  const [voicing, setVoicing] = useState<SignalReport | null>(null);
  return (
    <Panel
      title="Saved reports"
      headingLevel={headingLevel}
      description={reports ? `${reports.length} report${reports.length === 1 ? '' : 's'} written by observer agents${topic ? ` for ${topic}` : ''}` : undefined}
      headerAside={<IconButton icon={<Icon name="ArrowClockwise" size="sm" />} label="Reload reports" onClick={() => void load()} />}
    >
      {error && <Banner tone="error" title="Reports didn’t load" description={error} action={<Button variant="secondary" size="sm" onClick={() => void load()}>Try again</Button>} />}
      {!reports ? <Skeleton variant="text" lines={4} /> : reports.length === 0 && !error ? (
        <EmptyState icon="FileText" title="No reports yet">
          An agent writes a report after a run when “Write a report” is switched on in its settings, or when you run all agents with “Write one combined report”.
        </EmptyState>
      ) : (
        <Stack as="ul" gap="sm" label="Saved reports">
          {reports.slice(0, shown).map((r) => {
            const f = full[r.id];
            return (
              <li key={r.id}>
                <Collapsible onOpenChange={(o) => o && void open(r.id)}>
                  <Stack direction="row" justify="between" gap="sm" wrap={false}>
                    <Stack gap="sm">
                      <div><CollapsibleTrigger variant="ghost" size="sm" className="agents-wrap-trigger">{r.name}</CollapsibleTrigger></div>
                      <Text variant="caption">
                        {[r.instruction_name, fmt(r.created_at), r.articles_used ? `${r.articles_used} article${r.articles_used === 1 ? '' : 's'}` : null, r.model_used].filter(Boolean).join(' · ')}
                      </Text>
                    </Stack>
                    <Stack direction="row" gap="sm" wrap={false}>
                      <IconButton icon={<Icon name="DownloadSimple" size="sm" />} label={`Download “${r.name}” as Markdown`} disabled={!f || typeof f === 'string'} onClick={() => typeof f === 'object' && exportMd(f)} />
                      <IconButton tone="danger" icon={<Icon name="Trash" size="sm" />} label={`Delete “${r.name}”`} onClick={() => remove(r)} />
                    </Stack>
                  </Stack>
                  <CollapsibleContent>
                    {f === 'loading' || !f ? <Skeleton variant="text" lines={6} /> : f === 'failed' ? <Text tone="error">The report didn’t load.</Text> : (
                      <Stack gap="md">
                        {f.description && <Text variant="caption">{f.description}</Text>}
                        <Markdown text={f.report_content || 'This report has no text.'} />
                        {f.article_uris && f.article_uris.length > 0 && (
                          <Stack gap="sm">
                            <Text variant="label">{`Source articles (${f.article_uris.length})`}</Text>
                            <Stack direction="row" gap="sm">
                              {f.article_uris.slice(0, 10).map((u, i) => <TextLink key={u + i} href={u} external>{`Article ${i + 1}`}</TextLink>)}
                              {f.article_uris.length > 10 && <Text as="span" variant="caption">{`and ${f.article_uris.length - 10} more`}</Text>}
                            </Stack>
                          </Stack>
                        )}
                        <Stack direction="row" gap="sm">
                          <Button variant="secondary" size="sm" iconStart={<Icon name="DownloadSimple" size="sm" />} onClick={() => exportMd(f)}>Download as Markdown</Button>
                          <Button variant="secondary" size="sm" iconStart={<Icon name="FileText" size="sm" />} onClick={() => exportPdf(f)}>Download as PDF</Button>
                          <Button variant="secondary" size="sm" iconStart={<Icon name="SpeakerHigh" size="sm" />} onClick={() => setVoicing(f)}>
                            {audioIn(f.report_content) ? 'Listen' : 'Listen (AI voice, paid)'}
                          </Button>
                        </Stack>
                      </Stack>
                    )}
                  </CollapsibleContent>
                </Collapsible>
              </li>
            );
          })}
          {reports.length > shown && (
            <li><Button variant="ghost" size="sm" onClick={() => setShown((n) => n + PAGE)}>{`Show ${Math.min(PAGE, reports.length - shown)} more of ${reports.length - shown}`}</Button></li>
          )}
        </Stack>
      )}
      {voicing && (
        <VoiceDialog
          open
          onOpenChange={(o) => !o && setVoicing(null)}
          title={voicing.name}
          script={speakable(voicing.report_content || '')}
          audioUrl={audioIn(voicing.report_content)}
          notify={notify}
        />
      )}
    </Panel>
  );
}
