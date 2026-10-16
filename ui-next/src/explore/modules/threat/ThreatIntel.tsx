import { useCallback, useEffect, useState } from 'react';
import { Banner, Button, Icon, IconButton, Panel, Select, Stack, TabPanel, Tabs } from '@aunoo/ui';
import { errorText } from '../../../shell';
import { loadStarred, saveStarred } from '../../feed/api';
import { ArticleSheet, type SheetTarget } from '../../feed/ArticleSheet';
import { PromoteDialog, type PromoteArticle } from '../../feed/PromoteDialog';
import type { ModuleTabProps } from '../types';
import { getMapData, getOverview, type OverviewStats, type SeverityLevel, type ThreatMapData } from './api';
import type { ArticleFilter, ThreatCtx, ThreatTab } from './context';
import { PERIOD_OPTIONS } from './labels';
import { ScheduleDialog } from './overlays/ScheduleDialog';
import { UpdateDialog } from './overlays/UpdateDialog';
import { Actors } from './tabs/Actors';
import { Analysis } from './tabs/Analysis';
import { Articles } from './tabs/Articles';
import { Categories } from './tabs/Categories';
import { Insights } from './tabs/Insights';
import { MapView } from './tabs/MapView';
import { Overview } from './tabs/Overview';
import { Timeline } from './tabs/Timeline';
import './threat.css';

/*
 * Threat Intelligence on the routes the old tab used (/api/threat-intelligence, see
 * ui/src/components/newsfeed/ThreatIntelligenceTab.tsx). The AI reads collected articles ("Update")
 * and files threats, actors, indicators and campaigns; these views read what it filed. The header
 * period applies to the overview, map and timeline. Loading the tab only reads.
 */

const SUBTABS: { id: ThreatTab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'map', label: 'Map' },
  { id: 'timeline', label: 'Timeline' },
  { id: 'actors', label: 'Actors' },
  { id: 'categories', label: 'Categories' },
  { id: 'analysis', label: 'Indicators and campaigns' },
  { id: 'insights', label: 'Briefings' },
  { id: 'articles', label: 'Articles' },
];

export function ThreatIntel({ model, notify, askConfirm }: ModuleTabProps) {
  const [tab, setTab] = useState<ThreatTab>('overview');
  const [daysBack, setDaysBack] = useState(30);
  const [types, setTypes] = useState<string[]>([]);
  const [severities, setSeverities] = useState<SeverityLevel[]>([]);
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [mapThreats, setMapThreats] = useState<ThreatMapData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dialog, setDialog] = useState<null | 'update' | 'schedule'>(null);
  const [filter, setFilter] = useState<ArticleFilter>({});
  // Bumped after an update finishes, so the open sub-view reloads too
  const [version, setVersion] = useState(0);

  const [sheet, setSheet] = useState<SheetTarget | null>(null);
  const [promote, setPromote] = useState<PromoteArticle | null>(null);
  const [starred, setStarred] = useState<string[]>(loadStarred);
  const toggleStar = (uri: string) =>
    setStarred((s) => {
      const next = s.includes(uri) ? s.filter((u) => u !== uri) : [...s, uri];
      saveStarred(next);
      return next;
    });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, m] = await Promise.all([getOverview(daysBack), getMapData({ daysBack, threatTypes: types, severityLevels: severities })]);
      setStats(s);
      setMapThreats(m);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoading(false);
    }
  }, [daysBack, types, severities]);
  useEffect(() => void load(), [load]);
  // The Explore filter bar's Refresh button
  useEffect(() => {
    const onRefresh = () => {
      void load();
      setVersion((v) => v + 1);
    };
    window.addEventListener('explore:refresh', onRefresh);
    return () => window.removeEventListener('explore:refresh', onRefresh);
  }, [load]);

  const ctx: ThreatCtx = {
    daysBack, model, stats, mapThreats, loading, notify, askConfirm,
    showArticles: (f) => {
      setFilter(f);
      setTab('articles');
    },
    openArticle: (a) => setSheet({
      article: { uri: a.uri, title: a.title ?? undefined, summary: a.summary ?? undefined, publication_date: a.publication_date ?? undefined, source: a.source ? { name: a.source } : undefined } as SheetTarget['article'],
    }),
  };

  return (
    <>
      <Panel
        title="Threat Intelligence"
        description="Cyber threats, the groups behind them and the indicators to watch for, filed by the AI from collected articles."
        headerAside={
          <Stack direction="row" gap="sm">
            <Select label="Period" hideLabel icon="CalendarBlank" options={PERIOD_OPTIONS} value={String(daysBack)} onValueChange={(v) => setDaysBack(Number(v))} />
            <IconButton icon={<Icon name="Clock" size="sm" />} label="Scheduled updates" onClick={() => setDialog('schedule')} />
            <Button variant="secondary" iconStart={<Icon name="Sparkle" size="sm" />} onClick={() => setDialog('update')}>Update</Button>
            <IconButton icon={<Icon name="ArrowClockwise" size="sm" />} label="Reload" disabled={loading} onClick={() => { void load(); setVersion((v) => v + 1); }} />
          </Stack>
        }
      />
      {error && <Banner tone="error" title="Threat data didn’t load" description={error} action={<Button variant="secondary" size="sm" onClick={() => void load()}>Try again</Button>} />}

      <Tabs label="Threat Intelligence sections" scrollable value={tab} onValueChange={(v) => setTab(v as ThreatTab)} items={SUBTABS.map((t) => ({ value: t.id, label: t.label }))}>
        {SUBTABS.map((t) => (
          <TabPanel key={t.id} value={t.id}>
            {t.id === tab && (
              <Stack gap="lg">
                {tab === 'overview' && <Overview {...ctx} />}
                {tab === 'map' && (
                  <MapView
                    ctx={ctx}
                    types={types}
                    severities={severities}
                    onTypes={setTypes}
                    onSeverities={setSeverities}
                  />
                )}
                {tab === 'timeline' && <Timeline key={version} {...ctx} />}
                {tab === 'actors' && <Actors key={version} {...ctx} />}
                {tab === 'categories' && <Categories key={version} {...ctx} />}
                {tab === 'analysis' && <Analysis key={version} {...ctx} />}
                {tab === 'insights' && <Insights key={version} {...ctx} />}
                {tab === 'articles' && <Articles key={version} ctx={ctx} filter={filter} onFilter={setFilter} />}
              </Stack>
            )}
          </TabPanel>
        ))}
      </Tabs>

      <UpdateDialog
        open={dialog === 'update'}
        onOpenChange={(o) => setDialog(o ? 'update' : null)}
        model={model}
        notify={notify}
        onFinished={() => {
          void load();
          setVersion((v) => v + 1);
        }}
      />
      <ScheduleDialog open={dialog === 'schedule'} onOpenChange={(o) => setDialog(o ? 'schedule' : null)} model={model} notify={notify} askConfirm={askConfirm} />
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
