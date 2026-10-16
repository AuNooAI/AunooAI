import { useEffect, useState } from 'react';
import { Banner, Chip, EmptyState, Meter, Panel, SegmentedControl, SettingRow, Skeleton, Stack, Text } from '@aunoo/ui';
import { getCooccurrence, getCooccurrenceMatrix, type Cooccurrence, type CooccurrenceMatrix, type ScienceCategory } from '@monolith/scienceFundingApi';
import { errorText } from '../../../shell';
import { categoryColor, HOW_DATA_ARRIVES, periodText, SCIENCE_TOPIC, shortName } from './labels';
import './science.css';

/*
 * Analysis: how the categories overlap, as the old ScienceAnalysisTab. A heatmap of how often two
 * categories tag the same article, the twenty most common pairs, and each category's share with its
 * recent direction. The heatmap and pairs reload when the period changes (the old pairs list kept
 * the first period it loaded).
 */

type View = 'heatmap' | 'pairs' | 'breakdown';
const VIEWS = [
  { value: 'heatmap', label: 'Heatmap' },
  { value: 'pairs', label: 'Top pairs' },
  { value: 'breakdown', label: 'Breakdown' },
];

const Dot = ({ category }: { category: string }) => <span className="science-dot" style={{ background: categoryColor(category) }} aria-hidden="true" />;

export function Analysis({ categories, daysBack, reloadKey }: { categories: ScienceCategory[] | null; daysBack: number; reloadKey: number }) {
  const [view, setView] = useState<View>('heatmap');
  const [matrix, setMatrix] = useState<CooccurrenceMatrix | null | undefined>(undefined);
  const [pairs, setPairs] = useState<Cooccurrence[] | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setMatrix(undefined);
    setPairs(undefined);
    setError(null);
  }, [daysBack, reloadKey]);

  useEffect(() => {
    let live = true;
    if (view === 'heatmap' && matrix === undefined) {
      getCooccurrenceMatrix(SCIENCE_TOPIC, daysBack).then((m) => live && setMatrix(m), (e) => { if (live) { setError(errorText(e)); setMatrix(null); } });
    }
    if (view === 'pairs' && pairs === undefined) {
      getCooccurrence(SCIENCE_TOPIC, daysBack, 20).then((p) => live && setPairs(p), (e) => { if (live) { setError(errorText(e)); setPairs([]); } });
    }
    return () => {
      live = false;
    };
  }, [view, matrix, pairs, daysBack]);

  const heatmap = () => {
    if (matrix === undefined) return <Skeleton variant="block" size="card" />;
    const n = matrix?.categories.length ?? 0;
    const any = matrix?.matrix.some((row) => row.some((v) => v > 0));
    if (!matrix || !n || !any) return <EmptyState icon="SquaresFour" title="No overlaps to show yet">{HOW_DATA_ARRIVES}</EmptyState>;
    // Shade the overlaps against the biggest overlap, and the diagonal against itself, so one big category doesn't wash out the rest
    const off = matrix.matrix.flatMap((row, i) => row.filter((_, j) => j !== i));
    const maxOff = Math.max(1, ...off);
    const maxSelf = Math.max(1, ...matrix.matrix.map((row, i) => row[i]));
    return (
      <Stack gap="sm">
        <div className="science-heatmap" role="region" aria-label="Category overlap heatmap" tabIndex={0}>
          <table>
            <caption className="visually-hidden">Articles tagged with both categories; the diagonal is each category’s own count</caption>
            <thead>
              <tr>
                <td aria-hidden="true" />
                {matrix.categories.map((c) => <th key={c} scope="col" title={c}>{shortName(c)}</th>)}
              </tr>
            </thead>
            <tbody>
              {matrix.matrix.map((row, i) => (
                <tr key={matrix.categories[i]}>
                  <th scope="row" title={matrix.categories[i]}>{shortName(matrix.categories[i])}</th>
                  {row.map((v, j) => (
                    <td
                      key={j}
                      className={i === j ? 'science-heatmap__self' : undefined}
                      style={{ ['--heat' as string]: String(v / (i === j ? maxSelf : maxOff)) }}
                      title={`${matrix.categories[i]} and ${matrix.categories[j]}: ${v}`}
                    >
                      {v > 0 ? v : ''}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Text variant="caption">
          <span className="science-heatmap__key science-heatmap__key--self" aria-hidden="true" />The diagonal: articles in that category.{' '}
          <span className="science-heatmap__key" aria-hidden="true" />Elsewhere: articles tagged with both categories. Darker means more.
        </Text>
      </Stack>
    );
  };

  const pairList = () => {
    if (pairs === undefined) return <Skeleton variant="text" lines={6} />;
    if (!pairs.length) return <EmptyState icon="Link" title="No category pairs yet">{HOW_DATA_ARRIVES}</EmptyState>;
    return (
      <Stack as="ul" gap="sm" label="Most common category pairs">
        {pairs.map((p, i) => (
          <li key={`${p.category1}|${p.category2}`}>
            <SettingRow
              title={<span>{`${i + 1}. `}<Dot category={p.category1} />{shortName(p.category1)} and <Dot category={p.category2} />{shortName(p.category2)}</span>}
              description={`${p.count} articles carry both (${p.percentage}%).`}
            />
          </li>
        ))}
      </Stack>
    );
  };

  const breakdown = () => {
    if (!categories) return <Skeleton variant="text" lines={6} />;
    if (!categories.length) return <EmptyState icon="ChartBar" title="No categories yet">{HOW_DATA_ARRIVES}</EmptyState>;
    return (
      <Stack as="ul" gap="md" label="Category breakdown">
        {[...categories].sort((a, b) => b.article_count - a.article_count).map((c) => (
          <li key={c.category}>
            <Stack gap="sm">
              <Stack direction="row" justify="between" gap="sm">
                <Text as="span" variant="label"><Dot category={c.category} />{c.category}</Text>
                <Chip size="sm" tone={c.recent_trend === 'up' ? 'success' : c.recent_trend === 'down' ? 'error' : 'muted'}>
                  {c.recent_trend === 'up' ? 'Rising' : c.recent_trend === 'down' ? 'Falling' : 'Steady'}
                </Chip>
              </Stack>
              <Meter label={`${c.category}: share of articles`} value={c.percentage} max={100} valueText={`${c.article_count} articles, ${c.percentage}%`} />
            </Stack>
          </li>
        ))}
      </Stack>
    );
  };

  return (
    <>
      {error && <Banner tone="error" title="Part of this view didn’t load" description={error} />}
      <Panel
        title="How the categories overlap"
        description={`An article can sit in several categories. These views show which ones travel together, in ${periodText(daysBack)}.`}
        headerAside={<SegmentedControl className="science-segmented" label="View" options={VIEWS} value={view} onValueChange={(v) => setView(v as View)} />}
      >
        {view === 'heatmap' && heatmap()}
        {view === 'pairs' && pairList()}
        {view === 'breakdown' && breakdown()}
      </Panel>
    </>
  );
}
