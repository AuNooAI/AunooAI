import { useEffect, useMemo, useState } from 'react';
import {
  ActivityRow, Button, Chip, Eyebrow, Grid, Icon, LineChart, Panel, PanelDivider, Select, Stack, StackedBarChart, StackedBars, Stat, Table, Text, TextLink,
  type SelectOption,
} from '@aunoo/ui';
import { Markdown } from '../../../shell/Markdown';
import { TitleLink } from '../../feed/api';
import type { GlossaryEntry, Narrative, SourceRow, TargetRow } from '@monolith/swissDisinfoApi';
import { Empty, LANG_NAME, LANGS, LangChip, Loading, StanceChip, TIER_LABEL, TierChip, label, trend } from './bits';
import type { Swiss } from './useSwiss';

const LANG_SERIES = LANGS.map((l, i) => ({ id: l, label: LANG_NAME[l], color: (i + 1) as 1 | 2 | 3 | 4 }));
const niceMax = (n: number) => {
  if (n <= 5) return 5;
  const step = 10 ** Math.floor(Math.log10(n));
  return Math.ceil(n / step) * step;
};

// ---------------------------------------------------------------- Narratives

function NarrativeDetailView({ s, onBack }: { s: Swiss; onBack: () => void }) {
  const d = s.narrativeDetail!;
  const series = useMemo(() => {
    const byDay: Record<string, Record<string, number>> = {};
    for (const p of d.language_series) (byDay[p.day] ||= { de: 0, fr: 0, it: 0, en: 0 })[p.language] = p.count;
    return Object.entries(byDay).sort(([a], [b]) => a.localeCompare(b));
  }, [d]);
  return (
    <>
      <div>
        <Button variant="ghost" size="sm" iconStart={<Icon name="CaretLeft" size="sm" />} onClick={onBack}>All narratives</Button>
      </div>
      <Panel title={d.name} description={d.statement} headingLevel={3}>
        <Stack direction="row" gap="sm">
          <Chip size="sm" tone="muted">First seen {d.first_seen ?? '–'}</Chip>
          <Chip size="sm" tone="muted">Last seen {d.last_seen ?? '–'}</Chip>
          <Chip size="sm" tone="muted">{d.article_count} articles</Chip>
          <Chip size="sm" tone="muted">Attribution as reported: {label(d.attribution ?? 'unattributed')}</Chip>
          {d.languages.map((l) => <LangChip key={l} lang={l} />)}
        </Stack>
      </Panel>
      {series.length > 1 && (
        <Panel title="By language over time" headingLevel={3}>
          <StackedBarChart
            title="Articles by language over time"
            categories={series.map(([day]) => day)}
            series={LANG_SERIES.map((l) => ({ ...l, values: series.map(([, v]) => v[l.id] ?? 0) }))}
          />
        </Panel>
      )}
      {d.fact_checks.length > 0 && (
        <Panel title="Fact-checks attached" headingLevel={3}>
          <Stack as="ul" gap="sm" label="Fact-checks">
            {d.fact_checks.map((f) => (
              <li key={f.uri}><Text>{f.date}: <strong>{f.fact_check.verdict}</strong>, {f.fact_check.claim} ({f.fact_check.checker})</Text></li>
            ))}
          </Stack>
        </Panel>
      )}
      <Panel title="Articles" headingLevel={3}>
        <Table
          caption="Articles carrying this narrative"
          hideCaption
          rows={d.articles}
          rowKey={(a) => a.uri}
          columns={[
            { key: 'article_date', header: 'Date' },
            { key: 'title', header: 'Title', rowHeader: true, wrap: true, render: (a) => (a.url ? <TextLink href={a.url} external>{a.title}</TextLink> : a.title) },
            { key: 'source_domain', header: 'Outlet', render: (a) => <Stack gap="sm"><span>{a.source_domain}</span><TierChip tier={a.source_tier} /></Stack> },
            { key: 'stance', header: 'Stance', render: (a) => <StanceChip stance={a.stance} /> },
            { key: 'language', header: 'Language', render: (a) => <LangChip lang={a.language} /> },
          ]}
        />
      </Panel>
    </>
  );
}

const LANG_FILTER: SelectOption[] = [{ value: 'any', label: 'All languages' }, ...LANGS.map((l) => ({ value: l, label: LANG_NAME[l] }))];
const STANCE_FILTER: SelectOption[] = [
  { value: 'any', label: 'All stances' }, { value: 'promotes', label: 'Promotes' }, { value: 'reports', label: 'Reports' }, { value: 'debunks', label: 'Debunks' },
];

export function NarrativesPanel({ s }: { s: Swiss }) {
  const [lang, setLang] = useState('any');
  const [stance, setStance] = useState('any');
  const [openId, setOpenId] = useState<number | null>(null);
  const { loadNarratives, loadNarrativeDetail, setNarrativeDetail } = s;
  useEffect(() => {
    void loadNarratives(lang === 'any' ? undefined : lang, stance === 'any' ? undefined : stance);
  }, [loadNarratives, lang, stance]);
  useEffect(() => {
    if (openId) void loadNarrativeDetail(openId);
  }, [openId, loadNarrativeDetail]);

  if (openId && s.narrativeDetail?.id === openId) {
    return <NarrativeDetailView s={s} onBack={() => { setOpenId(null); setNarrativeDetail(null); }} />;
  }
  return (
    <Panel
      title="Narratives"
      description={`Last ${s.daysBack} days · ${s.narratives.length} narratives. Attribution is what the articles say, not a finding of this tool.`}
      headingLevel={3}
      headerAside={
        <Stack direction="row" gap="sm">
          <Select label="Language" hideLabel options={LANG_FILTER} value={lang} onValueChange={setLang} />
          <Select label="Stance" hideLabel options={STANCE_FILTER} value={stance} onValueChange={setStance} />
        </Stack>
      }
    >
      {s.loading.narratives ? <Loading /> : (
        <Table<Narrative>
          caption="Narratives"
          hideCaption
          rows={s.narratives}
          rowKey={(n) => String(n.id)}
          emptyText="No narratives in this window. Run “Analyse new” if articles are waiting."
          columns={[
            {
              key: 'name', header: 'Narrative', rowHeader: true, wrap: true,
              render: (n) => (
                <Stack gap="sm">
                  <TitleLink href={`#narrative-${n.id}`} onOpen={() => setOpenId(n.id)}>{n.name}</TitleLink>
                  {n.name !== n.statement && <Text variant="caption">{n.statement}</Text>}
                </Stack>
              ),
            },
            { key: 'last7', header: 'Last 7 days', render: (n) => trend(n.last7, n.prev7) },
            { key: 'stance', header: 'Promotes / reports / debunks', align: 'end', render: (n) => `${n.promotes} / ${n.reports} / ${n.debunks}` },
            { key: 'languages', header: 'Languages', render: (n) => n.languages.map((l) => l.toUpperCase()).join(' · ') },
            { key: 'attribution', header: 'Attribution', render: (n) => label(n.attribution ?? 'unattributed') },
            { key: 'top_outlets', header: 'Top outlets', wrap: true, render: (n) => n.top_outlets.join(', ') },
            { key: 'seen', header: 'Seen', render: (n) => `${n.first_seen ?? '–'} to ${n.last_seen ?? '–'}` },
          ]}
        />
      )}
    </Panel>
  );
}

// ------------------------------------------------------------------- Sources

const TIER_FILTER: SelectOption[] = [{ value: 'any', label: 'All source types' }, ...Object.entries(TIER_LABEL).map(([value, l]) => ({ value, label: l }))];

export function SourcesPanel({ s }: { s: Swiss }) {
  const { loadSources } = s;
  useEffect(() => {
    loadSources();
  }, [loadSources]);
  const [tier, setTier] = useState('any');
  const rows = s.sources.filter((x) => tier === 'any' || x.tier === tier);
  const co = s.cooccurrence;
  const cells = useMemo(() => {
    const idx: Record<string, number> = {};
    for (const c of co?.cells ?? []) idx[`${c.source}|${c.narrative_id}`] = c.count;
    return idx;
  }, [co]);
  return (
    <>
      <Panel
        title="Outlets"
        description={`Last ${s.daysBack} days · ${rows.length} outlets`}
        headingLevel={3}
        headerAside={<Select label="Source type" hideLabel options={TIER_FILTER} value={tier} onValueChange={setTier} />}
      >
        {s.loading.sources ? <Loading /> : (
          <Table<SourceRow>
            caption="Outlets"
            hideCaption
            rows={rows}
            rowKey={(r) => r.domain}
            emptyText="No outlets in this window."
            columns={[
              { key: 'name', header: 'Outlet', rowHeader: true, render: (r) => <Stack gap="sm"><span>{r.name}</span><Text variant="caption">{r.domain}</Text></Stack> },
              { key: 'tier', header: 'Type', render: (r) => <TierChip tier={r.tier} /> },
              { key: 'language', header: 'Language', render: (r) => <LangChip lang={r.language} /> },
              { key: 'articles', header: 'Articles', align: 'end' },
              { key: 'last7', header: 'Last 7 days', align: 'end' },
              { key: 'narratives', header: 'Narratives', align: 'end' },
              { key: 'promoted', header: 'Promoted', align: 'end' },
              { key: 'seen', header: 'Seen', render: (r) => `${r.first_seen ?? '–'} to ${r.last_seen ?? '–'}` },
            ]}
          />
        )}
      </Panel>
      {co && co.sources.length > 0 && (
        <Panel
          title="Who carries what"
          description="Outlet by narrative. Several outlets on one row within days of each other is what a coordinated push looks like in this data."
          headingLevel={3}
        >
          <Table<{ id: number; name: string }>
            caption="Articles per outlet and narrative"
            hideCaption
            rows={co.narratives}
            rowKey={(n) => String(n.id)}
            columns={[
              { key: 'name', header: 'Narrative', rowHeader: true, wrap: true },
              ...co.sources.map((src) => ({
                key: src,
                header: src.replace(/^www\./, ''),
                align: 'end' as const,
                render: (n: { id: number }) => {
                  const v = cells[`${src}|${n.id}`] ?? 0;
                  return v ? <Chip size="sm" tone={v >= 3 ? 'error' : v >= 2 ? 'warning' : 'muted'}>{v}</Chip> : '';
                },
              })),
            ]}
          />
        </Panel>
      )}
    </>
  );
}

// ------------------------------------------------------- Targets & techniques

function Legend({ entries, counts, criteriaLabel = 'Recorded when:' }: { entries: GlossaryEntry[]; counts?: Record<string, number>; criteriaLabel?: string }) {
  return (
    <Grid as="ul" columns={2} stackAt="wide" gap="md" label="Definitions">
      {entries.map((e) => (
        <li key={e.key}>
          <Stack gap="sm">
            <Stack direction="row" gap="sm">
              <Text variant="label" as="span">{e.label}</Text>
              {counts && <Text variant="caption" as="span">{counts[e.key] ? `${counts[e.key]} ${counts[e.key] === 1 ? 'article' : 'articles'}` : 'none in this window'}</Text>}
            </Stack>
            <Text variant="description">{e.attack}</Text>
            {e.criteria && <Text variant="caption"><strong>{criteriaLabel}</strong> {e.criteria}</Text>}
          </Stack>
        </li>
      ))}
    </Grid>
  );
}

export function TargetsPanel({ s }: { s: Swiss }) {
  const { loadTargets } = s;
  useEffect(() => {
    loadTargets();
  }, [loadTargets]);
  const active = s.targets.filter((t) => t.articles > 0);
  const seeded = s.targets.filter((t) => t.articles === 0);
  const techs = s.techniques.filter((t) => t.technique !== 'none_reported');
  const g = s.glossary;
  const techCounts = Object.fromEntries(s.techniques.map((t) => [t.technique, t.articles]));
  const targetCounts = s.targets.reduce<Record<string, number>>((acc, t) => ({ ...acc, [t.type]: (acc[t.type] ?? 0) + t.articles }), {});
  return (
    <>
      <Grid columns={2} stackAt="wide" gap="md">
        <Panel title={`Targets, last ${s.daysBack} days`} headingLevel={3}>
          <Stack gap="md">
            {s.loading.targets ? <Loading /> : (
              <Table<TargetRow>
                caption="Targets"
                hideCaption
                rows={active}
                rowKey={(t) => t.type + t.name}
                emptyText="No targets named in this window."
                columns={[
                  { key: 'name', header: 'Target', rowHeader: true, wrap: true },
                  { key: 'type', header: 'Type', render: (t) => label(t.type) },
                  { key: 'articles', header: 'Articles', align: 'end' },
                  { key: 'last7', header: 'Last 7 days', align: 'end' },
                  { key: 'last_seen', header: 'Last seen' },
                ]}
              />
            )}
            {seeded.length > 0 && <Text variant="caption">Watched, nothing yet: {seeded.map((t) => t.name).join(' · ')}</Text>}
          </Stack>
        </Panel>
        <Panel title="Techniques reported" description="A first deepfake or synthetic text aimed at a named person raises an alert on the Calendar tab." headingLevel={3}>
          {s.loading.techniques ? <Loading /> : (
            <StackedBars
              title="Techniques reported"
              series={[{ id: 'older', label: 'Earlier in the window', color: 1 }, { id: 'last7', label: 'Last 7 days', color: 3 }]}
              rows={techs.map((t) => ({ id: t.technique, label: label(t.technique), values: [Math.max(0, t.articles - t.last7), t.last7] }))}
              emptyText="No technique reported in this window."
            />
          )}
        </Panel>
      </Grid>

      {g && (
        <Panel
          title="What each technique means"
          description={`Each entry gives the attack and the test the model must pass before it records the label; the wording is the instruction the model receives. Techniques are recorded from what articles report, so a count of nought says nothing about whether a method is in use. Articles that name no method are recorded as “none reported” (${techCounts.none_reported ?? 0} here) and left off the chart.`}
          headingLevel={3}
        >
          <Legend entries={g.techniques.filter((t) => t.key !== 'none_reported')} counts={techCounts} />
        </Panel>
      )}
      {g && (
        <Panel title="What each target type means" description="Each type says what the manipulation is aimed at, as the article describes it." headingLevel={3}>
          <Legend entries={g.targets} counts={targetCounts} />
        </Panel>
      )}
      {g && (
        <Panel
          title="Attribution and source type"
          description="Attribution records who the article says is behind something; this tool never makes that finding itself. The source type sets how strictly an article is judged, which is why an outlet with no type loses storylines a known one would keep."
          headingLevel={3}
        >
          <Stack gap="lg">
            <Legend entries={g.attributions} />
            <PanelDivider />
            <Legend entries={g.tiers} criteriaLabel="How it is judged:" />
          </Stack>
        </Panel>
      )}
    </>
  );
}

// ---------------------------------------------------------------- Languages

export function LanguagesPanel({ s }: { s: Swiss }) {
  const { loadLanguages } = s;
  useEffect(() => {
    void loadLanguages();
  }, [loadLanguages]);
  const d = s.languages;
  if (s.loading.languages || !d) return <Loading />;
  const total = Object.values(d.totals).reduce((a, b) => a + b, 0);
  return (
    <>
      <Grid as="ul" columns={4} stackAt="small" gap="sm" label="Articles by language">
        {LANGS.map((l) => (
          <li key={l}>
            <Stat surface="panel" label={LANG_NAME[l]} value={d.totals[l] || 0} meta={`${total ? Math.round((100 * (d.totals[l] || 0)) / total) : 0}% of analysed articles`} />
          </li>
        ))}
      </Grid>
      <Panel title="Articles per week by language" headingLevel={3}>
        <StackedBarChart
          title="Articles per week by language"
          categories={d.weekly.map((w) => w.week)}
          series={LANG_SERIES.map((l) => ({ ...l, values: d.weekly.map((w) => w[l.id]) }))}
          emptyText="Nothing analysed in this window."
        />
      </Panel>
      <Panel
        title="Narratives that crossed a language border"
        description="A storyline first seen in one language and later in another is being carried across the border by someone. The lag is the days between first sightings."
        headingLevel={3}
      >
        <Table
          caption="Narratives that crossed a language border"
          hideCaption
          rows={d.crossings}
          rowKey={(n) => String(n.id)}
          emptyText="No narrative has appeared in a second language in this window."
          columns={[
            { key: 'name', header: 'Narrative', rowHeader: true, wrap: true },
            { key: 'from', header: 'From', render: (n) => <LangChip lang={n.crossed_from ?? null} /> },
            { key: 'to', header: 'To', render: (n) => <Stack direction="row" gap="sm">{(n.crossed_to ?? []).map((l) => <LangChip key={l} lang={l} />)}</Stack> },
            { key: 'lag', header: 'Lag', align: 'end', render: (n) => `${n.lag_days} days` },
            { key: 'by', header: 'Articles by language', render: (n) => Object.entries(n.by_language).map(([l, c]) => `${l.toUpperCase()} ${c}`).join(' · ') },
          ]}
        />
      </Panel>
      <Panel title="All narratives by language" headingLevel={3}>
        <Table
          caption="All narratives by language"
          hideCaption
          rows={d.narratives}
          rowKey={(n) => String(n.id)}
          columns={[
            { key: 'name', header: 'Narrative', rowHeader: true, wrap: true },
            ...LANGS.map((l) => ({ key: l, header: l.toUpperCase(), align: 'end' as const, render: (n: (typeof d.narratives)[number]) => n.by_language[l] || '' })),
          ]}
        />
      </Panel>
    </>
  );
}

// ----------------------------------------------------------------- Calendar

export function CalendarPanel({ s }: { s: Swiss }) {
  const { loadCalendar } = s;
  useEffect(() => {
    void loadCalendar();
  }, [loadCalendar]);
  const d = s.calendar;
  if (s.loading.calendar || !d) return <Loading />;
  const upcoming = d.votes.filter((v) => v.days_to >= 0).slice(0, 3);
  const alerts = d.events.filter((e) => e.event_type === 'alert');
  const days = d.daily.map((x) => x.day);
  const max = niceMax(Math.max(0, ...d.daily.map((x) => x.count)));
  const voteMarks = d.votes
    .map((v) => ({ v, index: days.indexOf(v.date) }))
    .filter((x) => x.index >= 0)
    .map(({ v, index }) => ({ id: v.date, index, seriesId: 'count', label: `Vote: ${v.label}` }));
  return (
    <>
      {upcoming.length > 0 && (
        <Grid as="ul" columns={3} stackAt="small" gap="sm" label="Upcoming votes">
          {upcoming.map((v) => (
            <li key={v.date}><Stat surface="panel" label={v.label} value={`${v.days_to} days`} meta={v.date} tone="error" /></li>
          ))}
        </Grid>
      )}
      <Panel title="Narrative articles per day, vote dates marked" headingLevel={3}>
        {d.daily.length === 0 ? <Empty>Nothing analysed in this window yet.</Empty> : (
          <LineChart
            title="Narrative articles per day"
            categories={days}
            series={[
              { id: 'count', label: 'All', color: 2, fill: true, values: d.daily.map((x) => x.count) },
              { id: 'promotes', label: 'Promotes', color: 1, values: d.daily.map((x) => x.promotes) },
            ]}
            yDomain={[0, max]}
            yTicks={[0, max / 2, max]}
            annotations={voteMarks}
          />
        )}
      </Panel>
      <Grid columns={2} stackAt="wide" gap="md">
        <Panel title="Alerts" headingLevel={3}>
          {alerts.length === 0 ? (
            <Text>No alerts. The rules: a new narrative on two outlets within 48 hours, weekly volume three times the week before, a first crossing into a second language, synthetic media aimed at a person.</Text>
          ) : (
            <Stack as="ul" gap="sm" label="Alerts">
              {alerts.map((e) => (
                <ActivityRow key={e.id} as="li" primary={e.title} timestamp={e.event_date} dateTime={e.event_date} dotTone={e.significance === 'high' ? 'accent' : 'pending'} dotLabel={`${e.significance} significance`} />
              ))}
            </Stack>
          )}
        </Panel>
        <Panel title="Narratives first seen" headingLevel={3}>
          {d.first_seen.length === 0 ? <Text>None in this window.</Text> : (
            <Stack as="ul" gap="sm" label="Narratives first seen">
              {d.first_seen.map((f) => <ActivityRow key={f.id} as="li" primary={f.name} timestamp={f.day} dateTime={f.day} />)}
            </Stack>
          )}
        </Panel>
      </Grid>
    </>
  );
}

// ---------------------------------------------------------------- Responses

export function ResponsesPanel({ s }: { s: Swiss }) {
  const { loadResponses } = s;
  useEffect(() => {
    void loadResponses();
  }, [loadResponses]);
  const d = s.responses;
  if (s.loading.responses || !d) return <Loading />;
  return (
    <Grid columns={2} stackAt="wide" gap="md">
      <Panel title="Fact-checks" headingLevel={3}>
        {d.fact_checks.length === 0 ? <Text>No fact-check articles in this window.</Text> : (
          <Stack as="ul" gap="md" label="Fact-checks">
            {d.fact_checks.map((f) => (
              <li key={f.uri}>
                <Stack gap="sm">
                  <Text variant="caption">{[f.date, f.fact_check.checker || f.news_source].filter(Boolean).join(' · ')}</Text>
                  <Text><strong>{f.fact_check.verdict}</strong>: {f.fact_check.claim}</Text>
                  {f.url && <TextLink href={f.url} external>{f.title}</TextLink>}
                </Stack>
              </li>
            ))}
          </Stack>
        )}
      </Panel>
      <Panel title="Institutional and platform responses" headingLevel={3}>
        {d.responses.length === 0 ? <Text>No responses recorded in this window.</Text> : (
          <Stack as="ul" gap="md" label="Responses">
            {d.responses.map((r) => (
              <li key={r.uri}>
                <Stack gap="sm">
                  <Text variant="caption">{[r.date, r.news_source].filter(Boolean).join(' · ')}</Text>
                  <Text><strong>{r.response.actor}</strong>: {r.response.action}</Text>
                  {r.url && <TextLink href={r.url} external>{r.title}</TextLink>}
                </Stack>
              </li>
            ))}
          </Stack>
        )}
      </Panel>
    </Grid>
  );
}

// ----------------------------------------------------------------- Insights

const BRIEF_ORDER: [string, string][] = [
  ['summary', 'This week'], ['narratives', 'Narratives'], ['actors_and_vectors', 'Actors and vectors'], ['targets', 'Targets'], ['outlook', 'Outlook'],
];

export function InsightsPanel({ s }: { s: Swiss }) {
  const { loadBrief } = s;
  useEffect(() => {
    void loadBrief();
  }, [loadBrief]);
  const b = s.brief;
  const sections = (b?.sections ?? {}) as Record<string, string>;
  return (
    <Panel
      title="Weekly brief"
      description={b ? `Latest: ${new Date(b.created_at).toLocaleString('en-GB')} · ${b.article_count} articles · ${b.narrative_count} narratives · ${b.model ?? ''}` : 'Written by the AI from this watch’s data only.'}
      headingLevel={3}
      headerAside={
        <Button iconStart={<Icon name="Sparkle" size="sm" />} disabled={s.loading.brief} onClick={() => void s.makeBrief(7)}>
          {s.loading.brief ? 'Writing…' : 'Generate weekly brief'}
        </Button>
      }
    >
      {!b ? <Empty>No brief yet.</Empty> : (
        <Stack gap="lg">
          {sections.headline && <Text variant="label">{sections.headline}</Text>}
          {BRIEF_ORDER.map(([k, l]) => sections[k] ? (
            <Stack key={k} gap="sm">
              <Eyebrow as="h4">{l}</Eyebrow>
              <Markdown text={sections[k]} />
            </Stack>
          ) : null)}
          {!sections.summary && <Markdown text={b.brief_text} />}
        </Stack>
      )}
    </Panel>
  );
}
