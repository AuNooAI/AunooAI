import { useCallback, useEffect, useState } from 'react';
import { Banner, Button, Chip, EmptyState, Icon, IconButton, Panel, Skeleton, Stack, Table, Text } from '@aunoo/ui';
import { errorText } from '../../shell/api';
import { deleteRun, getModels, getResults, getRuns, getTopics, type ArenaModel, type ArenaResults, type ArenaRun } from '../arena/api';
import { NewRunDialog } from '../arena/NewRunDialog';
import { Results } from '../arena/Results';
import type { SettingsPageProps } from '../types';
import '../arena/arena.css';

/*
 * Model Bias Arena (the old templates/model_bias_arena.html): run the same articles past several AI
 * models and see where they agree with a benchmark model and with each other. Loading the page only
 * reads; starting an evaluation costs money and asks first.
 */

const STATUS_TONE: Record<string, 'success' | 'info' | 'error' | 'muted'> = { completed: 'success', running: 'info', pending: 'info', failed: 'error' };

export function BiasArena({ notify, askConfirm }: SettingsPageProps) {
  const [models, setModels] = useState<ArenaModel[]>([]);
  const [topics, setTopics] = useState<string[]>([]);
  const [runs, setRuns] = useState<ArenaRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [results, setResults] = useState<ArenaResults | null>(null);
  const [opening, setOpening] = useState<number | null>(null);

  const loadRuns = useCallback(() => {
    getRuns().then(setRuns, (e) => {
      setRuns([]);
      setError(`Evaluations didn’t load: ${errorText(e)}`);
    });
  }, []);

  useEffect(() => {
    getModels().then(setModels, (e) => setError(`The model list didn’t load: ${errorText(e)}`));
    getTopics().then(setTopics, () => setTopics([]));
    loadRuns();
  }, [loadRuns]);

  // A run in progress updates on its own, so its round counter and status stay current
  const active = runs?.some((r) => r.status === 'running' || r.status === 'pending');
  useEffect(() => {
    if (!active) return;
    const t = window.setInterval(loadRuns, 15000);
    return () => window.clearInterval(t);
  }, [active, loadRuns]);

  const open = async (id: number) => {
    setOpening(id);
    try {
      setResults(await getResults(id));
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (e) {
      notify(`The results didn’t load: ${errorText(e)}`);
    } finally {
      setOpening(null);
    }
  };

  const remove = (r: ArenaRun) =>
    askConfirm({
      title: `Delete “${r.name}”?`,
      message: 'The evaluation and all its model answers are deleted. This can’t be undone.',
      action: 'Delete evaluation',
      onConfirm: async () => {
        try {
          await deleteRun(r.id);
          if (results?.run_details.id === r.id) setResults(null);
          notify('Evaluation deleted');
          loadRuns();
        } catch (e) {
          notify(`Not deleted: ${errorText(e)}`);
        }
      },
    });

  return (
    <Stack gap="lg">
      <Panel
        title="Model Bias Arena"
        description="Compare how different AI models label the same articles: sentiment, future signal, time to impact, driver type, category, political bias and factuality. One model is the benchmark; the arena shows where the others agree with it and with each other."
        headerAside={<Button iconStart={<Icon name="Plus" size="sm" />} disabled={!models.length} onClick={() => setCreating(true)}>New evaluation</Button>}
      />
      {error && <Banner tone="error" title="Something didn’t load" description={error} action={<Button variant="secondary" size="sm" onClick={() => setError(null)}>Dismiss</Button>} />}

      {results && <Results results={results} onClose={() => setResults(null)} notify={notify} />}

      <Panel
        title="Evaluation history"
        headerAside={<IconButton icon={<Icon name="ArrowClockwise" size="sm" />} label="Reload evaluations" onClick={loadRuns} />}
      >
        {runs === null ? <Skeleton variant="text" lines={5} /> : runs.length === 0 ? (
          <EmptyState icon="Scales" title="No evaluations yet" action={<Button disabled={!models.length} onClick={() => setCreating(true)}>New evaluation</Button>}>
            Start one to compare models on the same articles.
          </EmptyState>
        ) : (
          <Table
            caption="Evaluation history"
            hideCaption
            rows={runs}
            rowKey={(r) => String(r.id)}
            columns={[
              {
                key: 'name', header: 'Name', rowHeader: true, wrap: true,
                render: (r) => (
                  <Stack gap="sm" className="arena-wrap">
                    <Text as="span" variant="label">{r.name}</Text>
                    {r.description && <Text variant="caption">{r.description}</Text>}
                  </Stack>
                ),
              },
              { key: 'models', header: 'Models', wrap: true, render: (r) => <Text variant="caption">{`Benchmark: ${r.benchmark_model}. Compared: ${r.selected_models.join(', ')}`}</Text> },
              { key: 'article_count', header: 'Articles', align: 'end' },
              {
                key: 'rounds', header: 'Rounds', wrap: true,
                render: (r) => `${r.rounds}${r.status === 'running' && r.rounds > 1 ? ` (round ${r.current_round} of ${r.rounds})` : ''}`,
              },
              { key: 'status', header: 'Status', render: (r) => <Chip size="sm" tone={STATUS_TONE[r.status] ?? 'muted'}>{r.status}</Chip> },
              { key: 'created_at', header: 'Started', render: (r) => new Date(r.created_at).toLocaleDateString('en-GB') },
              {
                key: 'actions', header: 'Actions',
                render: (r) => (
                  <Stack direction="row" gap="sm" wrap={false}>
                    {r.status === 'completed' && (
                      <Button size="sm" variant="secondary" iconStart={<Icon name="ChartBar" size="sm" />} disabled={opening === r.id} onClick={() => void open(r.id)}>
                        {opening === r.id ? 'Opening…' : 'Results'}
                      </Button>
                    )}
                    <IconButton tone="danger" icon={<Icon name="Trash" size="sm" />} label={`Delete “${r.name}”`} onClick={() => remove(r)} />
                  </Stack>
                ),
              },
            ]}
          />
        )}
        {active && <Text variant="caption">An evaluation is running. This list checks for progress every 15 seconds.</Text>}
      </Panel>

      <NewRunDialog open={creating} onOpenChange={setCreating} models={models} topics={topics} notify={notify} askConfirm={askConfirm} onStarted={() => window.setTimeout(loadRuns, 1500)} />
    </Stack>
  );
}
