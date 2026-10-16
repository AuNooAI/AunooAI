import { useState } from 'react';
import { ArticleCard, Banner, Button, Chip, Grid, Icon, IconButton, Menu, Panel, Skeleton, Stack, Text, type MenuItem } from '@aunoo/ui';
import { errorText } from '../../shell';
import { askAuspex, download, saveNarrative, unsaveNarrative, type ArticleTheme } from './api';
import type { Feed } from './useFeed';
import { ShareDialog } from '../shared/ShareDialog';
import { downloadCsv, downloadPdf } from '../shared/exports';

const FIRST = 6;

function toMarkdown(themes: ArticleTheme[]) {
  const out = ['# Narratives', ''];
  for (const t of themes) {
    out.push(`## ${t.theme_name}`, '', t.theme_summary || t.description, '', `${t.article_count ?? (t.articles ?? []).length} articles`, '');
    for (const a of t.articles ?? []) out.push(`- ${a.title}${a.news_source ? ` (${a.news_source})` : ''}`);
    out.push('');
  }
  return out.join('\n');
}

/** One narrative in the shape /api/share/narrative takes */
function sharePayload(t: ArticleTheme, topic?: string) {
  return {
    narrative_name: t.theme_name, description: t.theme_summary || t.description, topic, sentiment: t.sentiment, confidence: t.confidence,
    article_count: t.article_count ?? (t.articles ?? []).length, source_count: t.source_count, key_entities: t.key_entities,
    key_points: t.research_suggestions,
    articles: (t.articles ?? []).map((a) => ({ title: a.title, source: a.news_source, url: a.uri, summary: a.short_summary, date: a.publication_date })),
  };
}

/** The narratives as CSV rows, with the old export's columns */
function csvRows(themes: ArticleTheme[]) {
  return themes.map((t) => {
    const urls = (t.articles ?? []).map((a) => a.uri).filter(Boolean);
    return {
      'Theme Name': t.theme_name, Summary: t.theme_summary || t.description, 'Article Count': t.article_count ?? (t.articles ?? []).length,
      'Source Count': t.source_count ?? '', Sentiment: t.sentiment ?? '', Confidence: t.confidence ?? '', 'Key Entities': (t.key_entities ?? []).join('; '),
      'Research Suggestions': (t.research_suggestions ?? []).join('; '), 'Primary Article URL': urls[0] ?? '', 'All Article URLs': urls.join(' '),
    };
  });
}

interface Props {
  feed: Feed;
  notify: (m: string) => void;
  onOpenArticle: (uri: string) => void;
  onConfigure: () => void;
}

export function Narratives({ feed, notify, onOpenArticle, onConfigure }: Props) {
  const [all, setAll] = useState(false);
  const themes = feed.themes;
  const shown = all ? themes : themes.slice(0, FIRST);
  const [share, setShare] = useState<null | { payload: Record<string, unknown>; title: string }>(null);

  const act = async (t: ArticleTheme & { topic: string }, id: string) => {
    try {
      if (id === 'save') {
        await saveNarrative(t, t.topic);
        feed.reloadSaved();
        notify('Narrative saved');
      } else if (id === 'unsave') {
        await unsaveNarrative(t.theme_name, t.topic);
        feed.reloadSaved();
        notify('Narrative removed from Saved');
      } else if (id === 'share') {
        setShare({ payload: sharePayload(t, t.topic), title: t.theme_name });
      } else if (id === 'md') {
        download(`narrative-${t.theme_name.replace(/\W+/g, '-').toLowerCase()}.md`, toMarkdown([t]));
      } else if (id === 'research') {
        askAuspex(`Research this narrative: "${t.theme_name}". ${t.theme_summary || t.description} Who is driving it, how is it evolving, and what does it mean for us?`, t.topic);
      }
    } catch (e) {
      notify(`Not done: ${errorText(e)}`);
    }
  };

  return (
    <Panel
      title="Narratives"
      description={themes.length ? `${themes.length} themes identified` : undefined}
      headerAside={
        <Stack direction="row" gap="sm">
          <Menu
            label="Download the narratives"
            align="end"
            trigger={<IconButton icon={<Icon name="DownloadSimple" size="sm" />} label="Download the narratives" disabled={!themes.length} />}
            items={[
              { id: 'md', label: 'Markdown', icon: 'FileText' },
              { id: 'pdf', label: 'PDF', icon: 'FileText' },
              { id: 'csv', label: 'CSV (one row per narrative)', icon: 'Table' },
            ]}
            onSelect={(id) => {
              if (id === 'md') download('narratives.md', toMarkdown(themes));
              else if (id === 'csv') downloadCsv('narratives.csv', csvRows(themes));
              else downloadPdf({ filename: 'narratives.pdf', title: 'Narratives', subtitle: feed.topics.join(', '), markdown: toMarkdown(themes).replace(/^# .*\n/, '') }).catch((e: unknown) => notify(`PDF not made: ${errorText(e)}`));
            }}
          />
          <IconButton icon={<Icon name="SlidersHorizontal" size="sm" />} label="Narrative settings" onClick={onConfigure} />
          <Button size="sm" variant="secondary" iconStart={<Icon name="Sparkle" size="sm" />} disabled={feed.narrativesBusy || !feed.topics.length} onClick={() => void feed.runNarratives('generate')}>
            Generate
          </Button>
        </Stack>
      }
    >
      <Stack gap="md">
        {feed.narrativesError && <Banner tone="error" title="Narratives didn’t load" description={feed.narrativesError} />}
        {feed.narrativesBusy && !themes.length ? <Skeleton variant="block" size="card" /> : themes.length === 0 ? (
          <Text>{feed.topics.length ? 'No stored narratives for these topics and dates. Generate groups the window’s articles into themes with the AI.' : 'Pick a topic to see narratives.'}</Text>
        ) : (
          <>
            <Grid as="ul" columns={2} gap="md" label="Narratives">
              {shown.map((t) => {
                const isSaved = feed.savedNarratives.includes(t.theme_name);
                const actions: MenuItem[] = [
                  isSaved ? { id: 'unsave', label: 'Remove from Saved', icon: 'BookmarkSimple' } : { id: 'save', label: 'Save', icon: 'BookmarkSimple' },
                  { id: 'research', label: 'Research with Auspex', icon: 'ChatCentered' },
                  { id: 'share', label: 'Share by email', icon: 'ShareNetwork' },
                  { id: 'md', label: 'Download as Markdown', icon: 'DownloadSimple' },
                ];
                const articles = t.articles ?? [];
                const count = t.article_count ?? articles.length;
                return (
                  <ArticleCard
                    key={`${t.topic}-${t.theme_name}`}
                    as="li"
                    variant="row"
                    headingLevel={3}
                    meta={`${count} ${count === 1 ? 'article' : 'articles'}${feed.topics.length > 1 ? ` · ${t.topic}` : ''}`}
                    flag={isSaved ? <Chip size="sm" tone="accent">Saved</Chip> : undefined}
                    title={t.theme_name}
                    summary={t.theme_summary || t.description}
                    actions={actions}
                    actionsLabel={`Actions for “${t.theme_name}”`}
                    onAction={(id) => void act(t, id)}
                    tags={t.sentiment ? <Chip size="sm" tone="muted">{t.sentiment}</Chip> : undefined}
                    details={
                      articles.length > 0 ? (
                        <Stack as="ul" gap="sm" label={`${t.theme_name} articles`}>
                          {articles.slice(0, 8).map((a) => (
                            <li key={a.uri}>
                              <Stack gap="sm">
                                <Stack direction="row" gap="sm">
                                  <Button variant="ghost" size="sm" onClick={() => onOpenArticle(a.uri)}>{a.title}</Button>
                                  <Text variant="caption" as="span">{[a.news_source, a.publication_date?.slice(0, 10)].filter(Boolean).join(' · ')}</Text>
                                </Stack>
                                {a.short_summary && <Text variant="caption">{a.short_summary}</Text>}
                              </Stack>
                            </li>
                          ))}
                          {articles.length > 8 && <li><Text variant="caption">and {articles.length - 8} more</Text></li>}
                        </Stack>
                      ) : undefined
                    }
                  />
                );
              })}
            </Grid>
            {themes.length > FIRST && (
              <div><Button variant="ghost" size="sm" onClick={() => setAll((v) => !v)}>{all ? 'Show fewer' : `Show all ${themes.length}`}</Button></div>
            )}
          </>
        )}
      </Stack>
      {share && <ShareDialog open onOpenChange={(o) => !o && setShare(null)} kind="narrative" payload={share.payload} title={share.title} notify={notify} />}
    </Panel>
  );
}
