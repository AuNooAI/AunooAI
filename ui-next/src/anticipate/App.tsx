import { useCallback, useEffect, useRef, useState } from 'react';
import { ConfirmDialog, type Confirm, useToasts } from '@aunoo/shell';
import { Icon, Stack, TabPanel, Tabs, type SelectOption } from '@aunoo/ui';
import { deleteDashboard, listDashboardsForTopic, loadDashboard, type SavedDashboardSummary } from '@monolith/api';
import { AppShell, errorText } from '../shell';
import { RefsContext } from './components/CitedText';
import { savePng, slug } from './lib/download';
import { BACKEND_TAB, type Payload } from './lib/model';
import { TABS, tabById } from './lib/tabs';
import { useAnalysis } from './lib/useAnalysis';
import { useTabPrefs } from './lib/useTabPrefs';
import { useTabRoute } from './lib/useTabRoute';
import { useWorkspace } from './lib/useWorkspace';
import { ConfigureDialog } from './overlays/ConfigureDialog';
import { ManageTabsPopover } from './overlays/ManageTabsPopover';
import { ProfilesDialog } from './overlays/ProfilesDialog';
import { RawDialog } from './overlays/RawDialog';
import { ReferencesDialog } from './overlays/ReferencesDialog';
import { SaveDialog } from './overlays/SaveDialog';
import { TuneDialog } from './overlays/TuneDialog';
import { ActionToolbar, type ToolbarAction } from './shell/ActionToolbar';
import { ContextRow } from './shell/ContextRow';
import { renderView } from './views';

const NEW = 'new';

/** "dd.mm.yyyy" from the run's cache info, else its generated time. */
const lastUpdatedOf = (d: Record<string, unknown> | null) => {
  const info = d?._cache_info as { last_updated?: string } | undefined;
  if (info?.last_updated) return info.last_updated;
  const at = typeof d?.generated_at === 'string' ? new Date(d.generated_at) : null;
  return at && !Number.isNaN(at.getTime()) ? at.toLocaleDateString('en-GB').replace(/\//g, '.') : undefined;
};

export function App() {
  const [tabId, navigate] = useTabRoute();
  const tab = tabById(tabId) ?? TABS[0];
  const backendTab = tab.built ? BACKEND_TAB[tab.id] : undefined;
  const { prefs, setOrder, setVisible } = useTabPrefs();
  const ws = useWorkspace();
  const { config, setConfig } = ws;
  // A saved analysis, once opened, stays open across the analysis tabs, each showing its own part
  const [savedDash, setSavedDash] = useState<Record<string, unknown> | null>(null);
  const savedTab = savedDash && backendTab ? (savedDash[`${backendTab}_data`] as Payload | null | undefined) : undefined;
  const analysis = useAnalysis(backendTab, config, ws.ready, savedDash ? (savedTab && Object.keys(savedTab).length ? savedTab : null) : undefined);
  const profile = ws.profiles.find((p) => p.id === config.profileId);

  const [saved, setSaved] = useState<SavedDashboardSummary[]>([]);
  const [savedId, setSavedId] = useState(NEW);
  const viewRef = useRef<HTMLDivElement>(null);
  const [dialog, setDialog] = useState<null | 'configure' | 'tune' | 'raw' | 'references' | 'save' | 'profiles'>(null);
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const { toasts, notify } = useToasts();

  const loadSaved = useCallback(() => {
    if (!config.topic) return;
    listDashboardsForTopic(config.topic).then(setSaved, () => setSaved([]));
  }, [config.topic]);
  useEffect(() => {
    setSavedId(NEW);
    setSavedDash(null);
    loadSaved();
  }, [loadSaved]);
  // A saved analysis belongs to one tab; switching tab goes back to the live one

  const openSaved = async (value: string) => {
    setSavedId(value);
    if (value === NEW) {
      setSavedDash(null);
      return;
    }
    try {
      const d = (await loadDashboard(Number(value))) as unknown as Record<string, unknown>;
      setSavedDash(d);
      const tabData = backendTab ? (d[`${backendTab}_data`] as Record<string, unknown> | undefined) : undefined;
      notify(tabData && Object.keys(tabData).length ? `Loaded “${String(d.name)}”` : `“${String(d.name)}” has no ${tab.label} analysis`, 'BookmarkSimple');
    } catch (e) {
      notify(`Couldn’t load it: ${errorText(e)}`, 'WarningCircle');
    }
  };

  const savedOptions: SelectOption[] = [
    { value: NEW, label: 'Latest analysis' },
    ...saved.map((s) => ({
      value: String(s.id),
      label: `${s.name}${s.articles_analyzed ? ` · ${s.articles_analyzed} articles` : ''}${(s as { auto_generated?: boolean }).auto_generated ? ' · auto' : ''}`,
    })),
  ];

  const onAction = (action: ToolbarAction) => {
    if (action === 'configure' || action === 'tune' || action === 'raw' || action === 'references' || action === 'save') setDialog(action);
    else if (action === 'pdf') window.print();
    else if (action === 'png') {
      if (!viewRef.current) return;
      savePng(viewRef.current, `${slug(tab.label)}-${slug(config.topic)}.png`).catch((e) => notify(`Couldn’t save the image: ${errorText(e)}`, 'WarningCircle'));
    }
    else if (action === 'delete') {
      const s = saved.find((x) => String(x.id) === savedId);
      if (!s) return;
      setConfirm({
        title: 'Delete saved analysis?',
        message: `“${s.name}” will be deleted. This can’t be undone.`,
        action: 'Delete',
        onConfirm: async () => {
          try {
            await deleteDashboard(s.id);
            notify(`“${s.name}” deleted`, 'Trash');
            setSavedId(NEW);
            setSavedDash(null);
            loadSaved();
          } catch (e) {
            notify(`Couldn’t delete it: ${errorText(e)}`, 'WarningCircle');
          }
        },
      });
    }
  };

  const visibleTabs = prefs.order.filter((id) => !prefs.hidden.includes(id)).map((id) => tabById(id)!).filter(Boolean);
  const data = analysis.data;

  return (
    <AppShell
      current="anticipate"
      page={tab.label}
      navActions={<ManageTabsPopover order={prefs.order} hidden={prefs.hidden} activeTab={tab.id} onReorder={setOrder} onVisibleChange={setVisible} />}
      title="Anticipate"
      toasts={toasts}
    >
      <Tabs
        label="Anticipate views"
        scrollable
        sticky
        value={tab.id}
        onValueChange={navigate}
        items={visibleTabs.map((t) => ({ value: t.id, label: t.label, icon: <Icon name={t.icon} size="sm" /> }))}
        subheader={
          <Stack gap="sm">
            <ContextRow
              topic={config.topic}
              topics={ws.topics}
              onTopicChange={(topic) => setConfig({ topic })}
              saved={savedId}
              savedOptions={savedOptions}
              onSavedChange={(v) => void openSaved(v)}
              lastUpdated={savedId === NEW ? lastUpdatedOf(data) : undefined}
              generateLabel="Refresh analysis (bypass cache)"
              busy={analysis.status === 'generating'}
              canGenerate={Boolean(backendTab)}
              onGenerate={() => void analysis.generate(true)}
            />
            {backendTab && (
              <ActionToolbar
                tune={backendTab !== 'horizons'}
                hasData={Boolean(data)}
                savedLoaded={savedId !== NEW}
                onAction={onAction}
              />
            )}
          </Stack>
        }
      >
        {visibleTabs.map((t) => (
          <TabPanel key={t.id} value={t.id}>
            <RefsContext.Provider value={analysis.refs}>
              {/* Unstyled wrapper: the PNG export captures what's inside it */}
              <div ref={t.id === tab.id ? viewRef : undefined}>
                <Stack gap="lg">
                  {t.id === tab.id &&
                    renderView({ tab, config, analysis, notify, navigate, setTopic: (topic) => setConfig({ topic }), askConfirm: setConfirm, openConfigure: () => setDialog('configure') })}
                </Stack>
              </div>
            </RefsContext.Provider>
          </TabPanel>
        ))}
      </Tabs>

      <ConfigureDialog
        open={dialog === 'configure'}
        onOpenChange={(o) => setDialog(o ? 'configure' : null)}
        config={config}
        topics={ws.topics}
        models={ws.models}
        profiles={ws.profiles}
        onManageProfiles={() => setDialog('profiles')}
        onSave={(c) => { setConfig(c); notify('Settings saved'); }}
        onGenerate={(c) => {
          setConfig(c);
          // Let the new settings land before generating with them
          window.setTimeout(() => void analysis.generate(), 0);
        }}
      />
      <ProfilesDialog
        open={dialog === 'profiles'}
        onOpenChange={(o) => setDialog(o ? 'profiles' : 'configure')}
        profiles={ws.profiles}
        initialId={config.profileId}
        onChanged={async (id) => {
          const list = await ws.reloadProfiles();
          if (id != null) setConfig({ profileId: id });
          // The selected profile was deleted: fall back to the default, as on first load
          else if (!list.some((p) => p.id === config.profileId)) setConfig({ profileId: (list.find((p) => p.is_default) ?? list[0])?.id ?? null });
        }}
        notify={notify}
        askConfirm={setConfirm}
      />
      {backendTab && (
        <>
          <TuneDialog
            open={dialog === 'tune'}
            onOpenChange={(o) => setDialog(o ? 'tune' : null)}
            tabLabel={tab.label}
            backendTab={backendTab}
            topic={config.topic}
            profile={profile}
            notify={notify}
            onSaved={() => void analysis.generate(true)}
          />
          <RawDialog
            open={dialog === 'raw'}
            onOpenChange={(o) => setDialog(o ? 'raw' : null)}
            backendTab={backendTab}
            analysisId={data?.analysis_id}
            fallbackModel={data?.model_used}
            onCopy={() => notify('JSON copied')}
          />
          <ReferencesDialog open={dialog === 'references'} onOpenChange={(o) => setDialog(o ? 'references' : null)} refs={analysis.refs} name={`${tab.id}-${config.topic}`} />
          <SaveDialog
            open={dialog === 'save'}
            onOpenChange={(o) => setDialog(o ? 'save' : null)}
            config={config}
            backendTab={backendTab}
            data={data}
            profile={profile}
            onSaved={(name) => {
              notify(`Saved as “${name}”`, 'BookmarkSimple');
              loadSaved();
            }}
          />
        </>
      )}
      <ConfirmDialog confirm={confirm} onClose={() => setConfirm(null)} />
    </AppShell>
  );
}
