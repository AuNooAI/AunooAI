import { useCallback, useEffect, useState } from 'react';
import { Banner, Button, Icon, IconButton, Panel, Select, Stack, TabPanel, Tabs } from '@aunoo/ui';
import type { PolicyArticle } from '@monolith/policyTrackerApi';
import { loadStarred, saveStarred } from '../../feed/api';
import { ArticleSheet, type SheetTarget } from '../../feed/ArticleSheet';
import { PromoteDialog, type PromoteArticle } from '../../feed/PromoteDialog';
import type { ModuleTabProps } from '../types';
import { PERIOD_OPTIONS, periodText, TRACKER_TOPIC } from './api';
import { RelatedDialog } from './RelatedDialog';
import { Analysis } from './tabs/Analysis';
import { Articles } from './tabs/Articles';
import { Categories } from './tabs/Categories';
import { Insights } from './tabs/Insights';
import { Overview } from './tabs/Overview';
import { Themes } from './tabs/Themes';
import { Timeline } from './tabs/Timeline';
import { UpdateDialog } from './UpdateDialog';
import { usePolicyTracker } from './usePolicyTracker';

/*
 * US Crisis Tracker (the policy module), on the routes the old tab uses (/api/policy-tracker/*, see
 * ui/src/components/newsfeed/PolicyTrackerTab.tsx). It follows one topic, "Trump Administration
 * Tracker", whose articles are sorted into ten policy categories. Loading the tab only reads; the AI
 * runs only from the Insights and Categories buttons, and data arrives through Update data.
 */

const SUBTABS = [
  { value: 'overview', label: 'Overview' },
  { value: 'timeline', label: 'Timeline' },
  { value: 'themes', label: 'Themes' },
  { value: 'analysis', label: 'Analysis' },
  { value: 'insights', label: 'Insights' },
  { value: 'categories', label: 'Categories' },
  { value: 'articles', label: 'Articles' },
];
const TAB_KEY = 'aunoo.policy.tab';
const loadTab = () => {
  try {
    const t = localStorage.getItem(TAB_KEY);
    return SUBTABS.some((s) => s.value === t) ? (t as string) : 'overview';
  } catch {
    return 'overview';
  }
};

export function CrisisTracker({ model, notify, askConfirm }: ModuleTabProps) {
  const pt = usePolicyTracker();
  const [tab, setTab] = useState(loadTab);
  const [updating, setUpdating] = useState(false);
  const [sheet, setSheet] = useState<SheetTarget | null>(null);
  const [promote, setPromote] = useState<PromoteArticle | null>(null);
  const [related, setRelated] = useState<{ uri: string; title: string } | null>(null);
  const [starred, setStarred] = useState<string[]>(loadStarred);

  useEffect(() => {
    try {
      localStorage.setItem(TAB_KEY, tab);
    } catch {
      // per visit only
    }
  }, [tab]);
  // The Explore filter bar's Refresh button
  const { refresh } = pt;
  useEffect(() => {
    window.addEventListener('explore:refresh', refresh);
    return () => window.removeEventListener('explore:refresh', refresh);
  }, [refresh]);

  const toggleStar = (uri: string) =>
    setStarred((s) => {
      const next = s.includes(uri) ? s.filter((u) => u !== uri) : [...s, uri];
      saveStarred(next);
      return next;
    });
  const openArticle = useCallback((a: { uri: string; title?: string } | PolicyArticle) => {
    const p = a as Partial<PolicyArticle> & { uri: string };
    setSheet({ article: { uri: p.uri, title: p.title, summary: p.summary ?? undefined, publication_date: p.publication_date ?? undefined } });
  }, []);

  const period = periodText(pt.config.daysBack);
  const openUpdate = () => setUpdating(true);

  return (
    <>
      <Panel
        title="US Crisis Tracker"
        description={`Articles from “${pt.config.topic || TRACKER_TOPIC}”, sorted into ten policy categories, for ${period}.`}
        headerAside={
          <Stack direction="row" gap="sm">
            <Select label="Period" hideLabel icon="CalendarBlank" options={PERIOD_OPTIONS} value={String(pt.config.daysBack)} onValueChange={(v) => pt.updateConfig({ daysBack: Number(v) })} />
            <Button variant="secondary" iconStart={<Icon name="DownloadSimple" size="sm" />} onClick={openUpdate}>Update data</Button>
            <IconButton icon={<Icon name="ArrowClockwise" size="sm" />} label="Reload the figures" disabled={pt.loadingOverview} onClick={refresh} />
          </Stack>
        }
      />
      {pt.error && <Banner tone="error" title="Something didn’t load" description={pt.error} action={<Button variant="secondary" size="sm" onClick={pt.clearError}>Dismiss</Button>} />}

      <Tabs label="Crisis Tracker sections" scrollable value={tab} onValueChange={setTab} items={SUBTABS}>
        {SUBTABS.map((s) => (
          <TabPanel key={s.value} value={s.value}>
            {s.value === tab && (
              <Stack gap="lg">
                {tab === 'overview' && <Overview pt={pt} period={period} onUpdate={openUpdate} />}
                {tab === 'timeline' && <Timeline pt={pt} />}
                {tab === 'themes' && <Themes pt={pt} />}
                {tab === 'analysis' && <Analysis pt={pt} />}
                {tab === 'insights' && <Insights pt={pt} model={model} notify={notify} askConfirm={askConfirm} />}
                {tab === 'categories' && <Categories pt={pt} model={model} />}
                {tab === 'articles' && <Articles pt={pt} onOpen={openArticle} onRelated={(a) => setRelated({ uri: a.uri, title: a.title })} />}
              </Stack>
            )}
          </TabPanel>
        ))}
      </Tabs>

      <UpdateDialog open={updating} onOpenChange={setUpdating} onDone={refresh} notify={notify} />
      <RelatedDialog source={related} load={pt.related} onClose={() => setRelated(null)} onOpen={openArticle} />
      <ArticleSheet
        target={sheet}
        onClose={() => setSheet(null)}
        onOpenRelated={(uri) => setSheet({ article: { uri } })}
        starred={starred}
        onToggleStar={toggleStar}
        onPromote={setPromote}
        notify={notify}
      />
      <PromoteDialog article={promote} topic={pt.config.topic} onOpenChange={(o) => !o && setPromote(null)} onDone={() => undefined} notify={notify} />
    </>
  );
}
