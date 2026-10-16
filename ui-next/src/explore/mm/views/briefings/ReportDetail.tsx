import { useEffect, useState } from 'react';
import { ActivityRow, Banner, Button, Chip, CodeBlock, Icon, Menu, Panel, SegmentedControl, Stack, Text, TextField } from '@aunoo/ui';
import {
  editBriefing, getBriefingRevision, getBriefingRevisions, restoreBriefingRevision,
  type BriefingDetail, type BriefingRevision,
} from '@monolith/marketMonitorApi';
import { api, ApiError, errorText } from '../../../../shell';
import { Markdown } from '../../../../shell/Markdown';
import { MarkdownEditor } from '../../../../anticipate/components/MarkdownEditor';
import { download } from '../../../feed/api';
import type { MmContext } from '../../context';
import { linkCitations, type CitationIndex } from './citations';

export const STATUS_TONE = { draft: 'muted', approved: 'success', rejected: 'error' } as const;

/**
 * One report or piece: the text, and the evidence it was written from. "Show the evidence" is how a
 * reader checks that a figure in the prose is real, so it stays one click away. Editing keeps every
 * earlier text in the history.
 */
export function ReportDetail({ report, ctx, topic, onChanged }: {
  report: BriefingDetail;
  ctx: Pick<MmContext, 'marketId' | 'notify' | 'askConfirm'>;
  topic: string;
  /** The report changed (edit, status or restore) */
  onChanged: (updated: BriefingDetail) => void;
}) {
  const { marketId, notify, askConfirm } = ctx;
  const [mode, setMode] = useState<'report' | 'evidence'>('report');
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [draftTitle, setDraftTitle] = useState('');
  const [saving, setSaving] = useState(false);
  const [history, setHistory] = useState<BriefingRevision[] | null>(null);
  const [preview, setPreview] = useState<{ id: number; content: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  // A different report starts fresh
  useEffect(() => {
    setMode('report');
    setEditing(false);
    setHistory(null);
    setPreview(null);
    setError(null);
  }, [report.id]);

  const citations = report.facts?.citation_index as CitationIndex | undefined;
  const isPiece = report.kind !== 'briefing';

  const startEdit = () => {
    setDraft(report.report_content || '');
    setDraftTitle(report.title || '');
    setEditing(true);
    setMode('report');
    setError(null);
  };
  const saveEdit = async () => {
    setSaving(true);
    setError(null);
    try {
      const updated = await editBriefing(marketId, report.id, { report_content: draft, title: draftTitle.trim() || null });
      setEditing(false);
      setHistory(null);
      onChanged(updated);
      notify(updated.status === 'approved' ? 'Saved. The feed item follows the new text.' : 'Saved. The previous text is kept in the history.');
    } catch (e) {
      setError(errorText(e));
    } finally {
      setSaving(false);
    }
  };

  const toggleHistory = async () => {
    if (history) {
      setHistory(null);
      setPreview(null);
      return;
    }
    try {
      setHistory((await getBriefingRevisions(marketId, report.id)).revisions);
    } catch (e) {
      setError(errorText(e));
    }
  };
  const showRevision = async (id: number) => {
    if (preview?.id === id) {
      setPreview(null);
      return;
    }
    try {
      const r = await getBriefingRevision(marketId, report.id, id);
      setPreview({ id, content: r.report_content });
    } catch (e) {
      setError(errorText(e));
    }
  };
  const restore = (r: BriefingRevision) =>
    askConfirm({
      title: 'Put this earlier text back?',
      message: `The text from ${r.saved_at.slice(0, 16).replace('T', ' ')} replaces the current one. The current text is kept in the history.`,
      action: 'Restore',
      onConfirm: () =>
        void restoreBriefingRevision(marketId, report.id, r.id).then(
          (updated) => {
            setHistory(null);
            setPreview(null);
            onChanged(updated);
            notify('Restored. The text that was there is kept in the history.');
          },
          (e) => setError(errorText(e)),
        ),
    });

  // Approving a piece re-checks its citations; the server refuses (409) when one isn't supported.
  // The old page stopped there; here the reader can approve anyway, which the server allows.
  const setStatus = async (status: 'approved' | 'rejected', override = false) => {
    try {
      await api(`/api/market-monitor/markets/${marketId}/briefings/${report.id}/status`, { method: 'PUT', json: { status, override } });
      onChanged({ ...report, status });
      notify(status === 'approved' ? 'Approved. It’s on the front page and in the feed.' : 'Rejected. It’s out of the feed.');
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && !override) {
        askConfirm({
          title: 'Approve despite the citation check?',
          message: errorText(e),
          action: 'Approve anyway',
          onConfirm: () => void setStatus(status, true),
        });
      } else setError(errorText(e));
    }
  };

  const name = report.title ?? report.period_label;
  const meta = [
    report.model_used,
    `${report.article_uris.length} sources`,
    isPiece ? `${report.kind === 'analysis' ? 'Analysis' : 'Note'}${report.author ? ` by ${report.author}` : ''}` : null,
    report.generation === 'edited' ? 'edited by hand' : null,
  ].filter(Boolean).join(' · ');

  return (
    <Panel
      title={name}
      description={meta}
      headingLevel={3}
      headerAside={
        <Stack direction="row" gap="sm">
          <Chip tone={STATUS_TONE[report.status]} size="sm">{report.status}</Chip>
          {report.status !== 'approved' && <Button size="sm" iconStart={<Icon name="CheckCircle" size="sm" />} onClick={() => void setStatus('approved')}>Approve</Button>}
          {report.status !== 'rejected' && <Button size="sm" variant="secondary" onClick={() => void setStatus('rejected')}>Reject</Button>}
          <Menu
            label="More actions"
            align="end"
            trigger={<Button size="sm" variant="ghost" iconEnd={<Icon name="CaretDown" size="sm" />}>More</Button>}
            items={[
              { id: 'edit', label: 'Edit', icon: 'PencilSimple', disabled: editing },
              { id: 'history', label: history ? 'Hide the history' : 'History', icon: 'ClockCounterClockwise', disabled: editing },
              { id: 'download', label: 'Download (Markdown)', icon: 'DownloadSimple' },
            ]}
            onSelect={(id) => {
              if (id === 'edit') startEdit();
              else if (id === 'history') void toggleHistory();
              else download(`${name.replace(/[^\w-]+/g, '-')}.md`, report.report_content || '');
            }}
          />
        </Stack>
      }
    >
      <Stack gap="md">
        {report.generation === 'fallback' && (
          <Banner tone="warning" title="Evidence only" description="This is the assembled evidence, not a written report. Either the period was too quiet to write about, or the model returned nothing usable." />
        )}
        {report.lint?.length > 0 && (
          <Banner tone="warning" title="Checks that flagged something" description={report.lint.map((l) => `${l.check}: ${l.detail}`).join(' · ')} />
        )}
        {error && <Banner tone="error" title="Something went wrong" description={error} />}

        {history && !editing && (
          <Stack gap="sm">
            <Text variant="label">History: every earlier text, newest first</Text>
            {history.length === 0 ? <Text variant="caption">No earlier text. This is the text as first written.</Text> : (
              <Stack as="ul" gap="sm" label="Earlier texts">
                {history.map((r) => (
                  <li key={r.id}>
                    <Stack direction="row" justify="between" gap="sm">
                      <ActivityRow
                        primary={`${r.reason}${r.saved_by ? ` by ${r.saved_by}` : ''}`}
                        secondary={`${r.generation ?? 'unknown'} · ${r.length.toLocaleString()} characters`}
                        timestamp={r.saved_at.slice(0, 16).replace('T', ' ')}
                        dateTime={r.saved_at}
                      />
                      <Stack direction="row" gap="sm">
                        <Button size="sm" variant="ghost" onClick={() => void showRevision(r.id)}>{preview?.id === r.id ? 'Hide' : 'View'}</Button>
                        <Button size="sm" variant="secondary" onClick={() => restore(r)}>Restore</Button>
                      </Stack>
                    </Stack>
                  </li>
                ))}
              </Stack>
            )}
            {preview && (
              <Panel title="Earlier text" headingLevel={4}>
                <Markdown text={linkCitations(preview.content, citations)} />
              </Panel>
            )}
          </Stack>
        )}

        {editing ? (
          <Stack gap="md">
            <TextField label="Title" maxLength={300} value={draftTitle} onChange={setDraftTitle} />
            <MarkdownEditor label="Text (Markdown; citations like [A3] stay linked to the evidence)" value={draft} onChange={setDraft} topic={topic} />
            <Text variant="hint">
              The previous text is kept and can be restored from History.{report.status === 'approved' ? ' This one is approved, so saving updates its feed item.' : ''}
            </Text>
            <Stack direction="row" gap="sm">
              <Button busy={saving} disabled={!draft.trim()} iconStart={<Icon name="Check" size="sm" />} onClick={() => void saveEdit()}>Save</Button>
              <Button variant="secondary" disabled={saving} onClick={() => setEditing(false)}>Cancel</Button>
            </Stack>
          </Stack>
        ) : (
          <>
            <SegmentedControl
              label="Show"
              options={[{ value: 'report', label: 'The report', icon: 'FileText' }, { value: 'evidence', label: 'The evidence', icon: 'Database' }]}
              value={mode}
              onValueChange={(v) => setMode(v as 'report' | 'evidence')}
            />
            {mode === 'evidence'
              ? <CodeBlock label="Facts the report was written from (JSON)" code={JSON.stringify(report.facts, null, 1)} />
              : <Markdown text={linkCitations(report.report_content || '', citations)} />}
          </>
        )}
      </Stack>
    </Panel>
  );
}
