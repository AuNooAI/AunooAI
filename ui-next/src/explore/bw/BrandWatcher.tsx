import { useCallback, useEffect, useMemo, useState } from 'react';
import { Banner, Button, Checkbox, Icon, IconButton, Menu, Panel, Popover, Select, Skeleton, Stack, TabPanel, Tabs, Text } from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import { loadStarred, saveStarred } from '../feed/api';
import { ArticleSheet, type SheetTarget } from '../feed/ArticleSheet';
import { PromoteDialog, type PromoteArticle } from '../feed/PromoteDialog';
import { getStorySiblings } from '@monolith/brandWatcherApi';
import { DAYS_OPTIONS, type BwContext, type BwTabId } from './context';
import { useBrandWatcher } from './useBrandWatcher';
import { BrandSettingsDialog } from './overlays/BrandSettingsDialog';
import { ClassifyDialog } from './overlays/ClassifyDialog';
import { BW_EXPORT_ROOT, exportItems, runExport } from './overlays/exports';
import { Onboarding } from './overlays/Onboarding';
import { SourcesDialog } from './overlays/SourcesDialog';
import { Accounts } from './tabs/Accounts';
import { Analysis } from './tabs/Analysis';
import { Articles } from './tabs/Articles';
import { Comparison } from './tabs/Comparison';
import { Dashboard } from './tabs/Dashboard';
import { Help } from './tabs/Help';
import { Incidents } from './tabs/Incidents';
import { Insights } from './tabs/Insights';
import { Perception } from './tabs/Perception';
import { SignalsDialog } from './tabs/SignalsDialog';
import { Social } from './tabs/Social';
import { Voices } from './tabs/Voices';
import { Workforce } from './tabs/Workforce';

/*
 * Brand Watcher on the routes the old tab uses (/api/brand-watcher/*, see
 * ui/src/components/newsfeed/BrandWatcherTab.tsx). The header picks brands and the period for
 * every sub-tab; each sub-tab loads what else it needs.
 */

const SUBTABS: { id: BwTabId; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'analysis', label: 'Brand analysis' },
  { id: 'perception', label: 'Perception' },
  { id: 'voices', label: 'Voices' },
  { id: 'comparison', label: 'Comparison' },
  { id: 'insights', label: 'Insights' },
  { id: 'articles', label: 'Articles' },
  { id: 'social', label: 'Social' },
  { id: 'accounts', label: 'Accounts' },
  { id: 'workforce', label: 'Workforce' },
  { id: 'incidents', label: 'Incidents' },
  { id: 'help', label: 'Help' },
];
// Shared with the old page, so a reader lands on the sub-tab they left
const TAB_KEY = 'bw_active_tab';

function loadTab(): BwTabId {
  try {
    const t = localStorage.getItem(TAB_KEY);
    return SUBTABS.some((s) => s.id === t) ? (t as BwTabId) : 'dashboard';
  } catch {
    return 'dashboard';
  }
}

interface Props {
  notify: (m: string) => void;
  askConfirm: (c: Confirm) => void;
  /** /api/modules features.bw_voices; undefined until the site has answered */
  voicesFeature: boolean | undefined;
}

export function BrandWatcher({ notify, askConfirm, voicesFeature }: Props) {
  const bw = useBrandWatcher();
  const { brands, config, updateConfig } = bw;
  const [tab, setTab] = useState<BwTabId>(loadTab);
  const voicesEnabled = voicesFeature === true;
  // A remembered Voices tab snaps back once the site says Voices is off
  useEffect(() => {
    if (voicesFeature === false && tab === 'voices') setTab('dashboard');
  }, [voicesFeature, tab]);
  useEffect(() => {
    try {
      localStorage.setItem(TAB_KEY, tab);
    } catch {
      // per visit only
    }
  }, [tab]);

  const [dialog, setDialog] = useState<null | 'brands' | 'classify' | 'sources'>(null);
  const [sheet, setSheet] = useState<SheetTarget | null>(null);
  const [promote, setPromote] = useState<PromoteArticle | null>(null);
  const [signals, setSignals] = useState<{ uri: string; title?: string; brand_id?: number | null } | null>(null);
  const [starred, setStarred] = useState<string[]>(loadStarred);
  const toggleStar = (uri: string) =>
    setStarred((s) => {
      const next = s.includes(uri) ? s.filter((u) => u !== uri) : [...s, uri];
      saveStarred(next);
      return next;
    });

  const enabled = brands.filter((b) => b.enabled);
  const selectedBrands = useMemo(() => brands.filter((b) => config.selectedBrandIds.includes(b.id)), [brands, config.selectedBrandIds]);
  const focusBrand = selectedBrands.length === 1 ? selectedBrands[0] : enabled.find((b) => b.is_primary) ?? enabled[0] ?? null;

  const goTo = useCallback<BwContext['goTo']>((next, patch) => {
    if (patch) updateConfig(patch);
    setTab(next);
  }, [updateConfig]);

  const ctx: BwContext = {
    bw, selectedBrands, focusBrand, notify, askConfirm, goTo, voicesEnabled,
    // A story carried by several outlets opens with the other copies listed, as on the old page
    openArticle: (a) => {
      const article = { ...a, uri: a.uri, title: a.title } as SheetTarget['article'];
      setSheet({ article });
      const group = a.story_group_id as string | number | undefined;
      if (group && Number(a.story_size ?? 1) >= 2) {
        getStorySiblings(group as never, (a.brand_id as number | null | undefined) ?? null).then(
          (sibs) => setSheet((cur) => (cur?.article.uri === a.uri ? { article, related: sibs.filter((x) => x.uri !== a.uri).map((x) => ({ ...x, similarity_score: 1 })) as SheetTarget['related'] } : cur)),
          () => undefined,
        );
      }
    },
    openSignals: setSignals,
  };

  if (bw.brandsLoaded && brands.length === 0) {
    return <Onboarding notify={notify} onDone={() => { void bw.fetchBrands(); void bw.refresh(); }} />;
  }

  const picked = config.selectedBrandIds;
  const brandLabel = picked.length === 0 ? 'All brands' : picked.length === 1 ? (brands.find((b) => b.id === picked[0])?.display_name ?? 'Brand') : `${picked.length} brands`;
  const visibleTabs = SUBTABS.filter((t) => t.id !== 'voices' || voicesEnabled);

  return (
    <>
      <Panel
        title="Brand Watcher"
        description={`${brands.length} ${brands.length === 1 ? 'brand' : 'brands'} tracked${selectedBrands.length === 1 ? `, viewing ${selectedBrands[0].display_name}` : selectedBrands.length > 1 ? `, viewing ${selectedBrands.length} brands` : ''}`}
        headerAside={
          <Stack direction="row" gap="sm">
            <Popover
              label="Brands"
              align="end"
              trigger={<Button variant="secondary" iconStart={<Icon name="Target" size="sm" />} iconEnd={<Icon name="CaretDown" size="sm" />}>{brandLabel}</Button>}
            >
              <Stack gap="sm">
                <Stack direction="row" justify="between" gap="sm">
                  <Text variant="label" as="span">Brands</Text>
                  <Button variant="ghost" size="sm" disabled={!picked.length} onClick={() => updateConfig({ selectedBrandIds: [] })}>All brands</Button>
                </Stack>
                <div>
                  {enabled.map((b) => (
                    <Checkbox
                      key={b.id}
                      label={`${b.display_name}${b.is_primary ? ' (primary)' : ''}`}
                      checked={picked.includes(b.id)}
                      onCheckedChange={(on) => updateConfig({ selectedBrandIds: on ? [...picked, b.id] : picked.filter((id) => id !== b.id) })}
                    />
                  ))}
                </div>
              </Stack>
            </Popover>
            <Select label="Period" hideLabel icon="CalendarBlank" options={DAYS_OPTIONS} value={String(config.daysBack)} onValueChange={(v) => updateConfig({ daysBack: Number(v) })} />
            <IconButton icon={<Icon name="GearSix" size="sm" />} label="Brand settings" onClick={() => setDialog('brands')} />
            <IconButton icon={<Icon name="Lightning" size="sm" />} label="Classify articles" onClick={() => setDialog('classify')} />
            <IconButton icon={<Icon name="BookOpen" size="sm" />} label="Official and scholarly sources" onClick={() => setDialog('sources')} />
            <Menu
              trigger={<IconButton icon={<Icon name="DownloadSimple" size="sm" />} label="Export" disabled={bw.loading} />}
              items={exportItems(ctx)}
              onSelect={(id) => void runExport(id, ctx)}
              align="end"
              label="Export"
            />
            <IconButton icon={<Icon name="ArrowClockwise" size="sm" />} label="Refresh" disabled={bw.loading} onClick={() => void bw.refresh()} />
          </Stack>
        }
      />
      {bw.error && <Banner tone="error" title="Something didn’t load" description={bw.error} action={<Button variant="secondary" size="sm" onClick={bw.clearError}>Dismiss</Button>} />}

      {!bw.brandsLoaded ? <Skeleton variant="block" size="card" /> : (
        // The "image" export captures this element: the open sub-tab as it is on screen
        <div id={BW_EXPORT_ROOT}>
        <Tabs label="Brand Watcher sections" scrollable value={tab} onValueChange={(v) => setTab(v as BwTabId)} items={visibleTabs.map((t) => ({ value: t.id, label: t.label }))}>
          {visibleTabs.map((t) => (
            <TabPanel key={t.id} value={t.id}>
              {t.id === tab && (
                <Stack gap="lg">
                  {tab === 'dashboard' && <Dashboard {...ctx} />}
                  {tab === 'analysis' && <Analysis {...ctx} />}
                  {tab === 'perception' && <Perception {...ctx} />}
                  {tab === 'voices' && <Voices {...ctx} />}
                  {tab === 'comparison' && <Comparison {...ctx} />}
                  {tab === 'insights' && <Insights {...ctx} />}
                  {tab === 'articles' && <Articles {...ctx} />}
                  {tab === 'social' && <Social {...ctx} />}
                  {tab === 'accounts' && <Accounts {...ctx} />}
                  {tab === 'workforce' && <Workforce {...ctx} />}
                  {tab === 'incidents' && <Incidents {...ctx} />}
                  {tab === 'help' && <Help {...ctx} />}
                </Stack>
              )}
            </TabPanel>
          ))}
        </Tabs>
        </div>
      )}

      <BrandSettingsDialog open={dialog === 'brands'} onOpenChange={(o) => setDialog(o ? 'brands' : null)} ctx={ctx} />
      <ClassifyDialog open={dialog === 'classify'} onOpenChange={(o) => setDialog(o ? 'classify' : null)} ctx={ctx} />
      <SourcesDialog open={dialog === 'sources'} onOpenChange={(o) => setDialog(o ? 'sources' : null)} ctx={ctx} />
      <SignalsDialog target={signals} onClose={() => setSignals(null)} notify={notify} />
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
