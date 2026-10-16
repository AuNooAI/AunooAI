import { useCallback, useEffect, useState } from 'react';
import { Banner, Button, Icon, IconButton, Panel, Select, Stack, TabPanel, Tabs } from '@aunoo/ui';
import {
  getMapData, getOverviewStats,
  type Hotspot, type OverviewStats, type RiskLevel, type ThreatCategory,
} from '@monolith/geopoliticalHotspotsApi';
import { errorText } from '../../../shell';
import { loadStarred, saveStarred } from '../../feed/api';
import { ArticleSheet, type SheetTarget } from '../../feed/ArticleSheet';
import { PromoteDialog, type PromoteArticle } from '../../feed/PromoteDialog';
import type { ModuleTabProps } from '../types';
import { PERIOD_OPTIONS } from './labels';
import { UpdateDialog } from './overlays/UpdateDialog';
import { Analysis } from './tabs/Analysis';
import { Articles, type ArticleFilter } from './tabs/Articles';
import { GlobalView } from './tabs/GlobalView';
import { Insights } from './tabs/Insights';
import { Overview } from './tabs/Overview';
import { Regions } from './tabs/Regions';
import { Themes } from './tabs/Themes';
import { Timeline } from './tabs/Timeline';

/*
 * GeoHotSpots on the routes the old tab uses (/api/geopolitical-hotspots/*, see
 * ui/src/components/newsfeed/GeopoliticalHotspotsTab.tsx). A hotspot is a place the AI found in
 * curated articles, scored for risk and intensity. The frame holds the period, the overview figures
 * and the map points that several sub-tabs share; each sub-tab loads anything else itself. Clicking a
 * hotspot, a risk level or a category anywhere opens Articles filtered to it.
 */

type SubTab = 'overview' | 'map' | 'timeline' | 'regions' | 'themes' | 'analysis' | 'insights' | 'articles';
const SUBTABS: { id: SubTab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'map', label: 'Global view' },
  { id: 'timeline', label: 'Timeline' },
  { id: 'regions', label: 'Regions' },
  { id: 'themes', label: 'Themes' },
  { id: 'analysis', label: 'Analysis' },
  { id: 'insights', label: 'Insights' },
  { id: 'articles', label: 'Articles' },
];

const TAB_KEY = 'aunoo.geo.tab';
const DAYS_KEY = 'aunoo.geo.days';
const read = (k: string) => {
  try {
    return localStorage.getItem(k);
  } catch {
    return null;
  }
};
const write = (k: string, v: string) => {
  try {
    localStorage.setItem(k, v);
  } catch {
    // per visit only
  }
};

export function GeoHotSpots({ model, notify, askConfirm }: ModuleTabProps) {
  const [tab, setTab] = useState<SubTab>(() => (SUBTABS.some((s) => s.id === read(TAB_KEY)) ? (read(TAB_KEY) as SubTab) : 'overview'));
  const [daysBack, setDaysBack] = useState(() => (PERIOD_OPTIONS.some((o) => o.value === read(DAYS_KEY)) ? Number(read(DAYS_KEY)) : 30));
  useEffect(() => write(TAB_KEY, tab), [tab]);
  useEffect(() => write(DAYS_KEY, String(daysBack)), [daysBack]);

  // The map's filters; the Overview shares the same points, as on the old page
  const [categories, setCategories] = useState<ThreatCategory[]>([]);
  const [riskLevels, setRiskLevels] = useState<RiskLevel[]>([]);

  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [hotspots, setHotspots] = useState<Hotspot[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [updateOpen, setUpdateOpen] = useState(false);
  // When the chosen period is empty, whether older hotspots exist (a site whose runs stopped)
  const [older, setOlder] = useState<{ count: number; newest: string | null; days: number } | null>(null);

  const load = useCallback(() => {
    setError(null);
    setStats(null);
    setHotspots(null);
    Promise.all([
      getOverviewStats(undefined, daysBack),
      getMapData({ categories: categories.length ? categories : undefined, riskLevels: riskLevels.length ? riskLevels : undefined, daysBack }),
    ]).then(
      ([s, h]) => {
        setStats(s);
        setHotspots(h);
        setOlder(null);
        if (s.total_hotspots === 0 && daysBack < 365) {
          // Look back a year, so an empty period on a site whose runs stopped doesn't read as "no data at all"
          getMapData({ daysBack: 365 }).then(
            (all) => {
              if (!all.length) return;
              const newest = all.map((x) => x.last_article_date ?? '').filter(Boolean).sort().pop() ?? null;
              const age = newest ? Math.ceil((Date.now() - Date.parse(newest)) / 86400000) : 365;
              const fit = PERIOD_OPTIONS.map((o) => Number(o.value)).find((d) => d >= age) ?? 365;
              setOlder({ count: all.length, newest, days: fit });
            },
            () => undefined,
          );
        }
      },
      (e) => {
        setError(errorText(e));
        setHotspots([]);
      },
    );
  }, [daysBack, categories, riskLevels]);
  useEffect(() => load(), [load]);
  // The Explore filter bar's Refresh button
  const refresh = useCallback(() => {
    load();
    setReloadKey((k) => k + 1);
  }, [load]);
  useEffect(() => {
    window.addEventListener('explore:refresh', refresh);
    return () => window.removeEventListener('explore:refresh', refresh);
  }, [refresh]);

  // Articles filter handed over from a click elsewhere; the key remounts Articles with it
  const [articleFilter, setArticleFilter] = useState<ArticleFilter>({});
  const [filterKey, setFilterKey] = useState(0);
  const showArticles = useCallback((f: ArticleFilter) => {
    setArticleFilter(f);
    setFilterKey((k) => k + 1);
    setTab('articles');
  }, []);
  const onHotspot = useCallback((h: Hotspot) => showArticles({ hotspot: h }), [showArticles]);
  const onRisk = useCallback((r: RiskLevel) => showArticles({ risk: r }), [showArticles]);
  const onCategory = useCallback((c: string) => showArticles({ category: c as ThreatCategory }), [showArticles]);

  // The shared article details sheet, as on the other Explore tabs
  const [sheet, setSheet] = useState<SheetTarget | null>(null);
  const [promote, setPromote] = useState<PromoteArticle | null>(null);
  const [starred, setStarred] = useState<string[]>(loadStarred);
  const toggleStar = (uri: string) =>
    setStarred((s) => {
      const next = s.includes(uri) ? s.filter((u) => u !== uri) : [...s, uri];
      saveStarred(next);
      return next;
    });
  const openArticle = useCallback((a: { uri: string; title?: string | null; summary?: string | null; publication_date?: string | null }) => {
    setSheet({ article: { uri: a.uri, title: a.title ?? undefined, summary: a.summary ?? undefined, publication_date: a.publication_date ?? undefined } });
  }, []);

  return (
    <>
      <Panel
        title="Geopolitical hotspots"
        description="Places the AI found in the collected news, scored for risk and intensity. Click a hotspot, a risk level or a category to see the articles behind it."
        headerAside={
          <Stack direction="row" gap="sm">
            <Select label="Period" hideLabel icon="CalendarBlank" options={PERIOD_OPTIONS} value={String(daysBack)} onValueChange={(v) => setDaysBack(Number(v))} />
            <Button variant="secondary" iconStart={<Icon name="DownloadSimple" size="sm" />} onClick={() => setUpdateOpen(true)}>Update hotspots</Button>
            <IconButton icon={<Icon name="ArrowClockwise" size="sm" />} label="Refresh" onClick={refresh} />
          </Stack>
        }
      />
      {older && (
        <Banner
          tone="info"
          title={`No hotspots in the last ${daysBack} days`}
          description={`There are ${older.count.toLocaleString()} from the last year${older.newest ? `; the newest article is from ${new Date(older.newest).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}` : ''}. GeoHotSpots only reads new articles when “Update hotspots” or a schedule runs.`}
          action={<Button variant="secondary" size="sm" onClick={() => setDaysBack(older.days)}>{`Show the last ${PERIOD_OPTIONS.find((o) => Number(o.value) === older.days)?.label.replace(/^Last /, '') ?? `${older.days} days`}`}</Button>}
        />
      )}
      {error && <Banner tone="error" title="Hotspots didn’t load" description={error} action={<Button variant="secondary" size="sm" onClick={load}>Try again</Button>} />}

      <Tabs label="GeoHotSpots sections" scrollable value={tab} onValueChange={(v) => setTab(v as SubTab)} items={SUBTABS.map((s) => ({ value: s.id, label: s.label }))}>
        {SUBTABS.map((s) => (
          <TabPanel key={s.id} value={s.id}>
            {s.id === tab && (
              <Stack gap="lg">
                {tab === 'overview' && <Overview stats={stats} hotspots={hotspots} daysBack={daysBack} olderExists={!!older} onHotspot={onHotspot} onRisk={onRisk} onCategory={onCategory} />}
                {tab === 'map' && (
                  <GlobalView
                    hotspots={hotspots}
                    categories={categories}
                    riskLevels={riskLevels}
                    onCategories={setCategories}
                    onRiskLevels={setRiskLevels}
                    onHotspot={onHotspot}
                  />
                )}
                {tab === 'timeline' && <Timeline key={reloadKey} daysBack={daysBack} />}
                {tab === 'regions' && <Regions key={reloadKey} />}
                {tab === 'themes' && <Themes key={reloadKey} daysBack={daysBack} onCategory={onCategory} />}
                {tab === 'analysis' && <Analysis key={reloadKey} onCategory={onCategory} />}
                {tab === 'insights' && <Insights key={reloadKey} stats={stats} model={model} notify={notify} askConfirm={askConfirm} onHotspot={(id) => { const h = hotspots?.find((x) => x.id === id); if (h) onHotspot(h); }} />}
                {tab === 'articles' && <Articles key={`${filterKey}-${reloadKey}`} initial={articleFilter} onOpen={openArticle} />}
              </Stack>
            )}
          </TabPanel>
        ))}
      </Tabs>

      <UpdateDialog open={updateOpen} onClose={() => setUpdateOpen(false)} model={model} notify={notify} askConfirm={askConfirm} onChanged={refresh} />
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
