import { useMemo } from 'react';
import { Chip, Collapsible, CollapsibleContent, CollapsibleTrigger, Grid, Panel, RangeBar, Stack, StackedBarChart, StackedBars, Text } from '@aunoo/ui';
import { CATEGORY_LABEL, classifyTheme, type ThemeCategory } from './categories';
import './visuals.css';

/*
 * The overview above the theme list, as the old TopicComparisonDashboard: when each theme was
 * detected in the last week, how themes split across rough categories and urgency, how their scores
 * are spread, and how many are speeding up or slowing down.
 *
 * The old timeline drew one dot per article, spread evenly between a theme's first and last
 * detection. Those positions were made up: the list holds no per-article dates. This one draws each
 * theme's detection window (first to last detection) on the last seven days instead.
 */

interface TrendScore {
  volume: number;
  velocity: number;
  diversity: number;
  novelty: number;
  composite: number;
  urgency?: 'low' | 'medium' | 'high';
}

interface EmergingTopic {
  id: number;
  topic_label: string;
  topic_description?: string;
  detection_date: string;
  first_detection_date?: string;
  last_detection_date?: string;
  article_count: number;
  velocity: 'accelerating' | 'stable' | 'decelerating';
  trajectory?: string;
  trend_score?: TrendScore;
  confidence_score?: number;
  key_themes?: string[];
  synthesis?: { urgency?: 'low' | 'medium' | 'high' } | null;
}

interface TopicComparisonDashboardProps {
  topics: EmergingTopic[];
  className?: string;
  onTopicClick?: (topic: EmergingTopic) => void;
}

const DAYS = 7;
const DAY_MS = 86_400_000;
const scoreOf = (t: EmergingTopic) => t.trend_score?.composite ?? (t.confidence_score || 0) * 100;
const urgencyOf = (t: EmergingTopic) => t.trend_score?.urgency ?? t.synthesis?.urgency;
const dayIndex = (iso: string | undefined, start: number) => {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? null : Math.floor((t - start) / DAY_MS);
};

export function TopicComparisonDashboard({ topics, className, onTopicClick }: TopicComparisonDashboardProps) {
  const start = useMemo(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d.getTime() - (DAYS - 1) * DAY_MS;
  }, []);
  const dayLabels = useMemo(
    () => Array.from({ length: DAYS }, (_, i) => new Date(start + i * DAY_MS).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })),
    [start],
  );

  // Themes whose detection window touches the last week, latest first
  const windows = useMemo(() => topics
    .map((t) => {
      const first = dayIndex(t.first_detection_date ?? t.detection_date, start);
      const last = dayIndex(t.last_detection_date ?? t.detection_date, start);
      if (first === null || last === null || last < 0) return null;
      return { t, from: Math.max(0, first), to: Math.min(DAYS - 1, last), before: first < 0 };
    })
    .filter((x): x is NonNullable<typeof x> => x !== null)
    .sort((a, b) => b.to - a.to || scoreOf(b.t) - scoreOf(a.t)), [topics, start]);

  const categories = useMemo(() => {
    const m = new Map<ThemeCategory, number[]>();
    for (const t of topics) {
      const cat = classifyTheme(t.topic_label, t.key_themes);
      const row = m.get(cat) ?? [0, 0, 0, 0];
      const u = urgencyOf(t);
      row[u === 'high' ? 0 : u === 'medium' ? 1 : u === 'low' ? 2 : 3] += 1;
      m.set(cat, row);
    }
    return [...m.entries()].sort((a, b) => b[1].reduce((x, y) => x + y, 0) - a[1].reduce((x, y) => x + y, 0));
  }, [topics]);

  const buckets = useMemo(() => {
    const b = [0, 0, 0, 0, 0];
    for (const t of topics) b[Math.min(4, Math.max(0, Math.floor(scoreOf(t) / 20)))] += 1;
    return b;
  }, [topics]);

  const velocity = useMemo(() => {
    const d = { accelerating: 0, stable: 0, decelerating: 0 };
    for (const t of topics) d[t.velocity in d ? t.velocity : 'stable'] += 1;
    return d;
  }, [topics]);

  if (topics.length < 2) return null;
  const hasUnrated = categories.some(([, v]) => v[3] > 0);

  return (
    <Panel className={className} title="Emerging themes overview" description={`${topics.length} themes`}>
      <Collapsible defaultOpen>
        <CollapsibleTrigger variant="ghost" size="sm">Charts</CollapsibleTrigger>
        <CollapsibleContent>
          <Stack gap="lg">
            <Stack gap="sm">
              <Text variant="label">Detected in the last {DAYS} days</Text>
              <Text variant="caption">Each bar runs from a theme’s first to its latest detection, cut to this week. A bar starting at the left edge was first found earlier.</Text>
              {windows.length === 0 ? <Text variant="caption">No theme was detected in the last {DAYS} days.</Text> : (
                <>
                  <div className="et-windows__axis" aria-hidden="true">
                    <span />
                    <span className="et-windows__days"><span>{dayLabels[0]}</span><span>{dayLabels[DAYS - 1]}</span></span>
                  </div>
                  <ul className="et-windows">
                    {windows.map(({ t, from, to, before }) => (
                      <li key={t.id} className="et-windows__row">
                        {onTopicClick ? (
                          <button type="button" className="text-link et-linkbutton" onClick={() => onTopicClick(t)} title={t.topic_label}>{t.topic_label}</button>
                        ) : <Text as="span" truncate>{t.topic_label}</Text>}
                        <RangeBar
                          min={0}
                          max={DAYS - 1}
                          start={from}
                          end={to}
                          showScale={false}
                          color={t.velocity === 'accelerating' ? 3 : 1}
                          label={`${t.topic_label}, detected ${before ? 'before this week and ' : ''}from ${dayLabels[from]} to ${dayLabels[to]}`}
                        />
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </Stack>

            <Grid columns={2} stackAt="wide">
              <Stack gap="sm">
                <Text variant="label">Categories, by urgency</Text>
                <Text variant="caption">A rough grouping by the words in each theme’s label and key themes.</Text>
                <StackedBars
                  title="Themes per category, by urgency"
                  series={[
                    { id: 'high', label: 'High urgency', color: 'negative' },
                    { id: 'medium', label: 'Medium', color: 'caution' },
                    { id: 'low', label: 'Low', color: 'positive' },
                    ...(hasUnrated ? [{ id: 'none', label: 'No urgency rated', color: 0 as const }] : []),
                  ]}
                  rows={categories.map(([cat, v]) => ({ id: cat, label: CATEGORY_LABEL[cat], values: hasUnrated ? v : v.slice(0, 3) }))}
                />
              </Stack>
              <Stack gap="sm">
                <Text variant="label">Score distribution</Text>
                <Text variant="caption">Themes by overall trend score, out of 100.</Text>
                <StackedBarChart
                  title="Themes by overall score"
                  categories={['0–20', '20–40', '40–60', '60–80', '80–100']}
                  series={[{ id: 'themes', label: 'Themes', color: 1, values: buckets }]}
                />
              </Stack>
            </Grid>

            <Stack gap="sm">
              <Text variant="label">Velocity</Text>
              <Stack direction="row" gap="sm">
                {velocity.accelerating > 0 && <Chip tone="success">{`Accelerating: ${velocity.accelerating}`}</Chip>}
                {velocity.stable > 0 && <Chip tone="neutral">{`Stable: ${velocity.stable}`}</Chip>}
                {velocity.decelerating > 0 && <Chip tone="warning">{`Slowing: ${velocity.decelerating}`}</Chip>}
              </Stack>
            </Stack>
          </Stack>
        </CollapsibleContent>
      </Collapsible>
    </Panel>
  );
}

export default TopicComparisonDashboard;
