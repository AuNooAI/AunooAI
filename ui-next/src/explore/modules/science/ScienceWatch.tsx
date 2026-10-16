import { useEffect, useState } from 'react';
import { Banner, Button, Icon, IconButton, Panel, Select, Stack, TabPanel, Tabs } from '@aunoo/ui';
import type { ScienceArticle } from '@monolith/scienceFundingApi';
import { ArticleSheet, type SheetTarget } from '../../feed/ArticleSheet';
import { PromoteDialog, type PromoteArticle } from '../../feed/PromoteDialog';
import { loadStarred, saveStarred } from '../../feed/api';
import type { ModuleTabProps } from '../types';
import { Analysis } from './Analysis';
import { Articles } from './Articles';
import { Categories } from './Categories';
import { ClassifyDialog } from './ClassifyDialog';
import { Insights } from './Insights';
import { PERIOD_OPTIONS } from './labels';
import { Overview } from './Overview';
import { RelatedDialog } from './RelatedDialog';
import { ScheduleDialog } from './ScheduleDialog';
import { Themes } from './Themes';
import { Timeline } from './Timeline';
import { useScience } from './useScience';

/*
 * ScienceWatch on the routes the old tab uses (/api/science-funding/*, see
 * ui/src/components/newsfeed/ScienceFundingTab.tsx): science funding coverage sorted into ten
 * categories. The header picks the period for every sub-tab. Refresh reloads the figures only; the
 * old Refresh also re-ran the AI report when Insights was open.
 */

type Sub = 'overview' | 'timeline' | 'themes' | 'analysis' | 'insights' | 'categories' | 'articles';
const SUBS: { id: Sub; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'timeline', label: 'Timeline' },
  { id: 'themes', label: 'Themes' },
  { id: 'analysis', label: 'Overlaps' },
  { id: 'insights', label: 'Report' },
  { id: 'categories', label: 'By category' },
  { id: 'articles', label: 'Articles' },
];
const SUB_KEY = 'aunoo.science.tab';

export function ScienceWatch({ model, notify, askConfirm }: ModuleTabProps) {
  const sci = useScience();
  const [sub, setSub] = useState<Sub>(() => {
    try {
      const s = localStorage.getItem(SUB_KEY);
      return SUBS.some((x) => x.id === s) ? (s as Sub) : 'overview';
    } catch {
      return 'overview';
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(SUB_KEY, sub);
    } catch {
      // per visit only
    }
  }, [sub]);

  const [dialog, setDialog] = useState<null | 'classify' | 'schedules'>(null);
  const [related, setRelated] = useState<{ uri: string; title: string } | null>(null);
  const [sheet, setSheet] = useState<SheetTarget | null>(null);
  const [promote, setPromote] = useState<PromoteArticle | null>(null);
  const [starred, setStarred] = useState<string[]>(loadStarred);
  const toggleStar = (uri: string) =>
    setStarred((s) => {
      const next = s.includes(uri) ? s.filter((u) => u !== uri) : [...s, uri];
      saveStarred(next);
      return next;
    });

  // The Explore filter bar's Refresh button
  useEffect(() => {
    window.addEventListener('explore:refresh', sci.refresh);
    return () => window.removeEventListener('explore:refresh', sci.refresh);
  }, [sci.refresh]);

  const openArticle = (a: { uri: string; title?: string } & Partial<ScienceArticle>) =>
    setSheet({ article: { uri: a.uri, title: a.title, summary: a.summary ?? undefined, publication_date: a.publication_date ?? undefined } as SheetTarget['article'] });
  const days = sci.config.daysBack;

  return (
    <>
      <Panel
        title="ScienceWatch"
        description={`Science funding coverage from the topic “${sci.topic}”, sorted into ten funding categories.`}
        headerAside={
          <Stack direction="row" gap="sm">
            <Select label="Period" hideLabel icon="CalendarBlank" options={PERIOD_OPTIONS} value={String(days)} onValueChange={(v) => sci.updateConfig({ daysBack: Number(v) })} />
            <Button variant="secondary" iconStart={<Icon name="Lightning" size="sm" />} onClick={() => setDialog('classify')}>Classify articles</Button>
            <IconButton icon={<Icon name="ArrowClockwise" size="sm" />} label="Reload the figures" onClick={sci.refresh} />
          </Stack>
        }
      />
      {sci.error && <Banner tone="error" title="Something didn’t load" description={sci.error} action={<Button variant="secondary" size="sm" onClick={sci.clearError}>Dismiss</Button>} />}

      <Tabs label="ScienceWatch sections" scrollable value={sub} onValueChange={(v) => setSub(v as Sub)} items={SUBS.map((s) => ({ value: s.id, label: s.label }))}>
        {SUBS.map((s) => (
          <TabPanel key={s.id} value={s.id}>
            {s.id === sub && (
              <Stack gap="lg">
                {sub === 'overview' && <Overview stats={sci.stats} categories={sci.categories} temporal={sci.temporal} loading={sci.overviewLoading} daysBack={days} />}
                {sub === 'timeline' && <Timeline daysBack={days} temporal={sci.temporal} reloadKey={sci.reloadKey} />}
                {sub === 'themes' && <Themes daysBack={days} reloadKey={sci.reloadKey} />}
                {sub === 'analysis' && <Analysis categories={sci.categories} daysBack={days} reloadKey={sci.reloadKey} />}
                {sub === 'insights' && <Insights daysBack={days} model={model} notify={notify} askConfirm={askConfirm} />}
                {sub === 'categories' && <Categories categories={sci.categories} daysBack={days} model={model} />}
                {sub === 'articles' && <Articles sci={sci} onOpen={openArticle} onRelated={(a) => setRelated({ uri: a.uri, title: a.title })} />}
              </Stack>
            )}
          </TabPanel>
        ))}
      </Tabs>

      <ClassifyDialog open={dialog === 'classify'} onOpenChange={(o) => setDialog(o ? 'classify' : null)} onDone={sci.refresh} onOpenSchedules={() => setDialog('schedules')} />
      <ScheduleDialog open={dialog === 'schedules'} onOpenChange={(o) => setDialog(o ? 'schedules' : null)} onRan={sci.refresh} />
      <RelatedDialog article={related} onClose={() => setRelated(null)} onOpen={openArticle} />
      <ArticleSheet
        target={sheet}
        onClose={() => setSheet(null)}
        onOpenRelated={(uri) => setSheet({ article: { uri } })}
        starred={starred}
        onToggleStar={toggleStar}
        onPromote={setPromote}
        notify={notify}
      />
      <PromoteDialog article={promote} onOpenChange={(o) => !o && setPromote(null)} onDone={() => undefined} notify={notify} />
    </>
  );
}
