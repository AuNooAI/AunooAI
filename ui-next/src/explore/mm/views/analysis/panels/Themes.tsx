import '../../../shared/mm.css';
import { useEffect, useState } from 'react';
import { Banner, Button, Collapsible, CollapsibleContent, CollapsibleTrigger, Icon, Panel, SegmentedControl, Select, Skeleton, Stack, Text, TextLink } from '@aunoo/ui';
import { getThemes, type MarketThemes } from '@monolith/marketMonitorApi';
import { errorText } from '../../../../../shell';
import { Markdown } from '../../../../../shell/Markdown';
import type { MmContext } from '../../../context';

/*
 * What the matched coverage is actually about, as the old MarketThemesPanel. Grouping is k-means
 * over stored embeddings and costs nothing. Describing the groups is a model call, so it stays
 * behind a button.
 */
export function Themes({ ctx }: { ctx: MmContext }) {
  const [scope, setScope] = useState<'all' | 'vendor'>('all');
  const [days, setDays] = useState(30);
  const [data, setData] = useState<MarketThemes | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [narrating, setNarrating] = useState(false);

  useEffect(() => {
    let live = true;
    setData(null);
    setError(null);
    getThemes(ctx.marketId, { scope, days }).then((d) => live && setData(d), (e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, [ctx.marketId, scope, days]);

  const narrate = async () => {
    setNarrating(true);
    try {
      setData(await getThemes(ctx.marketId, { scope, days, narrate: true }));
    } catch (e) {
      ctx.notify(`No description written: ${errorText(e)}`);
    } finally {
      setNarrating(false);
    }
  };

  return (
    <Panel
      title="Themes"
      description={
        scope === 'vendor'
          ? 'What vendors post about themselves, grouped by similarity: their own claims, not other people’s coverage of them.'
          : 'What the market’s whole matched coverage is about, grouped by similarity.'
      }
      headerAside={
        <Stack direction="row" gap="sm">
          <SegmentedControl label="Whose coverage" options={[{ value: 'all', label: 'The market' }, { value: 'vendor', label: 'Competitors' }]} value={scope} onValueChange={(v) => setScope(v as 'all' | 'vendor')} />
          <Select label="Themes period" hideLabel icon="CalendarBlank" options={[{ value: '7', label: '7 days' }, { value: '30', label: '30 days' }, { value: '90', label: '90 days' }]} value={String(days)} onValueChange={(v) => setDays(Number(v))} />
        </Stack>
      }
    >
      <Stack gap="md">
        {error && <Banner tone="error" title="Themes didn’t load" description={error} />}
        {!error && !data && <Skeleton variant="text" lines={5} />}
        {data && data.clusters.length === 0 && <Text>{data.reason ?? 'Nothing matched in this period.'}</Text>}
        {data && data.clusters.length > 0 && (
          <>
            <Stack direction="row" gap="sm">
              <Button variant="secondary" size="sm" iconStart={<Icon name="Sparkle" size="sm" />} disabled={narrating} onClick={() => void narrate()}>
                {narrating ? 'Writing…' : data.narrative ? 'Describe again with AI' : 'Describe the themes with AI'}
              </Button>
              <Text variant="caption">{`${data.n} articles in ${data.k} theme${data.k === 1 ? '' : 's'}`}</Text>
            </Stack>
            {data.narrative && <Markdown text={data.narrative} />}
            <Stack gap="sm">
              {data.clusters.map((c) => (
                <Collapsible key={c.id}>
                  <CollapsibleTrigger variant="ghost" size="sm" className="mm-wrap-trigger">
                    {`${c.sample[0]?.title ?? `Theme ${c.id}`} · ${c.size} articles${c.top_vendors.length ? ` · ${c.top_vendors.slice(0, 3).map((v) => v.vendor).join(', ')}` : ''}`}
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <Stack as="ul" gap="sm" label={`Examples from theme ${c.id}`}>
                      {c.sample.map((s) => (
                        <li key={s.uri}>
                          <TextLink href={s.uri} external>{s.title}</TextLink>
                          <Text as="span" variant="caption">{` · ${s.source ?? (scope === 'vendor' ? 'vendor post' : 'unknown source')} · ${(s.published ?? '').slice(0, 10)}`}</Text>
                        </li>
                      ))}
                    </Stack>
                  </CollapsibleContent>
                </Collapsible>
              ))}
            </Stack>
          </>
        )}
      </Stack>
    </Panel>
  );
}
