import { useEffect, useState } from 'react';
import { Banner, Button, Checkbox, Dialog, DialogClose, Eyebrow, Skeleton, Stack, Text } from '@aunoo/ui';
import { getOfficialSourcesStatus, pollOfficialSourcesNow, updateBrandConfig, type BWBrandSources } from '@monolith/brandWatcherApi';
import { errorText } from '../../../shell';
import type { BwContext } from '../context';

/*
 * Official and scholarly sources per brand (SEC EDGAR, CourtListener, regulations.gov, Crossref,
 * OpenAlex), as the old modal: /api/brand-watcher/official-sources/status and poll-now, saved into
 * each brand's config.extra_sources.
 */
export function SourcesDialog({ open, onOpenChange, ctx }: { open: boolean; onOpenChange: (o: boolean) => void; ctx: BwContext }) {
  const [rows, setRows] = useState<BWBrandSources[] | null>(null);
  const [busy, setBusy] = useState<null | 'save' | 'poll'>(null);
  const [msg, setMsg] = useState<{ tone: 'info' | 'error'; text: string } | null>(null);

  useEffect(() => {
    if (!open) return;
    setRows(null);
    setMsg(null);
    getOfficialSourcesStatus().then(setRows, (e: unknown) => {
      setRows([]);
      setMsg({ tone: 'error', text: errorText(e) });
    });
  }, [open]);

  const toggle = (brandId: number, key: string) =>
    setRows((r) => r && r.map((b) => (b.brand_id !== brandId ? b : { ...b, sources: b.sources.map((s) => (s.key !== key ? s : { ...s, enabled: !s.enabled })) })));

  const save = async () => {
    if (!rows) return;
    setBusy('save');
    try {
      for (const b of rows) await updateBrandConfig(b.brand_id, { extra_sources: b.sources.filter((s) => s.enabled).map((s) => s.key) });
      ctx.notify('Source settings saved');
      onOpenChange(false);
    } catch (e) {
      setMsg({ tone: 'error', text: `Not saved: ${errorText(e)}` });
    } finally {
      setBusy(null);
    }
  };

  const poll = async () => {
    setBusy('poll');
    setMsg(null);
    try {
      const r = await pollOfficialSourcesNow();
      setMsg({ tone: 'info', text: `Checked ${r.polled} sources: ${r.new_articles} new records, ${r.risk_flagged} flagged as a risk${r.errors ? `, ${r.errors} errors` : ''}.` });
      getOfficialSourcesStatus().then(setRows, () => undefined);
    } catch (e) {
      setMsg({ tone: 'error', text: `Check failed: ${errorText(e)}` });
    } finally {
      setBusy(null);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Official and scholarly sources"
      description="Records fetched straight from the source for each brand. Filings, court opinions and regulatory dockets match the company by name even when the news doesn’t mention them."
      footer={
        <>
          <Button variant="ghost" size="lg" disabled={busy !== null || !rows} onClick={() => void poll()}>{busy === 'poll' ? 'Checking…' : 'Check sources now'}</Button>
          <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
          <Button size="lg" disabled={busy !== null || !rows} onClick={() => void save()}>{busy === 'save' ? 'Saving…' : 'Save'}</Button>
        </>
      }
    >
      <Stack gap="lg">
        <Text variant="caption">Switched-on sources are checked once a day. New records arrive as articles, and adverse findings are screened for risk automatically.</Text>
        {msg && <Banner tone={msg.tone} title={msg.tone === 'error' ? 'Something went wrong' : 'Done'} description={msg.text} />}
        {!rows ? <Skeleton variant="text" lines={6} /> : rows.length === 0 ? <Text>No brands to set up.</Text> : rows.map((b) => (
          <Stack key={b.brand_id} gap="sm">
            <Eyebrow as="h3">{b.display_name}</Eyebrow>
            {b.sources.map((s) => (
              <Stack key={s.key} gap="sm">
                <Checkbox
                  label={`${s.label}${s.article_count > 0 ? ` (${s.article_count} records so far)` : ''}`}
                  checked={s.enabled}
                  disabled={!s.available}
                  onCheckedChange={() => toggle(b.brand_id, s.key)}
                />
                <Text variant="caption">
                  {s.description}
                  {!s.available && s.requires_key ? ` Needs ${s.requires_key} set on the server.` : ''}
                  {s.available && s.last_polled_at ? ` Last checked ${new Date(s.last_polled_at).toLocaleDateString('en-GB')}.` : ''}
                </Text>
              </Stack>
            ))}
          </Stack>
        ))}
      </Stack>
    </Dialog>
  );
}
