import { useEffect, useMemo, useState } from 'react';
import { ArticleCard, Banner, Button, Chip, Icon, Panel, Skeleton, Stack, Text, TextLink } from '@aunoo/ui';
import { generateMarketTimeline, getMarketTimeline, getWireArticles, type TimelineEvent, type WireArticle } from '@monolith/marketMonitorApi';
import { errorText } from '../../../../shell';
import type { MmContext } from '../../context';
import { VendorLink } from '../../shared/SortTable';
import { SEVERITY_TONE } from './labels';

/**
 * One Wire event. Its articles load only when asked for: a count and a significance can't be
 * checked without seeing what they were computed from.
 */
function WireEvent({ event: e, ctx, vendorIds }: { event: TimelineEvent; ctx: MmContext; vendorIds: Map<string, number> }) {
  const [articles, setArticles] = useState<WireArticle[] | null>(null);
  const [failed, setFailed] = useState(false);
  const uris = e.article_uris ?? [];
  // The extractor names every company in the story. Tracked vendors become links; the rest
  // (a customer, an acquirer, a rival outside the registry) stay plain text.
  const named = Array.isArray(e.entities) ? (e.entities as unknown[]).filter((n): n is string => typeof n === 'string') : [];
  const tracked = named.filter((n) => vendorIds.has(n.toLowerCase()));
  const others = named.filter((n) => !vendorIds.has(n.toLowerCase()));

  const load = () => {
    if (articles !== null || !uris.length) return;
    getWireArticles(uris).then(setArticles, () => { setArticles([]); setFailed(true); });
  };

  const meta = `${e.event_date} · ${e.event_type}${e.event_subtype ? ` · ${e.event_subtype}` : ''} · ${e.article_count} article${e.article_count === 1 ? '' : 's'}${e.occurrence_count > 1 ? ` · seen ${e.occurrence_count} times` : ''}`;
  return (
    <ArticleCard
      as="li"
      variant="row"
      headingLevel={4}
      title={e.title}
      meta={meta}
      flag={<Chip size="sm" tone={SEVERITY_TONE[e.significance] ?? 'neutral'}>{e.significance}</Chip>}
      summary={e.description ?? undefined}
      tags={named.length > 0 ? (
        <Stack direction="row" gap="sm">
          {tracked.map((n) => <VendorLink key={n} id={vendorIds.get(n.toLowerCase())!} name={n} color={ctx.colours.byName(n)} onOpen={ctx.openVendor} />)}
          {others.length > 0 && <Text as="span" variant="caption">{`${tracked.length ? 'with ' : ''}${others.join(', ')}${tracked.length === 0 ? ' (not a tracked vendor)' : ''}`}</Text>}
        </Stack>
      ) : undefined}
      footer={uris.length ? undefined : 'No linked articles: this event was worked out from counts, not tied to specific articles.'}
      details={uris.length ? (
        articles === null ? (
          <Button variant="ghost" size="sm" onClick={load}>Load the articles behind this event</Button>
        ) : failed || articles.length === 0 ? (
          <Text variant="caption">These articles couldn’t be loaded.</Text>
        ) : (
          <Stack as="ul" gap="sm" label={`Articles behind ${e.title}`}>
            {articles.map((a) => (
              <li key={a.uri}>
                <Stack gap="sm">
                  <TextLink href={a.uri} external>{a.title}</TextLink>
                  <Stack direction="row" gap="sm">
                    <Text as="span" variant="caption">{`${a.news_source ?? 'unknown source'}${a.publication_date ? ` · ${a.publication_date.slice(0, 10)}` : ''}`}</Text>
                    {a.vendors.map((v) => <VendorLink key={v.brand_id} id={v.brand_id} name={v.vendor} color={ctx.colours.byId(v.brand_id)} onOpen={ctx.openVendor} />)}
                  </Stack>
                </Stack>
              </li>
            ))}
          </Stack>
        )
      ) : undefined}
    />
  );
}

/** Market-level events pulled out of collected articles, newest first, from the shared timeline */
export function Wire({ ctx }: { ctx: MmContext }) {
  const { plan, periodDays, vendors } = ctx;
  const topic = plan?.topic_name;
  const [events, setEvents] = useState<TimelineEvent[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);
  const [nonce, setNonce] = useState(0);
  const vendorIds = useMemo(() => new Map((vendors ?? []).map((v) => [v.display_name.toLowerCase(), v.brand_id])), [vendors]);

  useEffect(() => {
    if (!plan) return;
    // Always resolve to a list, so a missing topic doesn't leave a loader spinning
    if (!topic) {
      setEvents([]);
      return;
    }
    let live = true;
    setEvents(null);
    getMarketTimeline(topic, 50, periodDays).then((r) => live && setEvents(r.events), () => live && setEvents([]));
    return () => {
      live = false;
    };
  }, [plan, topic, periodDays, nonce]);

  const build = () => ctx.askConfirm({
    title: 'Build events from the last 7 days?',
    message: 'This reads the market’s articles from the last 7 days and pulls out events. The AI reads the two most recent days, so this costs some AI usage; older days are matched without it.',
    action: 'Build events',
    onConfirm: async () => {
      if (!topic) return;
      setBusy(true);
      setResult(null);
      try {
        const r = await generateMarketTimeline(topic, 7);
        setResult({ tone: 'success', text: `${r.events_created} events from ${r.articles_processed} articles (${r.events_deduplicated} merged into existing ones).` });
        setNonce((n) => n + 1);
      } catch (e) {
        setResult({ tone: 'error', text: `Not built: ${errorText(e)}` });
      } finally {
        setBusy(false);
      }
    },
  });

  return (
    <Panel
      title="Wire"
      description="Market-level events pulled out of collected articles, newest first: the 50 most recent within the period picked above, with no significance filter."
      headerAside={<Button size="sm" iconStart={<Icon name="Play" size="sm" />} busy={busy} disabled={busy || !topic} onClick={build}>Build from the last 7 days</Button>}
    >
      <Stack gap="md">
        {result && <Banner tone={result.tone} title={result.tone === 'error' ? 'Something went wrong' : 'Done'} description={result.text} />}
        {plan && !topic && <Text>This market has no collection topic yet, so there is no wire.</Text>}
        {events === null ? <Skeleton variant="text" lines={6} /> : events.length === 0 ? (
          topic ? <Text>No events in this period. Extraction runs daily for the previous full day.</Text> : null
        ) : (
          <>
            <Stack as="ul" gap="sm" label="Wire events">
              {events.map((e) => <WireEvent key={e.id} event={e} ctx={ctx} vendorIds={vendorIds} />)}
            </Stack>
            {events.length >= 50 && <Text variant="caption">Showing the 50 most recent events. Older ones can’t be reached from this list yet.</Text>}
          </>
        )}
      </Stack>
    </Panel>
  );
}
