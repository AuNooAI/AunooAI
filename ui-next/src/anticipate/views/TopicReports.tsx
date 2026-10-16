import { useCallback, useEffect, useState } from 'react';
import { Banner, Button, Checkbox, EmptyState, Icon, Meter, Panel, SettingRow, Skeleton, Stack, Text, TextField } from '@aunoo/ui';
import { api, errorText } from '../../shell';
import { downloadFile } from '../lib/download';
import { useJob } from '../lib/jobs';
import { useTrackedTopics } from './Topics';
import type { ViewProps } from './types';

interface Recent { period_label: string; generated_at?: string; size_bytes?: number }

const defaultPeriod = () => {
  const d = new Date();
  return `Q${Math.floor(d.getMonth() / 3) + 1} ${d.getFullYear()}`;
};
/** The server stores "Q4_2026__<hash of the topic set>"; show the period and a short set id. */
const readable = (label: string) => {
  const [period, hash] = label.split('__');
  return `${period.replace(/_/g, ' ')}${hash ? ` · topic set ${hash.slice(0, 6)}` : ''}`;
};
const enc = encodeURIComponent;

/** Long-form reports across chosen tracked topics (POST /api/topic-reports/start). */
export function TopicReports({ config, notify }: ViewProps) {
  const topics = useTrackedTopics();
  const [period, setPeriod] = useState(defaultPeriod);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [recent, setRecent] = useState<Recent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const job = useJob(1500);

  const loadRecent = useCallback(() => {
    api<{ reports: Recent[] }>('/api/topic-reports/recent?limit=20').then((r) => setRecent(r.reports ?? []), () => setRecent([]));
  }, []);
  useEffect(loadRecent, [loadRecent]);

  // Only topics with a stored assessment can go into a report
  const eligible = (topics.rows ?? []).filter((t) => t.status !== 'archived' && t.assessment_id);
  const q = query.trim().toLowerCase();
  const shown = eligible.filter((t) => !q || (t.display_name || t.topic).toLowerCase().includes(q) || (t.tags ?? []).some((g) => g.toLowerCase().includes(q)));

  const start = async (rerun: boolean) => {
    setError(null);
    try {
      const r = await api<{ task_id: string; status_url?: string; download_url: string; period_label: string }>('/api/topic-reports/start', {
        method: 'POST',
        json: { topics: selected, period: period.trim(), rerun_forecast: rerun, force_model: rerun ? config.model : undefined },
      });
      job.watch(r.status_url ?? `/api/forecast/assessment/job/${r.task_id}`, (j) => {
        if (j.result?.error_count) notify(`Report ready, but the reviewer flagged ${j.result.error_count} errors — check the “Review pending” banner in it`);
        downloadFile(r.download_url, `topic-report-${r.period_label}.pptx`).then(loadRecent, (e) => notify(errorText(e)));
      });
    } catch (e) {
      setError(errorText(e));
    }
  };

  const running = job.state.kind === 'running';
  return (
    <>
      <Panel
        title="Topic Reports"
        description="Combine tracked topics into one long-form report for a period."
        headerAside={<Button variant="secondary" size="sm" iconStart={<Icon name="ArrowClockwise" size="sm" />} onClick={() => { topics.reload(); loadRecent(); }}>Refresh</Button>}
      />
      <Panel title="New report" description={`${selected.length} of ${eligible.length} topics selected`}>
        <Stack gap="md">
          {error && <Banner tone="error" icon="WarningCircle" title="The report didn’t start" description={error} />}
          <TextField label="Period label" value={period} onChange={setPeriod} hint="Shown on the cover. With the chosen topics it also keys the cache, so the same set and period reuse earlier work." />
          <TextField label="Search topics" hideLabel type="search" placeholder="Filter by name or tag…" value={query} onChange={setQuery} />
          <Stack direction="row" justify="between" gap="sm">
            <Text variant="label" as="span">Topics to include</Text>
            <Stack direction="row" gap="sm">
              <Button variant="ghost" size="sm" onClick={() => setSelected(shown.map((t) => t.topic))}>{`Select all (${shown.length})`}</Button>
              <Button variant="ghost" size="sm" disabled={!selected.length} onClick={() => setSelected([])}>Clear</Button>
            </Stack>
          </Stack>
          {topics.error ? (
            <Banner tone="error" icon="WarningCircle" title="Couldn’t load topics" description={topics.error} />
          ) : !topics.rows ? (
            <Skeleton lines={4} />
          ) : eligible.length === 0 ? (
            <EmptyState>No topics with a stored assessment. Run one from a topic’s Forecast Tracker first.</EmptyState>
          ) : (
            <div>
              {shown.map((t) => (
                <Checkbox
                  key={t.topic}
                  checked={selected.includes(t.topic)}
                  onCheckedChange={(c) => setSelected((s) => (c ? [...s, t.topic] : s.filter((x) => x !== t.topic)))}
                  label={
                    <span>
                      {t.display_name || t.topic}
                      <Text variant="caption" as="span">{[t.description, t.scenarios_count != null && `${t.scenarios_count} scenarios`, t.owner, (t.tags ?? []).slice(0, 3).join(', ')].filter(Boolean).map((x) => ` · ${x}`).join('')}</Text>
                    </span>
                  }
                />
              ))}
            </div>
          )}
          {job.state.kind === 'running' && <Meter label="Report progress" progress value={job.state.pct} valueText={`${job.state.pct}% · ${job.state.message} — the first run takes 2–5 minutes`} />}
          {job.state.kind === 'failed' && <Banner tone="error" icon="WarningCircle" title="Report failed" description={job.state.message} />}
          <Stack direction="row" gap="sm">
            <Button iconStart={<Icon name="ArrowClockwise" size="sm" />} disabled={!selected.length || !period.trim() || running} onClick={() => void start(true)}>{`Re-run analysis (${config.model}) and generate`}</Button>
            <Button variant="secondary" disabled={!selected.length || !period.trim() || running} onClick={() => void start(false)}>Generate from cache</Button>
          </Stack>
        </Stack>
      </Panel>
      <Panel title="Recent reports">
        {!recent ? (
          <Skeleton lines={3} />
        ) : recent.length === 0 ? (
          <EmptyState>No reports generated yet.</EmptyState>
        ) : (
          <Stack as="ul" gap="sm" label="Recent reports">
            {recent.map((r) => (
              <li key={r.period_label}>
                <SettingRow
                  title={readable(r.period_label)}
                  description={[r.generated_at && new Date(r.generated_at).toLocaleString('en-GB'), r.size_bytes && `${(r.size_bytes / 1e6).toFixed(1)} MB`].filter(Boolean).join(' · ')}
                  actions={
                    <>
                      {(['pptx', 'docx', 'md', 'html'] as const).map((ext) => (
                        <Button key={ext} size="sm" variant="ghost" onClick={() => downloadFile(`/api/topic-reports/${enc(r.period_label)}/download.${ext}`, `topic-report-${r.period_label}.${ext}`).catch((e) => notify(errorText(e)))}>{`.${ext}`}</Button>
                      ))}
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={async () => {
                          try {
                            await api(`/api/topic-reports/${enc(r.period_label)}/regenerate`, { method: 'POST' });
                            notify('Cache cleared — generate the report again to rebuild it');
                            loadRecent();
                          } catch (e) {
                            notify(`Not cleared: ${errorText(e)}`);
                          }
                        }}
                      >
                        Regenerate
                      </Button>
                    </>
                  }
                />
              </li>
            ))}
          </Stack>
        )}
      </Panel>
    </>
  );
}
