import { useEffect, useState } from 'react';
import { ReportSections } from '../../common/ReportSections';
import { downloadPdf } from '../../../shared/exports';
import { Banner, Button, EmptyState, Grid, Icon, IconButton, Menu, Panel, Skeleton, Stack, Text } from '@aunoo/ui';
import { errorText } from '../../../../shell';
import { download } from '../../../feed/api';
import { deleteNarrative, generateNarrative, getNarratives, type Narrative } from '../api';
import type { ThreatCtx } from '../context';
import { fmtDateTime } from '../labels';
import { LinkButton } from '../parts';

/*
 * AI-written threat briefings, as the old ThreatInsightsTab. Each covers the seven days before it was
 * written. Writing one calls the AI, so it's a button that says so first; the old page started at once.
 * Download as PDF or Markdown.
 */

const textOf = (n: Narrative) => n.narrative_text || n.executive_summary || '';
const fileName = (n: Narrative) => `threat-briefing-${(n.generated_at ?? '').slice(0, 10) || n.id}.md`;

export function Insights(ctx: ThreatCtx) {
  const [list, setList] = useState<Narrative[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<number | null>(null);
  const [writing, setWriting] = useState(false);

  useEffect(() => {
    let live = true;
    getNarratives().then((r) => {
      if (!live) return;
      setList(r.data);
      setPicked((p) => p ?? r.data[0]?.id ?? null);
    }, (e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, []);

  const write = () =>
    ctx.askConfirm({
      title: 'Write a new threat briefing?',
      message: `The AI (${ctx.model}) reads the threats, actors and articles filed over the last seven days and writes a briefing with recommendations. It takes a minute or two.`,
      action: 'Write the briefing',
      onConfirm: async () => {
        setWriting(true);
        try {
          const n = await generateNarrative(ctx.model);
          setList((l) => [n, ...(l ?? [])]);
          setPicked(n.id);
          ctx.notify('Briefing written');
        } catch (e) {
          ctx.notify(`The briefing wasn’t written: ${errorText(e)}`);
        } finally {
          setWriting(false);
        }
      },
    });

  const remove = (n: Narrative) =>
    ctx.askConfirm({
      title: 'Delete this briefing?',
      message: `The briefing from ${fmtDateTime(n.generated_at)} is removed for everyone. It can’t be brought back, only written again.`,
      action: 'Delete',
      onConfirm: async () => {
        try {
          await deleteNarrative(n.id);
          setList((l) => {
            const next = (l ?? []).filter((x) => x.id !== n.id);
            setPicked((p) => (p === n.id ? next[0]?.id ?? null : p));
            return next;
          });
          ctx.notify('Briefing deleted');
        } catch (e) {
          ctx.notify(`Not deleted: ${errorText(e)}`);
        }
      },
    });

  if (error) return <Banner tone="error" title="Briefings didn’t load" description={error} />;
  if (!list) return <Skeleton variant="block" size="card" />;
  const sel = list.find((n) => n.id === picked) ?? null;
  const savePdf = async (n: Narrative) => {
    try {
      await downloadPdf({
        filename: fileName(n).replace(/\.md$/, '.pdf'),
        title: 'Weekly threat briefing',
        subtitle: `Written ${fmtDateTime(n.generated_at)}${n.model_used ? ` by ${n.model_used}` : ''} · ${n.threat_count ?? 0} threats, ${n.article_count ?? 0} articles`,
        markdown: textOf(n),
      });
    } catch (e) {
      ctx.notify(`The PDF wasn’t saved: ${errorText(e)}`);
    }
  };

  return (
    <Grid columns="main-aside">
      <Panel
        title={sel ? 'Weekly threat briefing' : 'Threat briefing'}
        description={sel ? `Written ${fmtDateTime(sel.generated_at)}${sel.model_used ? ` by ${sel.model_used}` : ''} · ${sel.threat_count ?? 0} threats, ${sel.article_count ?? 0} articles` : undefined}
        headerAside={sel ? (
          <Stack direction="row" gap="sm">
            <Menu
              label="Download this briefing"
              align="end"
              trigger={<IconButton icon={<Icon name="DownloadSimple" size="sm" />} label="Download this briefing" />}
              items={[{ id: 'pdf', label: 'As PDF', icon: 'FileText' }, { id: 'md', label: 'As Markdown', icon: 'FileText' }]}
              onSelect={(id) => (id === 'md' ? download(fileName(sel), textOf(sel)) : void savePdf(sel))}
            />
            <IconButton tone="danger" icon={<Icon name="Trash" size="sm" />} label="Delete this briefing" onClick={() => remove(sel)} />
          </Stack>
        ) : undefined}
      >
        {!sel ? (
          <EmptyState icon="Sparkle" title="No briefing open">Write a briefing, or pick one from the list.</EmptyState>
        ) : textOf(sel) ? <ReportSections idPrefix="threat-briefing" markdown={textOf(sel)} /> : <Text>This briefing has no text.</Text>}
      </Panel>
      <Panel
        title="Briefings"
        description={`${list.length} written`}
        headerAside={<Button size="sm" iconStart={<Icon name="Sparkle" size="sm" />} disabled={writing} onClick={write}>{writing ? 'Writing…' : 'Write new'}</Button>}
      >
        {!list.length ? <Text variant="caption">None yet. “Write new” has the AI write one from the last seven days.</Text> : (
          <ul className="threat-plainlist">
            {list.map((n) => (
              <li key={n.id}>
                <Stack gap="sm">
                  <LinkButton onClick={() => setPicked(n.id)} label={`Open the briefing from ${fmtDateTime(n.generated_at)}`}>{fmtDateTime(n.generated_at)}</LinkButton>
                  <Text variant="caption">{`${n.threat_count ?? 0} threats · ${n.top_actors?.length ?? 0} actors${n.id === picked ? ' · open' : ''}`}</Text>
                </Stack>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </Grid>
  );
}
