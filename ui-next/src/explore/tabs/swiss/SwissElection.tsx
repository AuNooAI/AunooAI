import { useEffect, useState } from 'react';
import {
  ArticleCard, Banner, Button, Chip, Grid, Icon, LineItems, Pagination, Panel, Select, Stack, StackedBarChart, StackedBars, Stat, TabPanel, Tabs, Text,
  type SelectOption,
} from '@aunoo/ui';
import { CalendarPanel, InsightsPanel, LanguagesPanel, NarrativesPanel, ResponsesPanel, SourcesPanel, TargetsPanel } from './panels';
import { HowItWorksPanel } from './HowItWorks';
import { Empty, LangChip, Loading, StanceChip, TIER_LABEL, TierChip, label } from './bits';
import { useSwiss, type Swiss } from './useSwiss';

/*
 * Swiss Election Watch on the routes the old tab uses (/api/swiss-disinfo, see
 * ui/src/components/newsfeed/SwissDisinfoTab.tsx). "Analyse new" and "Generate weekly brief"
 * call the AI; everything else reads stored results.
 */

const SUBTABS = [
  { value: 'overview', label: 'Overview' },
  { value: 'narratives', label: 'Narratives' },
  { value: 'sources', label: 'Sources' },
  { value: 'targets', label: 'Targets' },
  { value: 'languages', label: 'Languages' },
  { value: 'calendar', label: 'Calendar' },
  { value: 'responses', label: 'Responses' },
  { value: 'insights', label: 'Insights' },
  { value: 'articles', label: 'Articles' },
  { value: 'how', label: 'How it works' },
];

const WINDOWS: SelectOption[] = [
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
  { value: '365', label: 'Last year' },
];

type Notify = (message: string) => void;

function ProcessButton({ s }: { s: Swiss }) {
  const p = s.processStatus;
  const running = !!p?.running;
  return (
    <Button
      iconStart={<Icon name={running ? 'ArrowsClockwise' : 'Play'} size="sm" />}
      disabled={running || !s.unprocessed}
      onClick={() => void s.process(false)}
    >
      {running ? `Analysing ${p?.processed ?? 0} of ${p?.total ?? 0}` : `Analyse ${s.unprocessed ?? '…'} new`}
    </Button>
  );
}

function OverviewPanel({ s }: { s: Swiss }) {
  const o = s.overview;
  if (s.loading.overview && !o) return <Loading />;
  if (!o) return <Empty>No data yet.</Empty>;
  const delta = o.approved - o.approved_prev;
  return (
    <>
      <Grid as="ul" columns={4} stackAt="small" gap="sm" label="This week">
        <li><Stat surface="panel" label="Narratives active, 7 days" value={o.narratives_active} meta={`${o.narratives_new} first seen this week`} tone="error" /></li>
        <li><Stat surface="panel" label="Articles passed the relevance check, 7 days" value={o.approved} meta={`${delta >= 0 ? '+' : ''}${delta} on the previous 7 days · ${o.rejected} rejected`} tone="info" /></li>
        <li><Stat surface="panel" label="Share from state or alternative media" value={`${Math.round(o.vector_share * 100)}%`} meta={`of ${o.extracted} analysed articles`} tone="warning" /></li>
        <li><Stat surface="panel" label={o.next_vote ? 'Days to the next federal vote' : 'Next vote'} value={o.next_vote ? o.next_vote.days_to : '–'} meta={o.next_vote?.label} tone="success" /></li>
      </Grid>

      {o.approved < 5 && (
        <Banner
          tone="info"
          title="A quiet week"
          description={`${o.sources_scanned} sources scanned, ${o.approved + o.rejected} articles checked, ${o.approved} kept. Silence here means nothing was found, not that collection stopped.`}
        />
      )}

      <Grid columns="main-aside" gap="md">
        <Panel title="Narrative articles by day and stance" headingLevel={3}>
          {o.stance_series.length === 0 ? (
            <Empty>Nothing analysed in the last 7 days. Use “Analyse new” above.</Empty>
          ) : (
            <StackedBarChart
              title="Narrative articles by day and stance"
              categories={o.stance_series.map((d) => d.day)}
              series={[
                { id: 'promotes', label: 'Promotes', color: 1, values: o.stance_series.map((d) => d.promotes) },
                { id: 'reports', label: 'Reports', color: 2, values: o.stance_series.map((d) => d.reports) },
                { id: 'debunks', label: 'Debunks', color: 3, values: o.stance_series.map((d) => d.debunks) },
              ]}
            />
          )}
        </Panel>
        <Panel title="Attribution, as reported" description="What the articles say is behind it. Not a finding of this tool." headingLevel={3}>
          {o.attribution.length === 0 ? <Text>None reported.</Text> : (
            <LineItems label="Attribution, as reported" items={o.attribution.map((a) => ({ id: a.actor, label: a.actor, amount: a.count }))} />
          )}
        </Panel>
      </Grid>

      <Panel title="Categories of articles kept in the last 7 days" headingLevel={3}>
        <StackedBars
          title="Categories of articles kept in the last 7 days"
          series={[{ id: 'count', label: 'Articles', color: 2 }]}
          rows={o.categories.map((c) => ({ id: c.category, label: c.category, values: [c.count] }))}
          emptyText="None in this window."
        />
      </Panel>
    </>
  );
}

const any = (v: string) => (v === 'any' ? undefined : v);
const opts = (all: string, values: [string, string][]): SelectOption[] => [{ value: 'any', label: all }, ...values.map(([value, l]) => ({ value, label: l }))];
const LANG_OPTS = opts('All languages', [['de', 'German'], ['fr', 'French'], ['it', 'Italian'], ['en', 'English']]);
const TIER_OPTS = opts('All source types', Object.entries(TIER_LABEL));
const ATTR_OPTS = opts('Any attribution', ['russia', 'china', 'other_state', 'domestic', 'unattributed'].map((t) => [t, label(t)]));
const TECH_OPTS = opts('Any technique', ['deepfake', 'synthetic_text', 'bot_amplification', 'fake_account', 'forged_document', 'doctored_quote', 'decontextualised_media', 'astroturfing', 'state_media_placement'].map((t) => [t, label(t)]));

function ArticlesPanel({ s }: { s: Swiss }) {
  const f = s.articleFilters;
  const { loadArticles } = s;
  useEffect(() => {
    void loadArticles({ page: 1 });
  }, [loadArticles]);
  const set = (patch: Partial<typeof f>) => void loadArticles({ ...f, ...patch, page: patch.page ?? 1 });
  const a = s.articles;
  const pages = a ? Math.max(1, Math.ceil(a.total / a.per_page)) : 1;
  return (
    <Panel title="Articles" description={a ? `${a.total} articles in the last ${s.daysBack} days` : undefined} headingLevel={3}>
      <Stack gap="md">
        <Stack direction="row" gap="sm" label="Article filters">
          <Select label="Language" hideLabel options={LANG_OPTS} value={f.language ?? 'any'} onValueChange={(v) => set({ language: any(v) })} />
          <Select label="Source type" hideLabel options={TIER_OPTS} value={f.tier ?? 'any'} onValueChange={(v) => set({ tier: any(v) })} />
          <Select label="Attribution" hideLabel options={ATTR_OPTS} value={f.attribution ?? 'any'} onValueChange={(v) => set({ attribution: any(v) })} />
          <Select label="Technique" hideLabel options={TECH_OPTS} value={f.technique ?? 'any'} onValueChange={(v) => set({ technique: any(v) })} />
        </Stack>
        {s.loading.articles && !a ? <Loading /> : !a || a.articles.length === 0 ? <Empty>No articles match.</Empty> : (
          <>
            <Stack as="ul" gap="sm" label="Articles">
              {a.articles.map((art) => (
                <ArticleCard
                  key={art.uri}
                  as="li"
                  variant="row"
                  headingLevel={4}
                  href={art.url ?? undefined}
                  meta={[art.news_source, (art.publication_date || art.submission_date || '').slice(0, 10)].filter(Boolean).join(' · ')}
                  title={art.title}
                  summary={
                    art.narratives?.length ? (
                      <Stack as="ul" gap="sm" label="Narratives in this article">
                        {art.narratives.map((n, i) => (
                          <li key={i}><Stack direction="row" gap="sm" wrap={false}><StanceChip stance={n.stance} /><Text variant="description" as="span">{n.statement}</Text></Stack></li>
                        ))}
                      </Stack>
                    ) : undefined
                  }
                  tags={
                    <>
                      <LangChip lang={art.language} />
                      <TierChip tier={art.source_tier} />
                      {art.attribution && art.attribution !== 'unattributed' && <Chip size="sm" tone="muted">As reported: {label(art.attribution)}</Chip>}
                      {art.techniques.filter((t) => t !== 'none_reported').map((t) => <Chip key={t} size="sm" tone="warning">{label(t)}</Chip>)}
                      {art.topic_alignment_score != null && <Chip size="sm" tone="muted">Relevance {art.topic_alignment_score.toFixed(2)}</Chip>}
                      {!art.extracted_at && <Chip size="sm" tone="muted">Not analysed yet</Chip>}
                    </>
                  }
                  footer={art.targets?.length ? <span>Targets: {art.targets.map((t) => t.name).join(', ')}</span> : undefined}
                />
              ))}
            </Stack>
            {pages > 1 && <Pagination label="Article pages" page={a.page} pageCount={pages} onPageChange={(page) => set({ page })} />}
          </>
        )}
      </Stack>
    </Panel>
  );
}

export function SwissElection({ notify }: { notify: Notify }) {
  const s = useSwiss();
  const [tab, setTab] = useState('overview');
  const current = s.scopes.find((sc) => sc.topic === (s.topic ?? s.scopes[0]?.topic));

  useEffect(() => {
    if (s.error) {
      notify(s.error);
      s.clearError();
    }
  }, [s.error, s, notify]);

  return (
    <>
      <Panel
        title={current?.label ?? 'Swiss Election Watch'}
        description={current?.blurb ?? 'Disinformation and influence operations aimed at Swiss voters: the 2027 federal elections and the votes before them.'}
        headerAside={
          <Stack direction="row" gap="sm">
            {s.scopes.length > 1 && (
              <Select
                label="Watch"
                hideLabel
                options={s.scopes.map((sc) => ({ value: sc.topic, label: sc.label }))}
                value={s.topic ?? s.scopes[0].topic}
                onValueChange={s.setTopic}
              />
            )}
            <Select label="Window" hideLabel icon="CalendarBlank" options={WINDOWS} value={String(s.daysBack)} onValueChange={(v) => s.setDaysBack(Number(v))} />
            <ProcessButton s={s} />
          </Stack>
        }
      />
      <Tabs label="Election watch sections" scrollable value={tab} onValueChange={setTab} items={SUBTABS}>
        {SUBTABS.map((t) => (
          <TabPanel key={t.value} value={t.value}>
            {t.value === tab && (
              <Stack gap="lg">
                {tab === 'overview' && <OverviewPanel s={s} />}
                {tab === 'narratives' && <NarrativesPanel s={s} />}
                {tab === 'sources' && <SourcesPanel s={s} />}
                {tab === 'targets' && <TargetsPanel s={s} />}
                {tab === 'languages' && <LanguagesPanel s={s} />}
                {tab === 'calendar' && <CalendarPanel s={s} />}
                {tab === 'responses' && <ResponsesPanel s={s} />}
                {tab === 'insights' && <InsightsPanel s={s} />}
                {tab === 'articles' && <ArticlesPanel s={s} />}
                {tab === 'how' && <HowItWorksPanel s={s} />}
              </Stack>
            )}
          </TabPanel>
        ))}
      </Tabs>
    </>
  );
}
