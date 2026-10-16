import { useState } from 'react';
import { Banner, Button, Chip, EmptyState, Icon, Panel, Select, Stack, Text } from '@aunoo/ui';
import { CATEGORY_DESCRIPTIONS, generateCategoryInsight, type CategoryInsightResponse } from '@monolith/policyTrackerApi';
import { errorText } from '../../../../shell';
import { aiDays } from '../api';
import type { PolicyTracker } from '../usePolicyTracker';

/*
 * The old PolicyCategoryAnalysisTab: pick a category and have the AI write a short analysis of it.
 * Only the button calls the AI. The old tab dropped failures silently and sent no model; this one says
 * when it fails and uses the model picked in the Explore filter bar.
 */

const TREND: Record<string, { label: string; tone: 'success' | 'error' | 'muted' }> = {
  up: { label: 'Rising', tone: 'success' },
  down: { label: 'Falling', tone: 'error' },
  stable: { label: 'Steady', tone: 'muted' },
};

export function Categories({ pt, model }: { pt: PolicyTracker; model: string }) {
  const { categories, config } = pt;
  const [picked, setPicked] = useState('');
  const [insights, setInsights] = useState<Record<string, CategoryInsightResponse>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async (category: string) => {
    setBusy(category);
    setError(null);
    try {
      const r = await generateCategoryInsight({ category, topic: config.topic, days_back: aiDays(config.daysBack), model });
      setInsights((p) => ({ ...p, [category]: r }));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(null);
    }
  };

  if (!categories.length) {
    return (
      <Panel title="One category at a time" headingLevel={3}>
        <EmptyState icon="Tag" title="No categories for this period">There are no classified articles to analyse yet. Update data adds them.</EmptyState>
      </Panel>
    );
  }

  const insight = picked ? insights[picked] : undefined;
  return (
    <>
      <Panel
        title="One category at a time"
        headingLevel={3}
        description={`Pick a category and the AI (${model}) writes a short analysis: its trend, its main themes and how it connects to the other categories.`}
      >
        <Stack gap="md">
          <Stack direction="row" gap="sm">
            <Select
              label="Category"
              hideLabel
              placeholder="Pick a category"
              value={picked || undefined}
              onValueChange={setPicked}
              disabled={busy !== null}
              options={categories.map((c) => ({ value: c.category, label: `${c.category} (${c.article_count} articles, ${c.percentage}%)` }))}
            />
            {picked && (
              <Button iconStart={<Icon name="Sparkle" size="sm" />} disabled={busy !== null} onClick={() => void run(picked)}>
                {busy === picked ? 'Writing…' : insight ? 'Write it again' : 'Write the analysis'}
              </Button>
            )}
          </Stack>
          {picked && CATEGORY_DESCRIPTIONS[picked] && <Text variant="caption">{`${picked} covers: ${CATEGORY_DESCRIPTIONS[picked]}.`}</Text>}
          {error && <Banner tone="error" title="The analysis wasn’t written" description={error} />}
          {busy && <Banner tone="info" title={`The AI is writing about ${busy}`} />}
          {insight && !busy && (
            <Stack gap="sm">
              <Stack direction="row" gap="sm">
                <Chip tone={TREND[insight.trend]?.tone ?? 'muted'} size="sm">{TREND[insight.trend]?.label ?? insight.trend}</Chip>
                <Chip tone="neutral" size="sm">{`${insight.article_count} articles, ${insight.percentage}%`}</Chip>
              </Stack>
              <Text>{insight.insight}</Text>
            </Stack>
          )}
          {!picked && <Text variant="caption">Nothing runs until you pick a category and press the button.</Text>}
        </Stack>
      </Panel>

      <Panel title="All categories" headingLevel={3} description="Pick one to analyse it.">
        <Stack direction="row" gap="sm">
          {categories.slice(0, 10).map((c) => (
            <Chip key={c.category} tone={picked === c.category ? 'accent' : 'neutral'} label={`Pick ${c.category}`} onClick={() => setPicked(c.category)}>
              {`${c.category}: ${c.article_count} (${c.percentage}%)`}
            </Chip>
          ))}
        </Stack>
      </Panel>
    </>
  );
}
