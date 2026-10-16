import { useState } from 'react';
import { Banner, Button, Chip, EmptyState, Icon, Panel, Select, Stack, Text } from '@aunoo/ui';
import { generateCategoryInsight, type CategoryInsightResponse, type ScienceCategory } from '@monolith/scienceFundingApi';
import { errorText } from '../../../shell';
import { Markdown } from '../../../shell/Markdown';
import { categoryColor, categoryDescription, HOW_DATA_ARRIVES, periodText, SCIENCE_TOPIC } from './labels';
import './science.css';

/*
 * Categories: an AI reading of one funding category at a time, as the old
 * ScienceCategoryAnalysisTab. Picking a category reads nothing; "Write the insight" makes one AI
 * call for that category and the period. Insights are kept for this visit only, as before. The old
 * tab dropped a failed call silently; it now says so.
 */

export function Categories({ categories, daysBack, model }: { categories: ScienceCategory[] | null; daysBack: number; model: string }) {
  const [picked, setPicked] = useState('');
  const [insights, setInsights] = useState<Record<string, CategoryInsightResponse>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const list = [...(categories ?? [])].sort((a, b) => b.article_count - a.article_count);
  const write = async (category: string) => {
    setBusy(category);
    setError(null);
    try {
      const r = await generateCategoryInsight({ category, topic: SCIENCE_TOPIC, days_back: daysBack, model });
      setInsights((m) => ({ ...m, [category]: r }));
    } catch (e) {
      setError(`No insight for ${category}: ${errorText(e)}`);
    } finally {
      setBusy(null);
    }
  };
  const insight = picked ? insights[picked] : undefined;

  return (
    <Panel
      title="One category at a time"
      description={`Pick a funding category and have the AI (${model || 'the default model'}) read its articles from ${periodText(daysBack)}: the trend, the main themes and how it connects to other categories. Each insight is one AI call.`}
    >
      {!list.length ? (
        <EmptyState icon="Tag" title="No categories yet">{HOW_DATA_ARRIVES}</EmptyState>
      ) : (
        <Stack gap="lg">
          <Stack direction="row" gap="sm">
            <Select
              label="Category"
              hideLabel
              icon="Tag"
              placeholder="Pick a category"
              options={list.map((c) => ({ value: c.category, label: `${c.category} (${c.article_count} articles, ${c.percentage}%)` }))}
              value={picked || undefined}
              onValueChange={setPicked}
              disabled={busy !== null}
            />
            {picked && (
              <Button iconStart={<Icon name="Sparkle" size="sm" />} disabled={busy !== null} onClick={() => void write(picked)}>
                {busy === picked ? 'Writing…' : insights[picked] ? 'Write it again' : 'Write the insight'}
              </Button>
            )}
          </Stack>
          <Stack direction="row" gap="sm">
            {list.slice(0, 10).map((c) => (
              <Chip
                key={c.category}
                tone={picked === c.category ? 'accent' : 'neutral'}
                label={`Pick ${c.category}`}
                onClick={() => busy === null && setPicked(c.category)}
              >
                <span className="science-dot" style={{ background: categoryColor(c.category) }} aria-hidden="true" />
                {`${c.category}: ${c.article_count}`}
              </Chip>
            ))}
          </Stack>
          {error && <Banner tone="error" title="Something went wrong" description={error} />}
          {busy && <Banner tone="info" title={`Writing the insight for ${busy}`} description="This usually takes a few seconds." />}
          {picked && !busy && (insight ? (
            <Stack gap="sm">
              <Stack direction="row" gap="sm">
                <Text as="span" variant="label"><span className="science-dot" style={{ background: categoryColor(picked) }} aria-hidden="true" />{picked}</Text>
                <Chip size="sm" tone={insight.trend === 'up' ? 'success' : insight.trend === 'down' ? 'error' : 'muted'}>
                  {insight.trend === 'up' ? 'Rising' : insight.trend === 'down' ? 'Falling' : 'Steady'}
                </Chip>
                <Text as="span" variant="caption">{`${insight.article_count} articles, ${insight.percentage}%`}</Text>
              </Stack>
              {categoryDescription(picked) && <Text variant="caption">{`Covers: ${categoryDescription(picked)}.`}</Text>}
              <Markdown text={insight.insight} />
            </Stack>
          ) : (
            <Text variant="caption">{categoryDescription(picked) ? `Covers: ${categoryDescription(picked)}. ` : ''}No insight written for this category yet.</Text>
          ))}
        </Stack>
      )}
    </Panel>
  );
}
