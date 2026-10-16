import { useImperativeHandle, useState } from 'react';
import { Icon, IconButton, Popover, Stack, Switch, Text } from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import type { ExploreWorkspace } from '../lib/useExploreConfig';
import { ArticleSheet, type SheetTarget } from './ArticleSheet';
import { Briefing } from './Briefing';
import { Incidents } from './Incidents';
import { LatestNews, type OpenArticle } from './LatestNews';
import { Narratives } from './Narratives';
import { PromoteDialog, type PromoteArticle } from './PromoteDialog';
import { BriefingTuneDialog, IncidentSettingsDialog, NarrativeSettingsDialog } from './SettingsDialogs';
import { useFeed } from './useFeed';

export interface NewsFeedHandle {
  /** The filter bar's Refresh: reloads the articles and runs the AI for every section on show */
  refresh: () => Promise<void>;
}

export type Sections = { briefing: boolean; incidents: boolean; narratives: boolean; topics: boolean };
// Shared with the old page
const SECTIONS_KEY = 'explore_visibleSections';
const SECTION_LABELS: [keyof Sections, string][] = [['briefing', 'Your briefing'], ['incidents', 'Incidents'], ['narratives', 'Narratives'], ['topics', 'Latest news']];

export function loadSections(): Sections {
  const all = { briefing: true, incidents: true, narratives: true, topics: true };
  try {
    return { ...all, ...JSON.parse(localStorage.getItem(SECTIONS_KEY) ?? '{}') };
  } catch {
    return all;
  }
}

interface Props {
  ref?: React.Ref<NewsFeedHandle>;
  sections: Sections;
  ws: ExploreWorkspace;
  notify: (m: string) => void;
  askConfirm: (c: Confirm) => void;
}

export function NewsFeed({ ref, sections, ws, notify, askConfirm }: Props) {
  const feed = useFeed(ws.config, ws.topics, ws.ready);
  const [reloadKey, setReloadKey] = useState(0);
  const [sheet, setSheet] = useState<SheetTarget | null>(null);
  const [promote, setPromote] = useState<PromoteArticle | null>(null);
  const [dialog, setDialog] = useState<null | 'tune' | 'incidents' | 'narratives'>(null);

  useImperativeHandle(ref, () => ({
    refresh: async () => {
      setReloadKey((k) => k + 1);
      const jobs: Promise<unknown>[] = [];
      if (sections.incidents) jobs.push(feed.runIncidents(false));
      if (sections.narratives) jobs.push(feed.runNarratives('force'));
      if (sections.briefing) jobs.push(feed.loadBriefing(true));
      await Promise.all(jobs);
    },
  }));

  const open: OpenArticle = (a, related) => setSheet({ article: typeof a === 'string' ? { uri: a } : a, related });
  const openUri = (uri: string) => open(uri);

  return (
    <>
      {sections.briefing && <Briefing ws={ws} feed={feed} notify={notify} askConfirm={askConfirm} onTune={() => setDialog('tune')} />}
      {sections.incidents && <Incidents feed={feed} notify={notify} askConfirm={askConfirm} onOpenArticle={openUri} onConfigure={() => setDialog('incidents')} />}
      {sections.narratives && <Narratives feed={feed} notify={notify} onOpenArticle={openUri} onConfigure={() => setDialog('narratives')} />}
      {sections.topics && <LatestNews feed={feed} dateRange={ws.config.dateRange} notify={notify} onOpenArticle={open} reloadKey={reloadKey} />}

      <ArticleSheet
        target={sheet}
        onClose={() => setSheet(null)}
        onOpenRelated={(uri) => setSheet((s) => ({ article: { uri }, related: s?.related?.filter((r) => r.uri !== uri) }))}
        starred={feed.starred}
        onToggleStar={feed.toggleStar}
        onPromote={setPromote}
        notify={notify}
      />
      <PromoteDialog
        article={promote}
        topic={feed.topic}
        profileId={ws.config.profileId}
        onOpenChange={(o) => !o && setPromote(null)}
        onDone={feed.reloadSaved}
        notify={notify}
      />
      <BriefingTuneDialog
        open={dialog === 'tune'}
        onOpenChange={(o) => setDialog(o ? 'tune' : null)}
        notify={notify}
        articleCount={ws.config.articleCount}
        onSaved={(articleCount) => ws.setConfig({ articleCount })}
      />
      <IncidentSettingsDialog open={dialog === 'incidents'} onOpenChange={(o) => setDialog(o ? 'incidents' : null)} notify={notify} />
      <NarrativeSettingsDialog open={dialog === 'narratives'} onOpenChange={(o) => setDialog(o ? 'narratives' : null)} notify={notify} />
    </>
  );
}

/** Show or hide the News Feed's sections; kept in this browser, shared with the old page. */
export function SectionsPopover({ sections, onChange }: { sections: Sections; onChange: (s: Sections) => void }) {
  const toggle = (k: keyof Sections, on: boolean) => {
    const next = { ...sections, [k]: on };
    try {
      localStorage.setItem(SECTIONS_KEY, JSON.stringify(next));
    } catch {
      // lasts for this visit
    }
    onChange(next);
  };
  return (
    <Popover title="Sections" align="end" trigger={<IconButton icon={<Icon name="SlidersHorizontal" size="sm" />} label="Show or hide News Feed sections" />}>
      <Stack gap="md">
        <Text variant="caption">Hidden sections aren’t loaded or generated on Refresh.</Text>
        {SECTION_LABELS.map(([k, label]) => <Switch key={k} label={label} checked={sections[k]} onCheckedChange={(on) => toggle(k, on)} />)}
      </Stack>
    </Popover>
  );
}
