import { useCallback, useEffect, useState } from 'react';
import { Banner, Button, Chip, Icon, Panel, Stack, Text, TextField } from '@aunoo/ui';
import { getAnalystFeeds, putAnalystFeeds, type AnalystFeed } from '@monolith/marketMonitorApi';
import { errorText } from '../../../../shell';
import type { MmContext } from '../../context';

const host = (u: string) => {
  try {
    return new URL(u).host.replace(/^www\./, '');
  } catch {
    return u;
  }
};

/**
 * The analyst firms' public feeds read for a market (a firm's security blog, a research listing), as
 * the old MarketAnalystFeeds.tsx. The RSS monitor reads them hourly and keeps items that mention the
 * market; they appear under "Latest research" on the market's front page. Saving the list registers
 * new feeds with the feed reader straight away.
 */
export function AnalystFeeds({ marketId, askConfirm }: Pick<MmContext, 'marketId' | 'askConfirm'>) {
  const [feeds, setFeeds] = useState<AnalystFeed[] | null>(null);
  const [defaults, setDefaults] = useState(false);
  const [firm, setFirm] = useState('');
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ tone: 'info' | 'error'; text: string } | null>(null);

  const load = useCallback(() => {
    getAnalystFeeds(marketId).then((r) => {
      setFeeds(r.feeds);
      setDefaults(r.defaults);
    }, () => setFeeds([]));
  }, [marketId]);
  useEffect(load, [load]);

  const save = async (next: { firm: string; url: string }[], done: string) => {
    setBusy(true);
    setNote(null);
    try {
      const r = await putAnalystFeeds(marketId, next);
      setFeeds(r.feeds);
      setDefaults(false);
      setNote({ tone: 'info', text: `${done}${r.sync.added ? ` ${r.sync.added} registered with the feed reader.` : ''}` });
      return true;
    } catch (e) {
      setNote({ tone: 'error', text: `Not saved: ${errorText(e)}` });
      return false;
    } finally {
      setBusy(false);
    }
  };
  const plain = (list: AnalystFeed[]) => list.map((x) => ({ firm: x.firm, url: x.url }));
  const add = async () => {
    if (!firm.trim() || !url.trim()) return;
    if (await save([...plain(feeds ?? []), { firm: firm.trim(), url: url.trim() }], `Added ${firm.trim()}.`)) {
      setFirm('');
      setUrl('');
    }
  };
  const remove = (f: AnalystFeed) =>
    askConfirm({
      title: `Stop reading ${f.firm}?`,
      message: `${host(f.url)} won’t be read for this market any more. Items already kept stay.${defaults ? ' Saving this makes the list this market’s own instead of the defaults.' : ''}`,
      action: 'Stop reading',
      onConfirm: () => void save(plain((feeds ?? []).filter((x) => x.url !== f.url)), `Removed ${f.firm}.`),
    });

  return (
    <Panel
      title="Analyst feeds"
      headingLevel={3}
      description={`The firms’ public blogs and research listings. Read hourly; items that mention the market appear under Latest research on the front page.${defaults ? ' These are the defaults; saving a change makes the list this market’s own.' : ''}`}
    >
      <Stack gap="md">
        <Stack direction="row" gap="sm">
          {feeds === null ? <Text variant="caption">Loading…</Text> : feeds.length === 0 ? <Text variant="caption">None. Add a feed address below.</Text> : feeds.map((f) => (
            <Chip key={f.url} tone="neutral" icon={<Icon name="X" size="sm" />} label={`Stop reading ${f.firm} (${f.url})`} onClick={busy ? undefined : () => remove(f)}>
              {`${f.firm} · ${host(f.url)}`}
            </Chip>
          ))}
        </Stack>
        <Stack direction="row" gap="sm">
          <TextField label="Firm" hideLabel placeholder="Firm (e.g. Forrester)" maxLength={60} value={firm} onChange={setFirm} />
          <TextField label="Feed address" hideLabel type="url" placeholder="https://…/feed" maxLength={500} value={url} onChange={setUrl} onSubmit={() => void add()} />
          <Button iconStart={<Icon name="Plus" size="sm" />} disabled={busy || !firm.trim() || !url.trim()} onClick={() => void add()}>Add</Button>
        </Stack>
        {note && <Banner tone={note.tone} title={note.tone === 'error' ? 'Something went wrong' : 'Saved'} description={note.text} />}
      </Stack>
    </Panel>
  );
}
