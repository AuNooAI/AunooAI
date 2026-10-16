import { useCallback, useEffect, useState } from 'react';
import { Banner, Button, Grid, Icon, Panel, Select, Skeleton, Stack, Stat, Table, Text, TextField } from '@aunoo/ui';
import { api, errorText } from '../../shell';
import type { SettingsPageProps } from '../types';
import { fmtDate, fmtSize, getActiveDatabase, getDatabases, getDbHealth, getDbInfo, saveFile, today, type DbEntry, type DbInfo } from './api';
import { ArticleImportDialog, TopicImportDialog } from './ImportDialogs';

/*
 * The database, as the old Database tab: what's in it, backups, clean-ups, clearing a topic's
 * articles, resets, and exports and imports of topic settings and articles. Creating, switching and
 * downloading database files only applies to SQLite sites; a PostgreSQL site manages those with
 * its own tools, as the old page said.
 */

type Busy = null | string;

export function DatabaseTab({ notify, askConfirm }: SettingsPageProps) {
  const [info, setInfo] = useState<DbInfo | null>(null);
  const [infoError, setInfoError] = useState<string | null>(null);
  const [stuck, setStuck] = useState(0);
  const [dbs, setDbs] = useState<DbEntry[]>([]);
  const [active, setActive] = useState('');
  const [topics, setTopics] = useState<string[]>([]);
  const [clearTopic, setClearTopic] = useState('');
  const [busy, setBusy] = useState<Busy>(null);
  const [dialog, setDialog] = useState<null | 'topics' | 'articles'>(null);

  const loadInfo = useCallback(async () => {
    setInfoError(null);
    try {
      const d = await getDbInfo();
      setInfo(d);
      if ((d.db_type || 'sqlite') === 'postgresql') {
        getDbHealth().then((h) => setStuck(h.stuck_transactions ?? 0), () => setStuck(0));
      } else {
        getDatabases().then(setDbs, () => setDbs([]));
        getActiveDatabase().then((a) => setActive(a.name ?? ''), () => undefined);
      }
    } catch (e) {
      setInfoError(errorText(e));
    }
  }, []);
  useEffect(() => {
    void loadInfo();
    api<{ name: string }[]>('/api/topics').then((t) => setTopics((t ?? []).map((x) => x.name)), () => setTopics([]));
  }, [loadInfo]);

  const sqlite = (info?.db_type || 'sqlite') !== 'postgresql';

  /** Runs one action with a busy marker and a notice either way */
  const run = async (id: string, fn: () => Promise<string | void>) => {
    setBusy(id);
    try {
      const msg = await fn();
      if (msg) notify(msg);
    } catch (e) {
      notify(`Didn’t work: ${errorText(e)}`);
    } finally {
      setBusy(null);
    }
  };
  const confirmRun = (id: string, title: string, message: React.ReactNode, action: string, fn: () => Promise<string | void>) =>
    askConfirm({ title, message, action, onConfirm: () => void run(id, fn) });

  const switchDb = (name: string) =>
    run('switch', async () => {
      await api('/api/active-database', { method: 'POST', json: { name } });
      setActive(name);
      await loadInfo();
      return `Switched to ${name}`;
    });

  const exportJson = (id: string, path: string, file: string, count?: (d: { total_articles?: number }) => string) =>
    run(id, async () => {
      const data = await api<Record<string, unknown>>(path);
      saveFile(`${file}-${today()}.json`, JSON.stringify(data, null, 2));
      return count ? count(data as { total_articles?: number }) : 'Exported';
    });

  return (
    <Grid columns="main-aside" stackAt="wide" gap="md">
      <Stack gap="lg">
        {info && (sqlite ? (
          <Banner tone="info" title="SQLite database" description="This site stores its data in database files. You can create, switch and download them here." />
        ) : (
          <Banner
            tone={stuck > 0 ? 'warning' : 'info'}
            title="PostgreSQL database"
            description={
              <>
                This site uses PostgreSQL. Create, switch and download databases with PostgreSQL’s own tools (psql, pgAdmin).
                {' '}Connection: {info.host || 'localhost'}:{info.port || 5432}/{info.name}. Connection pool: 20 base + 10 overflow = 30 at once.
                {stuck > 0 && ` ${stuck} stuck transaction${stuck === 1 ? '' : 's'} found; they end on their own after 60 seconds.`}
              </>
            }
          />
        ))}

        {info && sqlite && <SqliteDatabases dbs={dbs} active={active} busy={busy} onSwitch={switchDb} notify={notify} askConfirm={askConfirm} reload={loadInfo} />}

        <Panel title="Backups and reset" description="Back up the current database, or delete everything in it.">
          <Stack direction="row" gap="sm">
            <Button variant="secondary" iconStart={<Icon name="DownloadSimple" size="sm" />} busy={busy === 'backup'} disabled={!!busy}
              onClick={() => confirmRun('backup', 'Back up the database?', sqlite ? 'A copy of the database file is made on the server.' : 'A PostgreSQL backup (pg_dump) is written on the server.', 'Back up', async () => {
                const r = await api<{ message?: string }>('/api/databases/backup', { method: 'POST' });
                return r?.message || 'Backup made';
              })}>Back up</Button>
            <Button variant="danger" iconStart={<Icon name="Trash" size="sm" />} busy={busy === 'reset'} disabled={!!busy}
              onClick={() => confirmRun('reset', 'Delete all data in this database?', 'Every article, tag and report is deleted. This can’t be undone; make a backup first if you might need any of it.', 'Delete everything', async () => {
                const r = await api<{ message?: string }>('/api/databases/reset', { method: 'POST' });
                await loadInfo();
                return r?.message || 'Database reset';
              })}>Reset database</Button>
          </Stack>
        </Panel>

        <Panel title="Clean-up" description="Remove data left behind by deleted topics: topic records with no topic, and articles that belong to no active topic.">
          <Stack direction="row" gap="sm">
            <Button variant="secondary" iconStart={<Icon name="Sparkle" size="sm" />} busy={busy === 'clean-all'} disabled={!!busy}
              onClick={() => confirmRun('clean-all', 'Clean up everything left behind?', 'Orphaned topic data and orphaned articles are deleted, with their alerts.', 'Clean up', async () => {
                const r = await api<CleanAll>('/api/keyword-monitor/clean-all-orphaned', { method: 'POST' });
                if (r.status === 'error') throw new Error(r.message || 'Clean-up failed');
                await loadInfo();
                return cleanAllSummary(r);
              })}>Clean up all</Button>
            <Button variant="secondary" busy={busy === 'clean-topics'} disabled={!!busy}
              onClick={() => confirmRun('clean-topics', 'Clean up orphaned topics?', 'Keyword groups, keywords and alerts for topics that no longer exist are deleted.', 'Clean up topics', async () => {
                const r = await api<{ orphaned_topics?: string[] }>('/api/keyword-monitor/clean-orphaned-topics', { method: 'POST' });
                await loadInfo();
                return r?.orphaned_topics?.length ? `Cleaned up ${r.orphaned_topics.length} orphaned topics` : 'No orphaned topics found';
              })}>Clean up topics</Button>
            <Button variant="secondary" busy={busy === 'clean-articles'} disabled={!!busy}
              onClick={() => confirmRun('clean-articles', 'Delete orphaned articles?', 'Articles that no longer belong to an active topic are deleted, with their alerts.', 'Delete orphaned articles', async () => {
                const r = await api<{ orphaned_count?: number; alerts_deleted?: number }>('/api/keyword-monitor/clean-orphaned-articles', { method: 'POST' });
                await loadInfo();
                return r?.orphaned_count ? `Deleted ${r.orphaned_count} orphaned articles and ${r.alerts_deleted ?? 0} alerts` : 'No orphaned articles found';
              })}>Clean up articles</Button>
          </Stack>
        </Panel>

        <Panel title="Clear a topic’s articles" description="Delete every article in one topic and keep the topic’s settings, so collection starts again from empty.">
          <Stack gap="sm">
            <Select label="Topic" placeholder="Select a topic" options={topics.map((t) => ({ value: t, label: t }))} value={clearTopic || undefined} onValueChange={setClearTopic} fullWidth />
            <div>
              <Button variant="danger" iconStart={<Icon name="Trash" size="sm" />} busy={busy === 'clear-topic'} disabled={!clearTopic || !!busy}
                onClick={() => confirmRun('clear-topic', `Clear all articles in “${clearTopic}”?`, 'Every article in this topic is deleted. The topic and its keywords stay, and collection carries on. This can’t be undone.', 'Clear articles', async () => {
                  const r = await api<{ message?: string; articles_deleted?: number }>(`/api/clear-topic-articles/${encodeURIComponent(clearTopic)}`, { method: 'POST', json: {} });
                  setClearTopic('');
                  await loadInfo();
                  return `${r?.articles_deleted ?? 0} articles deleted from ${clearTopic}`;
                })}>Clear topic articles</Button>
            </div>
          </Stack>
        </Panel>

        <Panel title="Reset content" description="Delete one kind of data and keep the database itself.">
          <Stack direction="row" gap="sm">
            <Button variant="danger" busy={busy === 'reset-articles'} disabled={!!busy}
              onClick={() => confirmRun('reset-articles', 'Delete all articles and everything built on them?', (
                <>
                  This permanently deletes: articles (enriched and raw), article notes, keyword alerts and matches, keyword groups and monitored keywords,
                  podcasts, feed items and sources, Model Bias Arena data, saved analyses and their cache, signal alerts and incidents, and the vector index.
                  It can’t be undone.
                </>
              ), 'Delete all articles', async () => {
                const r = await api<{ message?: string }>('/api/reset-articles-data', { method: 'POST' });
                await loadInfo();
                return r?.message || 'Articles deleted';
              })}>Reset articles</Button>
            <Button variant="danger" busy={busy === 'reset-auspex'} disabled={!!busy}
              onClick={() => confirmRun('reset-auspex', 'Delete all Auspex chats?', 'Every Auspex conversation and message is deleted, for every user. This can’t be undone.', 'Delete chats', async () => {
                const r = await api<{ message?: string }>('/api/reset-auspex-chats', { method: 'POST' });
                return r?.message || 'Auspex chats deleted';
              })}>Reset Auspex chats</Button>
          </Stack>
        </Panel>

        <Panel title="Topic settings: export and import" description="Save the topics’ monitoring settings to a file, for a backup or another site, or load them from one.">
          <Stack direction="row" gap="sm">
            <Button variant="secondary" iconStart={<Icon name="DownloadSimple" size="sm" />} busy={busy === 'export-topics'} disabled={!!busy}
              onClick={() => void exportJson('export-topics', '/api/export-topics', 'topic-configurations', () => 'Topic settings exported')}>Export topics</Button>
            <Button variant="secondary" iconStart={<Icon name="UploadSimple" size="sm" />} disabled={!!busy} onClick={() => setDialog('topics')}>Import topics</Button>
          </Stack>
        </Panel>

        <Panel title="Articles: export and import" description="Save the articles to a file, for a backup, a move or your own analysis, or load them from one.">
          <Stack direction="row" gap="sm">
            <Button variant="secondary" iconStart={<Icon name="DownloadSimple" size="sm" />} busy={busy === 'export-enriched'} disabled={!!busy}
              onClick={() => void exportJson('export-enriched', '/api/export-articles-enriched', 'articles-enriched', (d) => `Exported ${d.total_articles ?? 0} articles with their AI analysis`)}>Export with AI analysis</Button>
            <Button variant="secondary" iconStart={<Icon name="DownloadSimple" size="sm" />} busy={busy === 'export-raw'} disabled={!!busy}
              onClick={() => void exportJson('export-raw', '/api/export-articles-raw', 'articles-raw', (d) => `Exported ${d.total_articles ?? 0} articles with their full text`)}>Export full text</Button>
            <Button variant="secondary" iconStart={<Icon name="UploadSimple" size="sm" />} disabled={!!busy} onClick={() => setDialog('articles')}>Import articles</Button>
          </Stack>
        </Panel>
      </Stack>

      <Panel title="Database information" description="What the current database holds.">
        {infoError ? <Banner tone="error" title="Database information didn’t load" description={infoError} /> : !info ? <Skeleton variant="text" lines={8} /> : (
          <Stack gap="lg">
            <Grid columns={2} gap="sm">
              <Stat size="compact" label="Type" value={(info.db_type || 'sqlite').toUpperCase()} />
              <Stat size="compact" label="Name" value={info.name || '—'} wrapValue />
              <Stat size="compact" label={sqlite ? 'Path' : 'Host'} value={sqlite ? info.path || '—' : `${info.host || 'localhost'}:${info.port || 5432}`} wrapValue />
              <Stat size="compact" label="Size" value={fmtSize(info.size)} />
              <Stat size="compact" label="Articles" value={(info.total_articles ?? 0).toLocaleString()} />
              <Stat size="compact" label="Topics" value={(info.total_topics ?? 0).toLocaleString()} />
              <Stat size="compact" label="First article" value={fmtDate(info.first_entry)} wrapValue />
              <Stat size="compact" label="Latest article" value={fmtDate(info.last_entry)} wrapValue />
            </Grid>
            <Table
              caption="Tables in the database"
              scroll
              rows={info.tables ?? []}
              rowKey={(t) => t.name}
              emptyText="No tables found."
              columns={[
                { key: 'name', header: 'Table', rowHeader: true },
                { key: 'rows', header: 'Rows', align: 'end', render: (t) => t.rows.toLocaleString() },
              ]}
            />
          </Stack>
        )}
      </Panel>

      <TopicImportDialog open={dialog === 'topics'} onClose={() => setDialog(null)} notify={notify} askConfirm={askConfirm} onDone={() => void loadInfo()} />
      <ArticleImportDialog open={dialog === 'articles'} onClose={() => setDialog(null)} notify={notify} askConfirm={askConfirm} onDone={() => void loadInfo()} />
    </Grid>
  );
}

interface CleanAll {
  status?: string;
  message?: string;
  topics_result?: { status?: string; message?: string; orphaned_topics?: string[] };
  articles_result?: { status?: string; message?: string; orphaned_count?: number; alerts_deleted?: number };
}

function cleanAllSummary(r: CleanAll) {
  const parts: string[] = [];
  const t = r.topics_result;
  if (t?.status === 'error') parts.push(`topics clean-up failed (${t.message})`);
  else parts.push(t?.orphaned_topics?.length ? `${t.orphaned_topics.length} orphaned topics removed` : 'no orphaned topics');
  const a = r.articles_result;
  if (a?.status === 'error') parts.push(`articles clean-up failed (${a.message})`);
  else parts.push(a?.orphaned_count ? `${a.orphaned_count} orphaned articles and ${a.alerts_deleted ?? 0} alerts removed` : 'no orphaned articles');
  return `${r.status === 'partial' ? 'Clean-up finished with errors' : 'Clean-up finished'}: ${parts.join('; ')}.`;
}

/** SQLite only: pick the active database file, create one, delete one, download one */
function SqliteDatabases({ dbs, active, busy, onSwitch, notify, askConfirm, reload }: {
  dbs: DbEntry[]; active: string; busy: Busy; onSwitch: (name: string) => void; notify: (m: string) => void;
  askConfirm: SettingsPageProps['askConfirm']; reload: () => Promise<void>;
}) {
  const [name, setName] = useState('');
  const [creating, setCreating] = useState(false);
  const [download, setDownload] = useState('');
  const create = async () => {
    const n = name.trim().replace(/\.db$/, '');
    if (!n) return;
    setCreating(true);
    try {
      const db = await api<{ id: string; name: string }>('/api/databases', { method: 'POST', json: { name: n } });
      await api('/api/active-database', { method: 'POST', json: { name: db.id } });
      setName('');
      await reload();
      notify(`Created ${db.name} and switched to it`);
    } catch (e) {
      notify(`Not created: ${errorText(e)}`);
    } finally {
      setCreating(false);
    }
  };
  const remove = (db: DbEntry) =>
    askConfirm({
      title: `Delete the database “${db.name}”?`,
      message: 'The database file and everything in it is deleted. This can’t be undone.',
      action: 'Delete database',
      onConfirm: async () => {
        try {
          await api(`/api/databases/${encodeURIComponent(db.id)}`, { method: 'DELETE' });
          await reload();
          notify(`Deleted ${db.name}`);
        } catch (e) {
          notify(`Not deleted: ${errorText(e)}`);
        }
      },
    });
  const downloadFile = async () => {
    if (!download) return;
    try {
      const res = await fetch(`/api/databases/download/${encodeURIComponent(download)}`, { credentials: 'same-origin' });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `${res.status}`);
      saveFile(download, await res.blob(), 'application/octet-stream');
    } catch (e) {
      notify(`Download failed: ${errorText(e)}`);
    }
  };
  return (
    <Panel title="Database files" description="The database the site uses now, the others on file, and new ones.">
      <Stack gap="md">
        <Select label="Active database" placeholder="Select the active database" options={dbs.map((d) => ({ value: d.id, label: d.name }))} value={active || undefined} onValueChange={onSwitch} disabled={busy === 'switch'} fullWidth hint="Where articles and analysis are stored." />
        <Stack as="ul" gap="sm" label="Databases on file">
          {dbs.map((d) => (
            <li key={d.id}>
              <Stack direction="row" justify="between" gap="sm">
                <Text as="span">{d.name}</Text>
                <Button size="sm" variant="ghost" onClick={() => remove(d)}>Delete</Button>
              </Stack>
            </li>
          ))}
        </Stack>
        <TextField label="New database" value={name} onChange={setName} onSubmit={() => void create()} placeholder="Name for the new database" hint="Starts empty, for a different set of articles. The site switches to it once it’s made." />
        <div><Button iconStart={<Icon name="Plus" size="sm" />} busy={creating} disabled={!name.trim() || creating} onClick={() => void create()}>Create database</Button></div>
        <Select label="Download a database file" placeholder="Select a database" options={dbs.map((d) => ({ value: d.name, label: d.name }))} value={download || undefined} onValueChange={setDownload} fullWidth />
        <div><Button variant="secondary" iconStart={<Icon name="DownloadSimple" size="sm" />} disabled={!download} onClick={() => void downloadFile()}>Download</Button></div>
      </Stack>
    </Panel>
  );
}
