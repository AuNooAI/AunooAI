import { useCallback, useEffect, useMemo, useState } from 'react';
import { Banner, Button, EmptyState, Icon, IconButton, Menu, Panel, Select, Skeleton, Stack, TabPanel, Tabs, Text } from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import {
  datasetCsvUrl, exportBundleUrl, feedUrl, getCollectionPlan, getDrilldown, getMarkets, getOverview, getPulse, getReportLink,
  getSourceHealth, getVendors, reportUrl,
  type CollectionPlan, type DrilldownVendor, type Market, type MarketOverview, type MarketPulse, type SourceHealth, type Vendor,
} from '@monolith/marketMonitorApi';
import { errorText } from '../../shell';
import { PERIOD_OPTIONS, usesPeriod, type CollectionSub, type MmContext, type MmView, type SettingsPanel } from './context';
import { vendorColoursFrom } from './shared/colours';
import { RecordsDialog, type DrilldownSpec } from './shared/Records';
import { LinkButton, SortTable, VendorLink } from './shared/SortTable';
import { SettingsSheet } from './settings/SettingsSheet';
import { Analysis } from './views/Analysis';
import { Briefings } from './views/Briefings';
import { Collection } from './views/Collection';
import { Findings } from './views/Findings';
import { Horizon } from './views/Horizon';
import { Vendors } from './views/Vendors';
import { Voices } from './views/Voices';
import { VendorPage } from './vendor/VendorPage';

/*
 * Market Monitor on the routes the old tab uses (/api/market-monitor/*, see
 * ui/src/components/newsfeed/MarketMonitorTab.tsx). A market is a tracked vendor portfolio built on
 * Brand Watcher brands. The frame picks the market and the period and loads what several views
 * share; each view loads the rest itself while it's open. A vendor page and a vendor list behind a
 * figure live in the URL (?vendor=, ?drill=) so they survive a refresh and can be sent to somebody.
 */

const VIEWS: { id: MmView; label: string }[] = [
  { id: 'findings', label: 'Findings' },
  { id: 'analysis', label: 'Analysis' },
  { id: 'voices', label: 'Top voices' },
  { id: 'horizon', label: 'Market Maturity Map' },
  { id: 'collection', label: 'Collection' },
  { id: 'briefings', label: 'Reports' },
  { id: 'vendors', label: 'Vendors' },
];

/** What each vendor list behind a figure is, in words */
const DRILL_LABEL: Record<string, string> = {
  quiet: 'Vendors with no observed activity: no posts, no job listings, no matched coverage',
  watched: 'Vendors we are collecting for',
  paused: 'Vendors in the registry with collection switched off',
  observed: 'Vendors we have read at least once',
  unobserved: 'Vendors we have never read',
  disclosed: 'Vendors with a disclosed funding amount on file',
  undisclosed: 'Vendors with no disclosed funding amount on file',
  no_linkedin: 'Vendors with no LinkedIn page on file',
  posting: 'Vendors that have announced something',
  hiring: 'Vendors with open job listings',
};

const MARKET_KEY = 'aunoo.mm.market';
const VIEW_KEY = 'aunoo.mm.view';
const readStored = (k: string) => {
  try {
    return localStorage.getItem(k);
  } catch {
    return null;
  }
};
const store = (k: string, v: string) => {
  try {
    localStorage.setItem(k, v);
  } catch {
    // per visit only
  }
};

const queryParam = (name: string) => new URLSearchParams(window.location.search).get(name);
function setQueryParam(name: string, value: string | null) {
  const url = new URL(window.location.href);
  if (value === null) url.searchParams.delete(name);
  else url.searchParams.set(name, value);
  window.history.pushState({}, '', url.toString());
}
const numParam = (name: string) => {
  const v = queryParam(name);
  return v && /^\d+$/.test(v) ? Number(v) : null;
};

interface Props {
  notify: (m: string) => void;
  askConfirm: (c: Confirm) => void;
}

export function MarketMonitor({ notify, askConfirm }: Props) {
  const [markets, setMarkets] = useState<Market[] | null>(null);
  const [marketId, setMarketId] = useState<number | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [view, setView] = useState<MmView>(() => (VIEWS.some((v) => v.id === readStored(VIEW_KEY)) ? (readStored(VIEW_KEY) as MmView) : 'findings'));
  const [sub, setSub] = useState<CollectionSub>('overview');
  const [periodDays, setPeriodDays] = useState(30);
  const [settings, setSettings] = useState<SettingsPanel | null>(null);
  const [records, setRecords] = useState<DrilldownSpec | null>(null);
  const [openVendor, setOpenVendor] = useState<number | null>(() => numParam('vendor'));
  const [drill, setDrill] = useState<string | null>(() => queryParam('drill'));
  const [drillRows, setDrillRows] = useState<DrilldownVendor[] | null>(null);

  const [vendors, setVendors] = useState<Vendor[] | null>(null);
  const [overview, setOverview] = useState<MarketOverview | null>(null);
  const [pulse, setPulse] = useState<MarketPulse | null>(null);
  const [plan, setPlan] = useState<CollectionPlan | null>(null);
  const [health, setHealth] = useState<SourceHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [shareLink, setShareLink] = useState<string | null>(null);

  useEffect(() => store(VIEW_KEY, view), [view]);
  // Back and forward move between a vendor page, a vendor list and the market
  useEffect(() => {
    const onPop = () => {
      setOpenVendor(numParam('vendor'));
      setDrill(queryParam('drill'));
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  useEffect(() => {
    getMarkets().then(
      (list) => {
        setMarkets(list);
        const remembered = Number(readStored(MARKET_KEY));
        setMarketId(list.find((m) => m.id === remembered)?.id ?? list[0]?.id ?? null);
      },
      (e) => setLoadError(errorText(e)),
    );
  }, []);
  useEffect(() => {
    if (marketId !== null) store(MARKET_KEY, String(marketId));
  }, [marketId]);

  const reload = useCallback(() => {
    if (marketId === null) return;
    setError(null);
    Promise.all([getVendors(marketId), getCollectionPlan(marketId, 'funded'), getSourceHealth(marketId), getOverview(marketId, periodDays), getPulse(marketId, Math.min(periodDays, 90))]).then(
      ([v, p, h, o, b]) => {
        setVendors(v);
        setPlan(p);
        setHealth(h);
        setOverview(o);
        setPulse(b);
      },
      (e) => setError(errorText(e)),
    );
  }, [marketId, periodDays]);
  // The pulse route accepts at most 90 days; the old tab asked for 365 and got a 422, so the whole
  // reload failed on "Last 365 days". The pulse caption states the window it actually covers.
  useEffect(() => reload(), [reload]);
  // The Explore filter bar's Refresh button
  useEffect(() => {
    window.addEventListener('explore:refresh', reload);
    return () => window.removeEventListener('explore:refresh', reload);
  }, [reload]);

  useEffect(() => {
    if (marketId === null || !drill) {
      setDrillRows(null);
      return;
    }
    let live = true;
    setDrillRows(null);
    getDrilldown(marketId, drill).then((r) => live && setDrillRows(r.vendors), (e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, [marketId, drill]);

  const colours = useMemo(() => vendorColoursFrom(vendors), [vendors]);
  const market = markets?.find((m) => m.id === marketId) ?? null;

  const openVendorPage = useCallback((id: number) => {
    setQueryParam('vendor', String(id));
    setOpenVendor(id);
  }, []);
  const closeVendorPage = () => {
    setQueryParam('vendor', null);
    setOpenVendor(null);
  };
  const openDrill = useCallback((name: string) => {
    setQueryParam('drill', name);
    setDrill(name);
  }, []);
  const closeDrill = () => {
    setQueryParam('drill', null);
    setDrill(null);
  };
  const goTo = useCallback((v: MmView, s?: CollectionSub) => {
    setView(v);
    if (s) setSub(s);
  }, []);

  const makeShareLink = async () => {
    if (marketId === null) return;
    setBusy(true);
    try {
      const r = await getReportLink(marketId, periodDays);
      setShareLink(r.url);
      await navigator.clipboard?.writeText(r.url).catch(() => undefined);
      notify(`Report link copied. It opens without a login and expires in ${r.ttl_days} days.`);
    } catch (e) {
      notify(`Couldn’t create a link: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };

  if (loadError && !markets) return <Banner tone="error" title="Markets didn’t load" description={loadError} />;
  if (!markets) return <Skeleton variant="block" size="card" />;
  if (!markets.length || !market || marketId === null) {
    return (
      <Panel title="Market Monitor">
        <EmptyState icon="ChartLineUp" title="No markets yet">Create one, then import a vendor registry to fill it.</EmptyState>
      </Panel>
    );
  }

  const ctx: MmContext = {
    marketId, market, periodDays, vendors, overview, pulse, plan, health, colours, reload, notify, askConfirm,
    openVendor: openVendorPage, openDrill, openRecords: setRecords, goTo, openSettings: setSettings,
  };

  const exportMenu = (
    <Menu
      label="Export and share"
      align="end"
      trigger={<Button variant="secondary" iconStart={<Icon name="DownloadSimple" size="sm" />} iconEnd={<Icon name="CaretDown" size="sm" />}>Export</Button>}
      items={[
        { id: 'csv', label: 'Dataset (CSV)', icon: 'Table' },
        { id: 'rss', label: 'RSS feed', icon: 'Rss' },
        { id: 'report', label: 'Report (HTML)', icon: 'FileText' },
        { id: 'zip', label: 'Everything (ZIP)', icon: 'Folder' },
        { id: 'share', label: 'Copy a share link', icon: 'Link', separatorBefore: true, disabled: busy },
      ]}
      onSelect={(id) => {
        if (id === 'share') void makeShareLink();
        else if (id === 'csv') window.location.href = datasetCsvUrl(marketId);
        else if (id === 'zip') window.location.href = exportBundleUrl(marketId);
        else window.open(id === 'rss' ? feedUrl(marketId) : reportUrl(marketId, periodDays), '_blank', 'noopener');
      }}
    />
  );

  const header = (
    <Panel
      className="mm-header"
      title="Market Monitor"
      description={market.question ?? undefined}
      headerAside={
        <Stack direction="row" gap="sm">
          {markets.length > 1 && (
            <Select label="Market" hideLabel icon="ChartLineUp" options={markets.map((m) => ({ value: String(m.id), label: m.name }))} value={String(marketId)} onValueChange={(v) => { setMarketId(Number(v)); closeDrill(); }} />
          )}
          {usesPeriod(view, sub) && !openVendor && (
            <Select label="Period" hideLabel icon="CalendarBlank" options={PERIOD_OPTIONS} value={String(periodDays)} onValueChange={(v) => setPeriodDays(Number(v))} />
          )}
          {(view === 'findings' || view === 'analysis') && !openVendor && exportMenu}
          <IconButton icon={<Icon name="GearSix" size="sm" />} label="Collection, sources and health" onClick={() => setSettings('collection')} />
          <IconButton icon={<Icon name="ArrowClockwise" size="sm" />} label="Refresh" onClick={reload} />
        </Stack>
      }
    >
      <Stack gap="sm">
        {markets.length === 1 && <Text variant="label">{market.name}</Text>}
        {(view === 'findings' || view === 'analysis') && (pulse || overview) && (
          <Text variant="caption">
            {pulse
              ? `Last ${pulse.period_days} days · ${pulse.coverage.watching} of ${pulse.coverage.vendors} vendors monitored`
              : `${overview!.coverage.watching} of ${overview!.coverage.vendors} vendors monitored`}
          </Text>
        )}
        {shareLink && <Text variant="caption">Shareable report link: {shareLink}</Text>}
      </Stack>
    </Panel>
  );

  return (
    <>
      {header}
      {error && <Banner tone="error" title="Something didn’t load" description={error} action={<Button variant="secondary" size="sm" onClick={() => setError(null)}>Dismiss</Button>} />}
      {/* Whether anything arrives at all; shown on every view so an empty Findings explains itself */}
      {plan && !plan.existing && (
        <Banner
          tone="warning"
          title="No collection configured"
          description="This market has no keyword group, so no articles are being gathered. Set the search terms in Collection settings."
          action={<Button variant="secondary" size="sm" onClick={() => setSettings('collection')}>Open collection settings</Button>}
        />
      )}

      {openVendor !== null ? (
        <VendorPage ctx={ctx} brandId={openVendor} onBack={closeVendorPage} />
      ) : (
        <>
          {drill && (
            <Panel
              title={DRILL_LABEL[drill] ?? drill}
              description={drillRows ? `${drillRows.length} vendors` : undefined}
              headerAside={<IconButton icon={<Icon name="X" size="sm" />} label="Close this list" onClick={closeDrill} />}
            >
              {drillRows === null ? <Skeleton variant="text" lines={5} /> : (
                <SortTable
                  caption={DRILL_LABEL[drill] ?? drill}
                  rows={drillRows}
                  rowKey={(v) => v.brand_id}
                  initialSort="vendor"
                  emptyText="No vendors match."
                  columns={[
                    { key: 'vendor', label: 'Vendor', rowHeader: true, render: (v) => <VendorLink id={v.brand_id} name={v.vendor} color={colours.byId(v.brand_id)} onOpen={openVendorPage} /> },
                    { key: 'country', label: 'Country', groupable: true },
                    { key: 'founded', label: 'Founded', groupable: true },
                    { key: 'funding_status', label: 'Funding', groupable: true, value: (v) => v.musd ?? v.funding_status, render: (v) => (v.musd !== null ? `$${v.musd}M` : v.funding_status ?? '—') },
                    { key: 'staff', label: 'Staff', align: 'end' },
                    // All-time, unlike the period-scoped figures above; the label says so
                    { key: 'announcements', label: 'Announced (all time)', align: 'end' },
                    {
                      key: 'openings', label: 'Open roles', align: 'end',
                      // A zero is a measured zero (both job collectors ran), so it's printed, not dashed
                      render: (v) => (v.openings ? <LinkButton onClick={() => setRecords({ kind: 'jobs', title: `${v.vendor}: job listings`, vendorId: v.brand_id, expectedTotal: v.openings })}>{v.openings}</LinkButton> : '0'),
                    },
                  ]}
                />
              )}
            </Panel>
          )}

          <Tabs
            label="Market Monitor views"
            scrollable
            value={view}
            onValueChange={(v) => setView(v as MmView)}
            items={VIEWS.map((v) => ({ value: v.id, label: v.id === 'vendors' && market.vendors ? `Vendors (${market.vendors})` : v.label }))}
          >
            {VIEWS.map((v) => (
              <TabPanel key={v.id} value={v.id}>
                {v.id === view && (
                  <Stack gap="lg">
                    {view === 'findings' && <Findings {...ctx} />}
                    {view === 'analysis' && <Analysis {...ctx} />}
                    {view === 'voices' && <Voices {...ctx} />}
                    {view === 'horizon' && <Horizon {...ctx} />}
                    {view === 'collection' && <Collection ctx={ctx} sub={sub} onSub={setSub} />}
                    {view === 'briefings' && <Briefings {...ctx} />}
                    {view === 'vendors' && <Vendors {...ctx} />}
                  </Stack>
                )}
              </TabPanel>
            ))}
          </Tabs>
        </>
      )}

      <SettingsSheet ctx={ctx} panel={settings} onPanel={setSettings} onMarketsChanged={() => getMarkets().then(setMarkets, () => undefined)} />
      <RecordsDialog marketId={marketId} spec={records} onClose={() => setRecords(null)} onVendor={(id) => { setRecords(null); openVendorPage(id); }} />
    </>
  );
}
