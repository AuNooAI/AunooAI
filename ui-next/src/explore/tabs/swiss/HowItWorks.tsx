import { useEffect } from 'react';
import { FlowDiagram, Grid, LineItems, Panel, Stack, Stat, Table, Text, TextLink, type ChartColor } from '@aunoo/ui';
import type { Flow, HowItWorks } from '@monolith/swissDisinfoApi';
import { Empty, LangChip, Loading, TierChip, when } from './bits';
import type { Swiss } from './useSwiss';

/** Colour by what a node is: outcome bands keep fixed colours, the rest share the neutral slots. */
const OUTCOME: Record<string, ChartColor> = {
  'In a storyline': 'negative', 'Analysed, no storyline': 'caution', 'Waiting to be analysed': 2, 'Never scored': 4,
  'Analysis failed': 'negative', 'Below the relevance line': 0,
};
const flowNodes = (f: Flow) => f.nodes.map((n) => ({ id: n.key, label: n.name, stage: n.stage, color: OUTCOME[n.name] ?? (((n.stage % 5) + 1) as ChartColor) }));

function Pipeline({ d, runs }: { d: HowItWorks; runs: (stage: string) => string }) {
  const s = d.settings;
  const news = d.keyword_groups.filter((g) => g.kind === 'news');
  const social = d.keyword_groups.filter((g) => g.kind === 'social');
  const liveFeeds = d.feeds.filter((f) => f.is_active);
  const steps: [string, string][] = [
    ['1. Collect', `${news.length} keyword ${news.length === 1 ? 'group queries' : 'groups query'} news providers, ${liveFeeds.length} RSS feeds are polled on their own schedule, and ${social.length} social ${social.length === 1 ? 'group reads' : 'groups read'} Bluesky and Telegram. A keyword is an AND of its words, so every term carries an anchor that ties it to this watch. Article text is searched as well as title and description (${s.search_fields ?? '–'}).`],
    ['2. Relevance check', `Each article is scored against this watch’s description. Below ${s.relevance_threshold ?? '0.40'} it is kept but marked rejected, so nothing is lost and the board isn’t flooded. Social posts are scored separately and reach the analysis at ${s.social_min_alignment} or above.`],
    ['3. Extraction', `One pass per article on ${runs('Extraction')}, returning the storylines it carries and the stance towards each (${s.stances.join(', ')}), what is targeted, who the article says is behind it, the technique, the language, and any fact-check or official response. What counts depends on the source: an outlet we class as state or alternative media pushing a line is itself the signal, while ordinary opinion in the mainstream press is not.`],
    ['4. Group into storylines', `A new statement is compared by meaning with this watch’s existing storylines, and the closest few (above ${s.narrative_shortlist_floor}) go to the model to decide whether it is the same storyline. Matching wording alone isn’t enough to merge, which is what lets one storyline be tracked across German, French, Italian and English.`],
    ['5. Alert and brief', `Four rules raise an alert: a new storyline on two outlets within two days, a week’s volume more than three times the week before, a first crossing into another language, and synthetic media aimed at a named person. The weekly brief is written on ${runs('Weekly brief')} from this data only.`],
  ];
  return (
    <Panel title="The pipeline" headingLevel={3}>
      <Stack as="ul" gap="md" label="Pipeline steps">
        {steps.map(([t, body]) => (
          <li key={t}><Stack gap="sm"><Text variant="label" as="span">{t}</Text><Text variant="description">{body}</Text></Stack></li>
        ))}
      </Stack>
    </Panel>
  );
}

export function HowItWorksPanel({ s }: { s: Swiss }) {
  const { loadHowItWorks } = s;
  useEffect(() => {
    loadHowItWorks();
  }, [loadHowItWorks]);
  const d = s.howItWorks;
  if (s.loading.how || !d) return <Loading />;
  const c = d.collection;
  const liveFeeds = d.feeds.filter((f) => f.is_active);
  const offFeeds = d.feeds.filter((f) => !f.is_active);
  const pct = (n: number, of: number) => (of ? `${Math.round((100 * n) / of)}%` : '–');
  // The configured aliases read like OpenAI models and none are, so show the model each stage really calls
  const runs = (stage: string) => d.models.find((m) => m.stage === stage)?.runs ?? '';
  const f = s.flow;

  return (
    <>
      <Panel title="What this watch does" headingLevel={3}>
        <Stack gap="sm">
          <Text>{d.blurb}</Text>
          <Text variant="description">Everything below is read from the running system each time this tab opens, so the source list shows what is collected right now.</Text>
        </Stack>
      </Panel>

      <Panel title="Collected so far" description={`Last collected ${when(c.last_collected)} · last analysed ${when(c.last_analysed)}`} headingLevel={3}>
        <Grid as="ul" columns={3} stackAt="small" gap="sm" label="Collected so far">
          <li><Stat size="compact" label="Collected" value={c.collected} meta="articles and posts, all time" /></li>
          <li><Stat size="compact" label="Kept" value={c.approved + c.social_kept} meta={`${c.approved} news, ${c.social_kept} social`} /></li>
          <li><Stat size="compact" label="Below the line" value={c.rejected} meta="kept on file, off the board" /></li>
          <li><Stat size="compact" label="Analysed" value={c.analysed} meta={c.analysis_failed ? `${c.analysis_failed} failed` : 'no failures'} /></li>
          <li><Stat size="compact" label="Storylines" value={c.narratives} meta={`${c.narrative_articles} article mentions`} /></li>
          <li><Stat size="compact" label="Never scored" value={c.unscored} meta={c.unscored ? 'collected, but the check never ran' : 'nothing stuck'} /></li>
        </Grid>
      </Panel>

      <Panel
        title="Where articles come from and what becomes of them"
        description={`Each article of the last ${f?.days_back ?? 30} days is counted once in every column.`}
        headingLevel={3}
      >
        {!f ? <Loading /> : !f.total ? <Empty>Nothing collected in this window.</Empty> : (
          <FlowDiagram title="Collection flow" stages={f.stages} nodes={flowNodes(f)} links={f.links} unit="articles" />
        )}
      </Panel>

      <Pipeline d={d} runs={runs} />

      <Panel title="Keyword groups" description="Each group has its own language, providers and terms." headingLevel={3}>
        <Table
          caption="Keyword groups"
          hideCaption
          rows={d.keyword_groups}
          rowKey={(g) => String(g.id)}
          columns={[
            { key: 'name', header: 'Group', rowHeader: true, render: (g) => `${g.name.replace(d.topic, '').replace(/^ - /, '').trim() || 'primary'}${g.is_active ? '' : ' (off)'}` },
            { key: 'language', header: 'Language', render: (g) => <LangChip lang={g.language} /> },
            { key: 'kind', header: 'Kind' },
            { key: 'providers', header: 'Providers', render: (g) => (g.providers || '').replace(/[[\]"]/g, '') || 'default' },
            { key: 'keywords', header: 'Terms', wrap: true, render: (g) => g.keywords.join(' · ') },
            { key: 'last_checked', header: 'Last run', render: (g) => when(g.last_checked) },
          ]}
        />
      </Panel>

      {d.telegram_channels.length > 0 && (
        <Panel title="Telegram channels" description="Public channel previews only. No account, no private channels." headingLevel={3}>
          <Stack as="ul" gap="sm" label="Telegram channels">
            {d.telegram_channels.map((ch) => (
              <li key={ch.channel}><Stack direction="row" gap="sm"><TextLink href={ch.url} external>@{ch.channel}</TextLink><TierChip tier={ch.tier} /></Stack></li>
            ))}
          </Stack>
        </Panel>
      )}

      <Panel title={`Feeds (${liveFeeds.length} live)`} description="Polled directly, separately from the keyword search." headingLevel={3}>
        <Stack gap="md">
          <Table
            caption="Feeds"
            hideCaption
            rows={liveFeeds}
            rowKey={(x) => String(x.id)}
            columns={[
              { key: 'name', header: 'Feed', rowHeader: true, render: (x) => <TextLink href={x.url} external>{x.name}</TextLink> },
              { key: 'tier', header: 'Type', render: (x) => <TierChip tier={x.tier} /> },
              { key: 'fetched', header: 'Fetched', align: 'end', render: (x) => x.fetched ?? 0 },
              { key: 'kept', header: 'Kept', align: 'end', render: (x) => `${x.produced.approved} of ${x.produced.articles} (${pct(x.produced.approved, x.produced.articles)})` },
              { key: 'last_checked', header: 'Last poll', render: (x) => when(x.last_checked) },
              { key: 'status', header: 'Status', render: (x) => (x.error ? <Text tone="error" as="span">{x.error.slice(0, 40)}</Text> : 'OK') },
            ]}
          />
          {offFeeds.length > 0 && <Text variant="caption">Switched off, kept for the record: {offFeeds.map((x) => x.name).join(' · ')}</Text>}
        </Stack>
      </Panel>

      <Panel
        title="What each source has produced"
        description="Everything the watch has collected, by outlet, with kept against total. Rows count by the article’s own domain, so an outlet reached two ways is still one row."
        headingLevel={3}
      >
        <LineItems label="Kept of collected, by source" items={d.produced_by_source.map((p) => ({ id: p.source, label: p.name, amount: `${p.approved} of ${p.articles}` }))} />
      </Panel>

      <Panel title="Models" description="Each stage is set by an alias. The aliases are old and read like OpenAI names, but every one runs on Bedrock." headingLevel={3}>
        <Table
          caption="Models"
          hideCaption
          rows={d.models}
          rowKey={(m) => m.stage}
          columns={[
            { key: 'stage', header: 'Stage', rowHeader: true },
            { key: 'runs', header: 'Runs on' },
            { key: 'alias', header: 'Configured as' },
            { key: 'note', header: 'What for', wrap: true },
          ]}
        />
      </Panel>

      <Panel title="Schedule" headingLevel={3}>
        <Stack gap="md">
          {d.schedules.length === 0 ? <Text>No schedule for this watch.</Text> : (
            <Stack as="ul" gap="sm" label="Schedules">
              {d.schedules.map((sc) => (
                <li key={sc.name}>
                  <Text>
                    <strong>{sc.name}</strong>: every {sc.every} on {runs('Extraction') || sc.model}, {sc.runs} runs so far, last {when(sc.last_run)} ({sc.status ?? '–'}), next {when(sc.next_run)}.
                    {!sc.enabled && ' Switched off.'}
                  </Text>
                </li>
              ))}
            </Stack>
          )}
          <Text variant="caption">
            Source types used: {d.settings.tiers.join(', ')}. Techniques recorded: {d.settings.techniques.filter((t) => t !== 'none_reported').join(', ')}. Attribution is always what the articles report, never a finding of this tool.
          </Text>
        </Stack>
      </Panel>
    </>
  );
}
