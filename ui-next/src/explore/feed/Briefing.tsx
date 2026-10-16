import { useEffect, useState } from 'react';
import {
  ArticleCard, Banner, Button, Chip, EmptyState, Eyebrow, Grid, Icon, IconButton, Menu, Panel, PanelDivider, Select, Skeleton, Stack, Stat, Text,
  type MenuItem, type SelectOption,
} from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import { errorText } from '../../shell';
import type { ExploreWorkspace, Persona } from '../lib/useExploreConfig';
import {
  askAuspex, cleanTitle, download, fetchBriefingPrefs, fetchHiddenBriefings, hideBriefing, setBriefingPreference, type TopStory,
} from './api';
import type { Feed } from './useFeed';
import { AddToBriefingDialog } from '../desk/AddToBriefingDialog';
import { ShareDialog } from '../shared/ShareDialog';
import { downloadCsv, downloadPdf } from '../shared/exports';
import { BriefingPodcast } from './BriefingPodcast';

const PERSONAS: SelectOption[] = [
  { value: 'CEO', label: 'CEO: strategic overview' },
  { value: 'CMO', label: 'CMO: marketing and brand' },
  { value: 'CTO', label: 'CTO: technology and innovation' },
  { value: 'CISO', label: 'CISO: security and risk' },
];

type Tone = 'success' | 'warning' | 'error' | 'info' | 'muted';
const RISK_TONE: Record<string, Tone> = { opportunity: 'success', mixed: 'warning', risk: 'error' };
// Signal strength graded as on the old briefing: strong stands out, moderate is marked, weak is plain
const SIGNAL_TONE: Record<string, 'accent' | 'info' | 'muted'> = { strong: 'accent', moderate: 'info' };
// The old briefing's arrows: up for an opportunity, down for a risk, a warning sign otherwise
const RISK_ICON: Record<string, 'TrendUp' | 'ArrowDown' | 'Warning'> = { opportunity: 'TrendUp', mixed: 'Warning', risk: 'ArrowDown' };
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const headlineOf = (s: TopStory) => s.headline || s.title;
const urlOf = (s: TopStory) => s.url || s.uri || s.primary_article?.url || s.primary_article?.uri;

function toMarkdown(stories: TopStory[], generated: string) {
  const lines = [`# Executive briefing`, '', `Generated ${generated}`, ''];
  for (const s of stories) {
    lines.push(`## ${cleanTitle(headlineOf(s))}`, '');
    if (s.executive_takeaway) lines.push(`**Why this matters:** ${s.executive_takeaway}`, '');
    if (s.summary) lines.push(s.summary, '');
    if (s.strategic_relevance) lines.push(`**Strategic relevance:** ${s.strategic_relevance}`, '');
    for (const a of s.executive_action ?? []) lines.push(`- ${a}`);
    if (urlOf(s)) lines.push('', `Source: ${s.source ?? ''} ${urlOf(s)}`);
    lines.push('');
  }
  return lines.join('\n');
}

/** One story in the shape /api/share/briefing-card and the briefing share take */
function storyPayload(s: TopStory) {
  return {
    title: headlineOf(s), headline: s.headline, executive_takeaway: s.executive_takeaway, strategic_relevance: s.strategic_relevance,
    category: s.category, signal_strength: s.signal_strength, risk_opportunity: s.risk_opportunity, time_horizon: s.time_horizon,
    source: s.source || s.primary_article?.source?.name, date: s.date || s.primary_article?.publication_date, url: urlOf(s), summary: s.summary,
    executive_actions: s.executive_action, scores: s.scores,
  };
}

/** The briefing as CSV rows, with the old export's columns */
function csvRows(stories: TopStory[]) {
  return stories.map((s) => ({
    Title: headlineOf(s), Source: s.source || s.primary_article?.source?.name || '', Date: s.date || s.primary_article?.publication_date || '',
    Category: s.category || '', 'Time Horizon': s.time_horizon || '', 'Risk/Opportunity': s.risk_opportunity || '', 'Signal Strength': s.signal_strength || '',
    Score: s.scores?.overall ?? '', 'Executive Takeaway': s.executive_takeaway || '', 'Strategic Relevance': s.strategic_relevance || '',
    Actions: (s.executive_action ?? []).join('; '), URL: urlOf(s) || '',
  }));
}

function Details({ s }: { s: TopStory }) {
  const scores = s.scores ?? {};
  const scoreRows = (['relevance', 'impact', 'actionability', 'timeliness', 'credibility', 'overall'] as const).filter((k) => scores[k] != null);
  const url = urlOf(s);
  return (
    <>
      <PanelDivider />
      <Stack gap="lg">
        {s.summary && (
          <Stack gap="sm">
            <Eyebrow as="h4">Summary</Eyebrow>
            <Text variant="description">{s.summary}</Text>
          </Stack>
        )}
        {s.strategic_relevance && <Banner tone="info" icon="Target" headingLevel={4} title="Strategic relevance" description={s.strategic_relevance} />}
        {!!s.executive_action?.length && (
          <Stack gap="sm">
            <Eyebrow as="h4">Executive actions</Eyebrow>
            <Stack as="ul" gap="sm" label="Executive actions">
              {s.executive_action.map((a) => (
                <li key={a}><Stack direction="row" wrap={false} gap="sm"><Icon name="ArrowRight" size="sm" /><Text variant="description" as="span">{a}</Text></Stack></li>
              ))}
            </Stack>
          </Stack>
        )}
        {scoreRows.length > 0 && (
          <Stack gap="sm">
            <Eyebrow as="h4">Scores</Eyebrow>
            <Grid as="ul" columns={3} stackAt="never" gap="sm" label="Scores">
              {scoreRows.map((k) => <li key={k}><Stat size="compact" surface="panel" label={cap(k)} value={scores[k]} meta="out of 5" /></li>)}
            </Grid>
          </Stack>
        )}
        <Stack direction="row" gap="sm" label="Article links">
          {url && (
            <Button asChild variant="secondary" size="sm" iconStart={<Icon name="ArrowSquareOut" size="sm" />}>
              <a href={url} target="_blank" rel="noreferrer">Read original<span className="visually-hidden"> (opens in new tab)</span></a>
            </Button>
          )}
          <Button
            variant="secondary"
            size="sm"
            iconStart={<Icon name="ChatCentered" size="sm" />}
            onClick={() => askAuspex(`Tell me more about this story and what it means for us: "${cleanTitle(headlineOf(s))}". ${s.executive_takeaway ?? ''}`)}
          >
            Ask Auspex
          </Button>
        </Stack>
      </Stack>
    </>
  );
}

interface Props {
  ws: ExploreWorkspace;
  feed: Feed;
  notify: (m: string) => void;
  askConfirm: (c: Confirm) => void;
  onTune: () => void;
}

export function Briefing({ ws, feed, notify, askConfirm, onTune }: Props) {
  const [prefs, setPrefs] = useState<Record<string, 'more' | 'less'>>({});
  const [hidden, setHidden] = useState<string[]>([]);
  const [toBriefing, setToBriefing] = useState<TopStory | null>(null);
  const [share, setShare] = useState<null | { kind: 'briefing' | 'briefing-card'; payload: Record<string, unknown>; title: string }>(null);
  const [podcast, setPodcast] = useState(false);
  useEffect(() => {
    void fetchBriefingPrefs().then((p) =>
      setPrefs(Object.fromEntries([...p.more_like.map((x) => [x.headline, 'more']), ...p.less_like.map((x) => [x.headline, 'less'])])),
    );
    void fetchHiddenBriefings().then(setHidden);
  }, []);

  const b = feed.briefing;
  const stories = (b?.articles ?? []).filter((s) => !hidden.includes(headlineOf(s))).slice(0, 8);
  const updated = b?.generated_at ? new Date(b.generated_at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' }) : null;

  const act = async (s: TopStory, id: string) => {
    const h = headlineOf(s);
    if (id === 'briefing') {
      setToBriefing(s);
      return;
    }
    if (id === 'share') {
      setShare({ kind: 'briefing-card', payload: storyPayload(s), title: cleanTitle(h) });
      return;
    }
    if (id === 'more' || id === 'less') {
      const next = prefs[h] === id ? null : id;
      try {
        await setBriefingPreference(s, next);
        setPrefs((p) => {
          const c = { ...p };
          if (next) c[h] = next;
          else delete c[h];
          return c;
        });
        notify(next ? `You’ll see ${next === 'more' ? 'more' : 'fewer'} stories like this` : 'Preference cleared');
      } catch (e) {
        notify(`Not saved: ${errorText(e)}`);
      }
    } else if (id === 'star') {
      const uri = urlOf(s);
      if (uri) feed.toggleStar(uri);
    } else if (id === 'hide') {
      askConfirm({
        title: 'Hide this story?',
        message: 'It leaves your briefing now and stays out of later briefings.',
        action: 'Hide story',
        onConfirm: () =>
          void hideBriefing(h).then(
            () => {
              setHidden((x) => [...x, h]);
              notify('Story hidden from your briefings');
            },
            (e: unknown) => notify(`Not hidden: ${errorText(e)}`),
          ),
      });
    }
  };

  const story = toBriefing;
  return (
    <>
    <Panel
      title="Your briefing"
      description={updated ? `Updated ${updated}` : feed.briefingBusy ? 'Writing your briefing…' : undefined}
      headerAside={
        <Stack direction="row" gap="sm">
          <Select
            label="Briefing persona"
            hideLabel
            options={PERSONAS}
            value={ws.config.persona}
            onValueChange={(v) => ws.setConfig({ persona: v as Persona })}
          />
          <Menu
            label="Download the briefing"
            align="end"
            trigger={<IconButton icon={<Icon name="DownloadSimple" size="sm" />} label="Download the briefing" disabled={!stories.length} />}
            items={[
              { id: 'md', label: 'Markdown', icon: 'FileText' },
              { id: 'pdf', label: 'PDF', icon: 'FileText' },
              { id: 'csv', label: 'CSV (one row per story)', icon: 'Table' },
            ]}
            onSelect={(id) => {
              const name = `briefing-${b?.date ?? 'today'}`;
              if (id === 'md') download(`${name}.md`, toMarkdown(stories, updated ?? ''));
              else if (id === 'csv') downloadCsv(`${name}.csv`, csvRows(stories));
              else downloadPdf({ filename: `${name}.pdf`, title: `Executive briefing for ${ws.config.persona}`, subtitle: updated ? `Updated ${updated}` : undefined, markdown: toMarkdown(stories, updated ?? '').replace(/^# .*\n/, '') }).catch((e: unknown) => notify(`PDF not made: ${errorText(e)}`));
            }}
          />
          <IconButton
            icon={<Icon name="ShareNetwork" size="sm" />}
            label="Share the briefing by email"
            disabled={!stories.length}
            onClick={() => setShare({
              kind: 'briefing',
              title: `Executive briefing for ${ws.config.persona}`,
              payload: { persona: ws.config.persona, articles: stories.map(storyPayload), key_themes: (b as { key_themes?: string[] } | null)?.key_themes },
            })}
          />
          <IconButton icon={<Icon name="SpeakerHigh" size="sm" />} label="Make a podcast of the briefing" disabled={!stories.length} onClick={() => setPodcast(true)} />
          <IconButton icon={<Icon name="SlidersHorizontal" size="sm" />} label="Tune the briefing" onClick={onTune} />
          <IconButton
            icon={<Icon name="ArrowClockwise" size="sm" />}
            label="Write a new briefing"
            disabled={feed.briefingBusy}
            onClick={() => void feed.loadBriefing(true)}
          />
        </Stack>
      }
    >
      {feed.briefingError && <Banner tone="error" title="The briefing didn’t load" description={feed.briefingError} />}
      {feed.briefingBusy && !stories.length ? (
        <Skeleton variant="block" size="card" />
      ) : stories.length === 0 ? (
        <EmptyState
          icon="Newspaper"
          title="No briefing yet"
          action={<Button onClick={() => void feed.loadBriefing(true)} disabled={feed.briefingBusy}>Write a briefing</Button>}
        >
          The AI picks the most important stories for the persona above and explains why each matters.
        </EmptyState>
      ) : (
        <Grid as="ul" columns={2} gap="md" label="Briefing stories">
          {stories.map((s, i) => {
            const h = headlineOf(s);
            const uri = urlOf(s);
            const isStarred = !!uri && feed.starred.includes(uri);
            const actions: MenuItem[] = [
              { id: 'more', label: prefs[h] === 'more' ? 'Clear “More like this”' : 'More like this', icon: 'ArrowUp' },
              { id: 'less', label: prefs[h] === 'less' ? 'Clear “Less like this”' : 'Less like this', icon: 'ArrowDown' },
              ...(uri ? [{ id: 'star', label: isStarred ? 'Remove star' : 'Star', icon: 'Star' as const }] : []),
              ...(uri ? [{ id: 'briefing', label: 'Add to a briefing', icon: 'Notebook' as const }] : []),
              { id: 'share', label: 'Share by email', icon: 'ShareNetwork' },
              { id: 'hide', label: 'Hide from briefings', icon: 'EyeSlash', separatorBefore: true },
            ];
            return (
              <ArticleCard
                key={`${h}-${i}`}
                as="li"
                variant="row"
                headingLevel={3}
                meta={[s.date, s.category].filter(Boolean).join(' · ')}
                flag={isStarred ? <Chip size="sm" tone="accent" icon={<Icon name="Star" size="sm" />}>Starred</Chip> : prefs[h] ? <Chip size="sm" tone="muted">{prefs[h] === 'more' ? 'More like this' : 'Less like this'}</Chip> : undefined}
                title={cleanTitle(h)}
                summary={s.executive_takeaway ? <Banner headingLevel={4} title="Why this matters" description={s.executive_takeaway} /> : s.summary}
                details={<Details s={s} />}
                expandFullWidth
                actions={actions}
                actionsLabel={`Actions for “${cleanTitle(h)}”`}
                onAction={(id) => void act(s, id)}
                tags={
                  <>
                    {s.risk_opportunity && <Chip size="sm" tone={RISK_TONE[s.risk_opportunity] ?? 'muted'} icon={<Icon name={RISK_ICON[s.risk_opportunity] ?? 'Warning'} size="sm" />}>{cap(s.risk_opportunity)}</Chip>}
                    {s.time_horizon && <Chip size="sm" tone="info">{s.time_horizon} impact</Chip>}
                    {s.signal_strength && <Chip size="sm" tone={SIGNAL_TONE[s.signal_strength.toLowerCase()] ?? 'muted'}>{cap(s.signal_strength)} signal</Chip>}
                  </>
                }
                footer={uri ? <a href={uri} target="_blank" rel="noreferrer">{s.source || 'Source'}<span className="visually-hidden"> (opens in new tab)</span></a> : s.source}
              />
            );
          })}
        </Grid>
      )}
    </Panel>
    {share && <ShareDialog open onOpenChange={(o) => !o && setShare(null)} kind={share.kind} payload={share.payload} title={share.title} notify={notify} />}
    <BriefingPodcast open={podcast} onOpenChange={setPodcast} stories={stories} persona={ws.config.persona} model={ws.config.model} askConfirm={askConfirm} notify={notify} />
    {story && (
      <AddToBriefingDialog
        open
        onClose={() => setToBriefing(null)}
        itemType="article"
        article={{
          uri: urlOf(story) || '',
          title: headlineOf(story),
          summary: story.summary || story.executive_takeaway,
          source: story.source || story.primary_article?.source?.name,
          topic: story.category,
          category: story.category,
          url: urlOf(story),
          analysis: {
            key_insight: story.executive_takeaway, executive_takeaway: story.executive_takeaway, strategic_relevance: story.strategic_relevance,
            category: story.category, time_horizon: story.time_horizon, risk_opportunity: story.risk_opportunity, signal_strength: story.signal_strength,
          },
        }}
        notify={notify}
      />
    )}
    </>
  );
}
