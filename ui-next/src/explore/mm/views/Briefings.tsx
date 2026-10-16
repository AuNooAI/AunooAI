import { useCallback, useEffect, useMemo, useState } from 'react';
import { Banner, Button, EmptyState, Grid, Icon, NotificationItem, Panel, SegmentedControl, Select, Skeleton, Stack, Text } from '@aunoo/ui';
import { generateBriefing, getBriefing, getBriefings, type BriefingDetail, type BriefingSummary } from '@monolith/marketMonitorApi';
import { errorText } from '../../../shell';
import type { MmContext } from '../context';
import { periodOptions, PERIOD_KINDS, type PeriodKind } from './briefings/periods';
import { PieceDialog } from './briefings/PieceDialog';
import { ReportDetail } from './briefings/ReportDetail';

/*
 * Reports: generated, versioned market reports, plus pieces people write, as the old
 * MarketBriefingsView.tsx on /api/market-monitor/markets/{id}/briefings. A report is facts assembled
 * from stored records with model prose on top, so the reader gets both the text and the evidence.
 * The API still says "briefing"; the page says "report". Writing a report calls the AI, so it only
 * runs from the Generate button.
 */
export function Briefings(ctx: MmContext) {
  const { marketId, plan, notify, askConfirm } = ctx;
  const topic = plan?.topic_name ?? '';
  const [list, setList] = useState<BriefingSummary[] | null>(null);
  const [open, setOpen] = useState<BriefingDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [writing, setWriting] = useState(false);
  const [kind, setKind] = useState<PeriodKind>('month');
  const options = useMemo(() => periodOptions(kind), [kind]);
  const [refDate, setRefDate] = useState(options[0].refDate);
  // A new kind invalidates the old date (a first-of-month isn't a week's Monday)
  useEffect(() => setRefDate(periodOptions(kind)[0].refDate), [kind]);

  const reload = useCallback(() => {
    getBriefings(marketId).then((r) => setList(r.briefings), (e) => setError(errorText(e)));
  }, [marketId]);
  useEffect(() => {
    setOpen(null);
    setList(null);
    reload();
  }, [reload]);

  const openReport = async (id: number) => {
    try {
      setOpen(await getBriefing(marketId, id));
    } catch (e) {
      setError(errorText(e));
    }
  };

  const write = async () => {
    setBusy(true);
    setNote(null);
    try {
      const r = await generateBriefing(marketId, { periodKind: kind, refDate });
      setNote(
        r.generation === 'fallback'
          ? `${r.period_label}: ${r.item_count} items, too few to write from, or the model returned nothing. The stored report is the evidence itself.`
          : `${r.period_label} written from ${r.item_count} items.`,
      );
      reload();
      if (r.id) void openReport(r.id);
    } catch (e) {
      setNote(`Couldn’t write it: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };
  // Writing a period that already has a report replaces its text and takes it back to draft (out of
  // the feed). The server keeps no copy of the replaced text, so ask first. The old page didn't.
  const option = options.find((o) => o.refDate === refDate) ?? options[0];
  const existing = list?.find((b) => b.kind === 'briefing' && b.period_start?.slice(0, 10) === option.start);
  const generate = () => {
    if (!existing) return void write();
    askConfirm({
      title: `Rewrite the report for ${existing.period_label}?`,
      message: `${existing.period_label} already has a report (${existing.status}${existing.generation === 'edited' ? ', edited by hand' : ''}). Writing it again replaces that text, which isn’t kept in the history, and puts it back to draft, so it leaves the front page and the feed until someone approves it.`,
      action: 'Rewrite',
      onConfirm: () => void write(),
    });
  };

  const changed = (updated: BriefingDetail) => {
    setOpen(updated);
    setList((prev) => prev?.map((b) => (b.id === updated.id ? { ...b, title: updated.title, status: updated.status, generation: updated.generation, updated_at: updated.updated_at } : b)) ?? prev);
  };

  if (error) return <Banner tone="error" title="Reports didn’t load" description={error} action={<Button variant="secondary" size="sm" onClick={() => { setError(null); reload(); }}>Try again</Button>} />;

  return (
    <>
      <Panel
        title="Reports"
        description="One report per period (day, week, month or year), written from that period’s announcements, coverage, hiring and headcount readings. The figures come from stored records first and the text is written around them, so no number in a report is one the model made up. Claims drawn from one specific fact carry a citation, listed under References at the end."
        headerAside={<Button variant="secondary" iconStart={<Icon name="NotePencil" size="sm" />} onClick={() => setWriting(true)}>Write a piece</Button>}
      >
        <Stack gap="md">
          <Stack direction="row" gap="sm">
            <SegmentedControl label="Period length" options={PERIOD_KINDS} value={kind} onValueChange={(v) => setKind(v as PeriodKind)} />
            <Select label="Period" hideLabel icon="CalendarBlank" options={options.map((o) => ({ value: o.refDate, label: o.label }))} value={refDate} onValueChange={setRefDate} />
            <Button iconStart={<Icon name="Sparkle" size="sm" />} busy={busy} disabled={busy || list === null} onClick={generate}>
              {existing ? 'Rewrite report' : 'Generate report'}
            </Button>
          </Stack>
          <Text variant="hint">Generating writes the report with the AI. Only complete periods are offered.</Text>
          {note && <Banner tone="info" title="Report" description={note} />}
        </Stack>
      </Panel>

      <Grid columns="main-aside">
        {open ? (
          <ReportDetail report={open} ctx={{ marketId, notify, askConfirm }} topic={topic} onChanged={changed} />
        ) : (
          <Panel title="Report" headingLevel={3}>
            <EmptyState icon="FileText" title="Pick a report">Choose one from the list to read it, check its evidence, edit it or approve it.</EmptyState>
          </Panel>
        )}
        <Panel title="Reports and pieces" headingLevel={3}>
          {list === null ? <Skeleton variant="text" lines={6} /> : list.length === 0 ? <Text>None yet.</Text> : (
            <Stack as="ul" gap="sm" label="Reports and pieces">
              {list.map((b) => (
                <NotificationItem
                  key={b.id}
                  as="li"
                  headingLevel={4}
                  title={b.kind === 'briefing' ? b.period_label : b.title ?? b.period_label}
                  description={`${b.status} · ${b.kind === 'briefing' ? `${b.sources ?? 0} sources${b.generation === 'fallback' ? ', evidence only' : ''}` : `${b.kind === 'analysis' ? 'Analysis' : 'Note'}${b.author ? ` by ${b.author}` : ''}`}`}
                  unread={open?.id === b.id}
                  onOpen={() => void openReport(b.id)}
                  openLabel={`Open ${b.kind === 'briefing' ? b.period_label : b.title ?? b.period_label}`}
                  />
              ))}
            </Stack>
          )}
        </Panel>
      </Grid>

      <PieceDialog
        open={writing}
        onOpenChange={setWriting}
        marketId={marketId}
        topic={topic}
        onSaved={(row) => {
          notify('Saved as a draft. Approve it to publish it on the front page and in the feed.');
          reload();
          setOpen(row);
        }}
      />
    </>
  );
}
