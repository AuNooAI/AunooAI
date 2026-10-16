import { useMemo, useState } from 'react';
import { ConfirmDialog, type Confirm, useHashTab, useNow, useToasts } from '@aunoo/shell';
import { Banner, Button, Chip, Icon, IconButton, type IconName, Stack, Stat, Switch, TabPanel, Tabs, TextLink } from '@aunoo/ui';
import { deleteRSSFeed, fetchRSSFeed, getRecentArticlesForGroup } from '@monolith/gatherApi';
import { AppShell, errorText } from '../shell';
import { fromCollectSettings, modelOptions, type Feed } from './model';
import { ago, fmt, nextLabel, plural } from './lib';
import { jobsLabel, useActiveJobs, useFeeds, useGather } from './useGather';
import { AutoCollectDialog } from './overlays/AutoCollectDialog';
import { FeedDialog } from './overlays/FeedDialog';
import { GroupDetailsSheet } from './overlays/GroupDetailsSheet';
import { GroupSettingsDialog } from './overlays/GroupSettingsDialog';
import { ManageKeywordsDialog } from './overlays/ManageKeywordsDialog';
import { TestEnrichmentDialog } from './overlays/TestEnrichmentDialog';
import { AiPipeline } from './tabs/AiPipeline';
import { KeywordGroups } from './tabs/KeywordGroups';
import { RssFeeds } from './tabs/RssFeeds';

/** The old page re-read the feeds this long after Fetch Now. */
const FEED_REFRESH_MS = 1000;

const TABS = [
  { value: 'keywords', label: 'Keyword Groups', icon: 'MagnifyingGlass' as IconName },
  { value: 'rss', label: 'RSS Feeds', icon: 'Rss' as IconName },
  { value: 'pipeline', label: 'AI Pipeline Mgmt. & Training', icon: 'SlidersHorizontal' as IconName },
];

type DialogName = 'test' | 'autocollect' | 'keywords';

export function App() {
  const now = useNow(15000);
  const [tab, setTab] = useHashTab(TABS.map((t) => t.value), 'keywords');
  const data = useGather();
  const rss = useFeeds(tab === 'rss');
  const jobs = jobsLabel(useActiveJobs());
  const [dialog, setDialog] = useState<DialogName | null>(null);
  const [testInitial, setTestInitial] = useState<{ uri: string; groupId: string } | null>(null);
  const [detailsId, setDetailsId] = useState<string | null>(null);
  const [settingsId, setSettingsId] = useState<string | null>(null);
  const [feedDialog, setFeedDialog] = useState<Feed | 'new' | null>(null);
  const [fetching, setFetching] = useState<Set<string>>(new Set());
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const { toasts, notify } = useToasts();

  const global = data.globalSettings;
  const models = useMemo(() => modelOptions(data.models, global?.model ?? ''), [data.models, global?.model]);
  const status = data.status;
  const enabled = status?.is_enabled ?? false;

  const details = data.groups.find((g) => g.id === detailsId) ?? null;
  const settingsGroup = data.groups.find((g) => g.id === settingsId) ?? null;
  const tabLabel = TABS.find((t) => t.value === tab)!.label;
  const error = data.error ?? (tab === 'rss' ? rss.error : null);

  const updateNow = async () => {
    try {
      const r = await data.checkNow();
      notify(r?.message || (r?.success ? 'Collection started' : 'Collection didn’t start'), 'ArrowsClockwise');
    } catch (e) {
      notify(`Update failed: ${errorText(e)}`, 'WarningCircle');
    }
  };

  // The header flask opens the test with the newest article of the first group that has any
  const openTest = async (initial?: { uri: string; groupId: string }) => {
    if (initial) {
      setTestInitial(initial);
    } else {
      const first = data.groups.find((g) => g.total > 0);
      const latest = first ? await getRecentArticlesForGroup(Number(first.id), 1).catch(() => []) : [];
      setTestInitial(first && latest[0] ? { uri: latest[0].uri, groupId: first.id } : null);
    }
    setDialog('test');
  };

  const fetchFeed = async (f: Feed) => {
    setFetching((s) => new Set(s).add(f.id));
    try {
      const r = await fetchRSSFeed(Number(f.id));
      notify(r.message || `Fetching ${f.name}…`, 'ArrowsClockwise');
      window.setTimeout(() => void rss.reload(), FEED_REFRESH_MS);
    } catch (e) {
      notify(`Fetch failed: ${errorText(e)}`, 'WarningCircle');
    } finally {
      setFetching((s) => {
        const n = new Set(s);
        n.delete(f.id);
        return n;
      });
    }
  };

  return (
    <AppShell current="gather" page={tab === 'keywords' ? 'Automated Data Collection' : tabLabel} title="Gather" toasts={toasts}>
      <Tabs
        label="Gather sections"
        scrollable
        value={tab}
        onValueChange={setTab}
        items={TABS.map((t) => ({ value: t.value, label: t.label, icon: <Icon name={t.icon} size="sm" /> }))}
        header={
          <Stack gap="md">
            <Stack direction="row" justify="between" gap="md">
              <Stack direction="row" gap="sm" wrap={false}>
                <Switch
                  label="Auto-Collect"
                  checked={enabled}
                  disabled={!status}
                  onCheckedChange={async (c) => {
                    if (await data.setEnabled(c)) notify(c ? 'Auto-collect on' : 'Auto-collect off');
                  }}
                />
                <Chip size="sm" tone={enabled ? 'success' : 'muted'}>{enabled ? 'On' : 'Off'}</Chip>
                {jobs && <Chip size="sm" tone="info" icon={<Icon name="ArrowsClockwise" size="sm" />}>{jobs}</Chip>}
              </Stack>
              {status && (
                <Stack direction="row" gap="sm" label="Collection status">
                  <Stat size="compact" label="API usage" value={`${fmt(status.requests_today)}/${fmt(status.daily_limit)}`} />
                  <Stat size="compact" label="Last check" value={ago(status.last_check_time, now)} />
                  <Stat
                    size="compact"
                    label="Next check"
                    value={!enabled ? 'Off' : status.next_check_time ? nextLabel(new Date(status.next_check_time), now).replace(/^In /, '') : 'Unknown'}
                  />
                </Stack>
              )}
            </Stack>
            <Stack direction="row" justify="between" gap="md">
              <Stack direction="row" gap="sm">
                <Button iconStart={<Icon name="ArrowClockwise" size="sm" />} busy={data.checking} onClick={updateNow}>
                  {data.checking ? 'Checking…' : 'Update Now'}
                </Button>
                <Button variant="secondary" iconStart={<Icon name="GearSix" size="sm" />} disabled={!global} onClick={() => setDialog('autocollect')}>
                  Auto-Collect
                </Button>
                <Button variant="secondary" iconStart={<Icon name="ListBullets" size="sm" />} onClick={() => setDialog('keywords')}>Manage Keywords</Button>
              </Stack>
              <Stack direction="row" gap="md">
                <IconButton icon={<Icon name="Flask" size="sm" />} label="Test LLM processing on a single article" onClick={() => void openTest()} />
                <TextLink href="/submit-articles/next">Submit Articles</TextLink>
              </Stack>
            </Stack>
            {error && (
              <Banner
                tone="error"
                icon="WarningCircle"
                title="Something went wrong"
                description={error}
                action={
                  <Button variant="secondary" onClick={() => (data.error ? data.clearError() : rss.clearError())}>Dismiss</Button>
                }
              />
            )}
          </Stack>
        }
      >
        <TabPanel value="keywords">
          <KeywordGroups
            groups={data.groups}
            loading={data.loading}
            now={now}
            onOpenDetails={setDetailsId}
            onOpenSettings={setSettingsId}
            onCreate={() => setDialog('keywords')}
            onDeleteUnscored={(id) => {
              const g = data.groups.find((x) => x.id === id)!;
              setConfirm({
                title: 'Delete unscored articles?',
                message: `${plural(g.unscored, 'unscored article')} in “${g.name}” will be deleted. Scored articles are kept. This can’t be undone.`,
                action: 'Delete articles',
                onConfirm: async () => {
                  if (await data.deleteUnscored(id)) notify(`${plural(g.unscored, 'unscored article')} deleted`, 'Trash');
                },
              });
            }}
          />
        </TabPanel>
        <TabPanel value="rss">
          <RssFeeds
            feeds={rss.feeds}
            loading={rss.loading}
            monitor={rss.monitor}
            now={now}
            fetching={fetching}
            onAdd={() => setFeedDialog('new')}
            onEdit={setFeedDialog}
            onFetch={(f) => void fetchFeed(f)}
            onDelete={(f) =>
              setConfirm({
                title: 'Delete feed?',
                message: `“${f.name}” will stop being fetched. Articles already collected are kept. This can’t be undone.`,
                action: 'Delete feed',
                onConfirm: async () => {
                  try {
                    await deleteRSSFeed(Number(f.id));
                    notify(`“${f.name}” deleted`, 'Trash');
                    await rss.reload();
                  } catch (e) {
                    notify(`Couldn’t delete “${f.name}”: ${errorText(e)}`, 'WarningCircle');
                  }
                },
              })
            }
          />
        </TabPanel>
        <TabPanel value="pipeline">
          <AiPipeline active={tab === 'pipeline'} notify={notify} askConfirm={setConfirm} />
        </TabPanel>
      </Tabs>

      <TestEnrichmentDialog
        open={dialog === 'test'}
        onOpenChange={(o) => setDialog(o ? 'test' : null)}
        groups={data.groups}
        initial={testInitial}
        onSuccess={() => void data.reload()}
      />
      {global && data.settings && (
        <AutoCollectDialog
          open={dialog === 'autocollect'}
          onOpenChange={(o) => setDialog(o ? 'autocollect' : null)}
          settings={global}
          providers={data.providers}
          models={models}
          onSave={async (s) => {
            if (await data.saveSettings(fromCollectSettings(s, data.settings!))) notify('Auto-collect settings saved');
          }}
        />
      )}
      <ManageKeywordsDialog
        open={dialog === 'keywords'}
        onOpenChange={(o) => setDialog(o ? 'keywords' : null)}
        groups={data.groups}
        topics={data.topics}
        onCreateGroup={async (name, topic) => {
          if (await data.createGroup(name, topic)) notify(`Group “${name}” created — add keywords to start collecting`);
        }}
        onAddKeyword={async (id, text) => {
          if (await data.addKeyword(id, text)) notify(`Keyword “${text}” added`);
        }}
        onRemoveKeyword={async (_groupId, keywordId) => {
          if (await data.removeKeyword(keywordId)) notify('Keyword removed', 'Trash');
        }}
        onDeleteGroup={async (id) => {
          const name = data.groups.find((g) => g.id === id)?.name;
          if (await data.deleteGroup(id)) notify(`“${name}” deleted`, 'Trash');
        }}
        askConfirm={setConfirm}
      />
      <GroupDetailsSheet
        group={details}
        onClose={() => setDetailsId(null)}
        onAddKeyword={async (id, text) => {
          if (await data.addKeyword(id, text)) notify(`Keyword “${text}” added`);
        }}
        onEditKeyword={async (keywordId, text) => {
          if (await data.editKeyword(keywordId, text)) notify(`Keyword changed to “${text}”`);
        }}
        onRemoveKeyword={async (keywordId) => {
          if (await data.removeKeyword(keywordId)) notify('Keyword removed', 'Trash');
        }}
        onDeleteGroup={async (id) => {
          const name = data.groups.find((g) => g.id === id)?.name;
          if (await data.deleteGroup(id)) notify(`“${name}” deleted`, 'Trash');
        }}
        onRunCheck={(id) => data.checkNow(id)}
        checking={data.checking}
        onTestArticle={(uri, groupId) => void openTest({ uri, groupId })}
        onKeywordsChanged={() => void data.reload()}
        askConfirm={setConfirm}
        notify={notify}
      />
      {global && (
        <GroupSettingsDialog
          group={settingsGroup}
          onClose={() => setSettingsId(null)}
          global={global}
          providers={data.providers}
          models={models}
          onSaved={() => {
            notify('Group settings saved');
            void data.reload();
          }}
        />
      )}
      <FeedDialog
        feed={feedDialog}
        onClose={() => setFeedDialog(null)}
        topics={data.topics}
        onSaved={(name, created) => {
          notify(created ? `“${name}” added — first fetch in a minute` : `“${name}” updated`, 'Rss');
          void rss.reload();
        }}
      />
      <ConfirmDialog confirm={confirm} onClose={() => setConfirm(null)} />
    </AppShell>
  );
}
