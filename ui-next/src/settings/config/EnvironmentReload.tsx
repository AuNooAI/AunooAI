import { useState } from 'react';
import { Button, Icon, Panel, Stack, Text } from '@aunoo/ui';
import { errorText } from '../../shell';
import { reloadEnvironment } from './api';

/** Re-reads the site's .env without a restart, as the old page's "Reload environment" button */
export function EnvironmentReload({ notify, onReloaded, what }: { notify: (m: string) => void; onReloaded: () => void; what: string }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const reload = async () => {
    setBusy(true);
    setResult(null);
    try {
      const r = await reloadEnvironment();
      const keys = Object.entries(r.keys_available ?? {}).filter(([, ok]) => ok).map(([k]) => k);
      setResult(keys.length ? `Reloaded. Keys found for: ${keys.join(', ')}.` : 'Reloaded. No keys were found.');
      notify('Environment reloaded');
      onReloaded();
    } catch (e) {
      setResult(null);
      notify(`Not reloaded: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel title="Environment" description={`Reload the site’s settings file without restarting, after changing ${what} in it by hand.`}>
      <Stack gap="sm">
        <div><Button variant="secondary" iconStart={<Icon name="ArrowsClockwise" size="sm" />} busy={busy} disabled={busy} onClick={() => void reload()}>Reload environment</Button></div>
        {result && <Text variant="caption">{result}</Text>}
      </Stack>
    </Panel>
  );
}
