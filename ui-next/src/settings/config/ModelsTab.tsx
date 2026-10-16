import { useCallback, useEffect, useState } from 'react';
import { Banner, Button, EmptyState, Grid, Icon, Panel, Select, SettingRow, Skeleton, Stack, TextField, TextLink } from '@aunoo/ui';
import { errorText } from '../../shell';
import type { SettingsPageProps } from '../types';
import { addModel, getConfiguredModels, getModelCatalogue, removeModel, type ModelEntry } from './api';
import { EnvironmentReload } from './EnvironmentReload';

/*
 * AI models, as the old AI Models tab: pick a model from the site's catalogue and set its provider
 * key; the list shows the models that have a key and can be used. A saved key is never shown again.
 */

export function ModelsTab({ notify, askConfirm }: SettingsPageProps) {
  const [catalogue, setCatalogue] = useState<ModelEntry[] | null>(null);
  const [configured, setConfigured] = useState<ModelEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [model, setModel] = useState('');
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setError(null);
    getModelCatalogue().then(setCatalogue, (e) => {
      setCatalogue([]);
      setError(errorText(e));
    });
    getConfiguredModels().then(setConfigured, (e) => {
      setConfigured([]);
      setError(errorText(e));
    });
  }, []);
  useEffect(load, [load]);

  // The catalogue can list the same name under two providers, so the option value carries both
  const options = (catalogue ?? []).map((m) => ({ value: `${m.provider}::${m.name}`, label: `${m.name} (${m.provider})` }));
  const save = async () => {
    const [provider, ...rest] = model.split('::');
    const name = rest.join('::');
    if (!name || !provider || !key.trim()) return;
    setBusy(true);
    try {
      const r = await addModel(name, provider, key.trim());
      if (r?.error) throw new Error(r.error);
      notify(r?.message || `${name} saved`);
      setKey('');
      load();
    } catch (e) {
      notify(`Model not saved: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };
  const remove = (m: ModelEntry) =>
    askConfirm({
      title: `Remove ${m.name}?`,
      message: `${m.name} (${m.provider}) is taken off the list of usable models. Features set to use it fall back to another model or stop until it’s added again.`,
      action: 'Remove model',
      onConfirm: async () => {
        try {
          await removeModel(m.name, m.provider);
          notify(`${m.name} removed`);
          load();
        } catch (e) {
          notify(`Not removed: ${errorText(e)}`);
        }
      },
    });

  return (
    <Grid columns="main-aside" stackAt="wide" gap="md">
      <Stack gap="lg">
        <Panel
          title="AI models"
          description={<>Set the provider key for a model the site’s AI features can use. Need a key? <TextLink href="https://platform.openai.com/" external>OpenAI API</TextLink> · <TextLink href="https://www.anthropic.com/api" external>Anthropic API</TextLink></>}
        >
          <Stack gap="md">
            <Select label="AI model" placeholder="Select a model" options={options} value={model || undefined} onValueChange={setModel} fullWidth hint="Choose a model to add, or to replace its key." />
            <TextField label="API key" type="password" autoComplete="off" value={key} onChange={setKey} placeholder="Paste the key from the provider’s dashboard" hint="The key isn’t shown again after it’s saved." />
            <div><Button iconStart={<Icon name="Key" size="sm" />} busy={busy} disabled={!model || !key.trim() || busy} onClick={() => void save()}>Save model key</Button></div>
          </Stack>
        </Panel>
        <EnvironmentReload notify={notify} onReloaded={load} what="AI model keys" />
      </Stack>
      <Panel title="Available models" description="Models with a key set, which the site’s AI features can use.">
        {error && <Banner tone="error" title="Models didn’t load" description={error} />}
        {!configured ? <Skeleton variant="text" lines={6} /> : configured.length === 0 ? (
          <EmptyState icon="Brain" title="No models set up">Add a model and its key to use the AI features.</EmptyState>
        ) : (
          <Stack as="ul" gap="sm" label="Available models">
            {configured.map((m) => (
              <li key={`${m.provider}:${m.name}`}>
                <SettingRow title={m.name} description={m.provider} actions={<Button size="sm" variant="ghost" onClick={() => remove(m)}>Remove</Button>} />
              </li>
            ))}
          </Stack>
        )}
      </Panel>
    </Grid>
  );
}
