import { useCallback, useEffect, useMemo, useState } from 'react';
import { Banner, Grid, Select, SegmentedControl, Skeleton, Stack, Stat, Text } from '@aunoo/ui';
import { api, errorText } from '../../../shell';
import type { EmergingTopic, FilterMode, TopicCategory } from './types';
import { CATEGORY_LABELS, deriveCategory } from './utils';
import { SignalCard } from './SignalCard';
import { TopicDetailPanel } from './TopicDetailPanel';
import { TrajectoryPanel } from './TrajectoryPanel';
import { WatchPanel } from './WatchPanel';
import './signals.css';

/*
 * The "signals" view of Emerging Topics, as the old signal-dashboard EmergingTopicsDashboard: a
 * count strip, theme cards with category and urgency filters, the detection trajectory of the top
 * eight, key actors and things to watch, and a detail dialog. The tab passes its themes in; given
 * none, it reads the active themes itself (a plain read).
 */

interface EmergingTopicsDashboardProps {
  topics?: EmergingTopic[];
  apiUrl?: string;
  runDates?: string[];
}

const FILTERS: { value: FilterMode; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'accelerating', label: 'Accelerating' },
  { value: 'high_urgency', label: 'High urgency' },
];

export function EmergingTopicsDashboard({ topics: given, apiUrl = '/api/emerging-topics/topics?status=active&limit=50', runDates: givenDates }: EmergingTopicsDashboardProps) {
  const [fetched, setFetched] = useState<EmergingTopic[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterMode>('all');
  const [category, setCategory] = useState<TopicCategory | 'all'>('all');
  const [selected, setSelected] = useState<EmergingTopic | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  useEffect(() => {
    if (given) return;
    let live = true;
    setError(null);
    api<unknown>(apiUrl).then(
      (data) => {
        if (!live) return;
        const d = data as { topics?: EmergingTopic[]; emerging_topics?: EmergingTopic[] } | EmergingTopic[];
        setFetched(Array.isArray(d) ? d : d.topics ?? d.emerging_topics ?? []);
      },
      (e) => live && setError(errorText(e)),
    );
    return () => {
      live = false;
    };
  }, [apiUrl, given]);

  const topics = useMemo(() => given ?? fetched ?? [], [given, fetched]);
  const runDates = useMemo(() => givenDates ?? Array.from({ length: 7 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - (6 - i));
    return d.toISOString().slice(0, 10);
  }), [givenDates]);

  const shown = useMemo(() => topics.filter((t) =>
    (filter !== 'accelerating' || t.velocity === 'accelerating')
    && (filter !== 'high_urgency' || t.synthesis?.urgency === 'high')
    && (category === 'all' || deriveCategory(t.topic_filter) === category)), [topics, filter, category]);

  const stats = useMemo(() => {
    const weekAgo = Date.now() - 7 * 86_400_000;
    return {
      total: topics.length,
      accelerating: topics.filter((t) => t.velocity === 'accelerating').length,
      high: topics.filter((t) => t.synthesis?.urgency === 'high').length,
      fresh: topics.filter((t) => t.first_detected_at && new Date(t.first_detected_at).getTime() >= weekAgo).length,
    };
  }, [topics]);

  const open = useCallback((t: EmergingTopic) => {
    setSelected(t);
    setDetailOpen(true);
  }, []);

  if (error) return <Banner tone="error" title="The themes didn’t load" description={error} />;
  if (!given && fetched === null) return <Skeleton variant="block" size="card" />;

  return (
    <Stack gap="lg">
      <Stack direction="row" justify="between" gap="sm">
        <Text variant="label">Emerging signals</Text>
        <Stack direction="row" gap="sm">
          {topics.some((t) => t.topic_filter) && <Select
            label="Category"
            hideLabel
            icon="Funnel"
            value={category}
            onValueChange={(v) => setCategory(v as TopicCategory | 'all')}
            options={[{ value: 'all', label: 'All categories' }, ...(Object.entries(CATEGORY_LABELS) as [TopicCategory, string][]).map(([value, label]) => ({ value, label }))]}
          />}
          <SegmentedControl label="Show" options={FILTERS} value={filter} onValueChange={(v) => setFilter(v as FilterMode)} />
        </Stack>
      </Stack>

      <Grid columns={4} stackAt="small" as="ul" label="Theme counts">
        <Stat as="li" size="compact" label="Active signals" value={stats.total} />
        <Stat as="li" size="compact" label="Accelerating" value={stats.accelerating} tone={stats.accelerating ? 'success' : 'default'} />
        <Stat as="li" size="compact" label="High urgency" value={stats.high} tone={stats.high ? 'error' : 'default'} />
        <Stat as="li" size="compact" label="First found this week" value={stats.fresh} />
      </Grid>

      {shown.length === 0 ? <Text variant="caption">No themes match this filter.</Text> : (
        <ul className="sig-grid" aria-label="Themes">
          {shown.map((t) => (
            <li key={t.id}><SignalCard topic={t} isSelected={selected?.id === t.id && detailOpen} onClick={() => open(t)} /></li>
          ))}
        </ul>
      )}

      <Grid columns="main-aside" stackAt="wide">
        <TrajectoryPanel topics={shown.slice(0, 8)} runDates={runDates} onSelectTopic={open} />
        <WatchPanel topics={shown} onSelectTopic={open} />
      </Grid>

      <TopicDetailPanel topic={selected} open={detailOpen} onClose={() => setDetailOpen(false)} />
    </Stack>
  );
}
