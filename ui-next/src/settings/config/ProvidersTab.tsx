import { useCallback, useEffect, useState } from 'react';
import { Banner, Button, Chip, Grid, Icon, Panel, Select, SettingRow, Skeleton, Stack, Text, TextField, TextLink } from '@aunoo/ui';
import { errorText } from '../../shell';
import type { SettingsPageProps } from '../types';
import {
  PROVIDER_GROUPS, getProviders, providerStatus, removeProviderKey, saveBluesky, saveGooglePse, saveProviderKey,
  type Provider,
} from './api';
import { EnvironmentReload } from './EnvironmentReload';

/*
 * News and article providers, as the old Providers tab: an API key per provider, Bluesky's handle
 * and password, Google Programmable Search's key and engine ID, and which are set. A saved key is
 * never shown again; the list only says whether one is set.
 */

interface Status { configured: boolean; username?: string; failed?: boolean }

export function ProvidersTab({ notify, askConfirm }: SettingsPageProps) {
  const [providers, setProviders] = useState<Provider[] | null>(null);
  const [status, setStatus] = useState<Record<string, Status>>({});
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const list = await getProviders();
      setProviders(list);
      const listed = list.filter((p) => PROVIDER_GROUPS.some((g) => g.providers.includes(p.name)) && (p.config_type === 'api_key' || p.name === 'bluesky' || p.name === 'google_pse'));
      const pairs = await Promise.all(listed.map(async (p) => [p.name, await providerStatus(p.name).catch(() => ({ configured: false, failed: true }))] as const));
      setStatus(Object.fromEntries(pairs));
    } catch (e) {
      setError(errorText(e));
      setProviders([]);
    }
  }, []);
  useEffect(() => void load(), [load]);

  const remove = (p: Provider) =>
    askConfirm({
      title: `Remove the ${p.display_name} credentials?`,
      message: `Collection through ${p.display_name} stops until a new key is saved.`,
      action: 'Remove',
      onConfirm: async () => {
        try {
          await removeProviderKey(p.name);
          notify(`${p.display_name} credentials removed`);
          void load();
        } catch (e) {
          notify(`Not removed: ${errorText(e)}`);
        }
      },
    });

  return (
    <Grid columns="main-aside" stackAt="wide" gap="md">
      <Stack gap="lg">
        <ProviderKeyForm providers={providers} notify={notify} onSaved={load} />
        <BlueskyForm configured={status.bluesky?.configured} username={status.bluesky?.username} notify={notify} onSaved={load} />
        <GooglePseForm configured={status.google_pse?.configured} notify={notify} onSaved={load} />
        <EnvironmentReload notify={notify} onReloaded={load} what="provider keys" />
      </Stack>
      <Panel title="Available providers" description="Which news and article providers have credentials set on this site.">
        {error && <Banner tone="error" title="Providers didn’t load" description={error} />}
        {!providers ? <Skeleton variant="text" lines={8} /> : (
          <Stack gap="lg">
            {PROVIDER_GROUPS.map((g) => {
              const inGroup = g.providers.map((n) => providers.find((p) => p.name === n)).filter((p): p is Provider => !!p);
              return (
                <Stack key={g.name} gap="sm">
                  <Text variant="label">{g.name}</Text>
                  {inGroup.length === 0 ? <Text variant="caption">No providers in this group on this site.</Text> : (
                    <Stack as="ul" gap="sm" label={g.name}>
                      {inGroup.map((p) => {
                        const s = status[p.name];
                        const note = p.name === 'bluesky' ? 'Signs in with a handle and password.' : p.name === 'google_pse' ? 'Needs an API key and a search engine ID.' : undefined;
                        return (
                          <li key={p.name}>
                            <SettingRow
                              title={p.name === 'google_pse' ? 'Google Programmable Search' : p.display_name}
                              description={s?.failed ? 'Its status didn’t load.' : note}
                              actions={
                                <Stack direction="row" gap="sm" wrap={false}>
                                  {s && !s.failed && <Chip size="sm" tone={s.configured ? 'success' : 'muted'}>{s.configured ? 'Set' : 'Not set'}</Chip>}
                                  {s?.configured && <Button size="sm" variant="ghost" onClick={() => remove(p)}>Remove</Button>}
                                </Stack>
                              }
                            />
                          </li>
                        );
                      })}
                    </Stack>
                  )}
                </Stack>
              );
            })}
          </Stack>
        )}
      </Panel>
    </Grid>
  );
}

function ProviderKeyForm({ providers, notify, onSaved }: { providers: Provider[] | null; notify: (m: string) => void; onSaved: () => void }) {
  const [name, setName] = useState('');
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);
  // Every key-based provider except Bluesky, grouped as in the list
  const options = PROVIDER_GROUPS.flatMap((g) =>
    g.providers
      .map((n) => providers?.find((p) => p.name === n && p.config_type === 'api_key' && p.name !== 'bluesky'))
      .filter((p): p is Provider => !!p)
      .map((p) => ({ value: p.name, label: p.display_name, group: g.name })),
  );
  const label = options.find((o) => o.value === name)?.label ?? name;
  const save = async () => {
    if (!name || !key.trim()) return;
    setBusy(true);
    try {
      await saveProviderKey(name, key.trim());
      notify(`${label} key saved`);
      setKey('');
      onSaved();
    } catch (e) {
      notify(`${label} key not saved: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel
      title="Article provider keys"
      description={<>Set an API key for a news or article provider. Need one? <TextLink href="https://newsapi.org/register" external>NewsAPI free developer tier</TextLink> · <TextLink href="https://newsdata.io/pricing" external>NewsData.io free tier</TextLink> · <TextLink href="https://www.firecrawl.dev/pricing" external>Firecrawl free plan</TextLink> · <TextLink href="https://elevenlabs.io/pricing" external>ElevenLabs free tier</TextLink></>}
    >
      <Stack gap="md">
        <Select label="Provider" placeholder="Select a provider" options={options} value={name || undefined} onValueChange={setName} fullWidth hint="Choose a provider to add or replace its key." />
        <TextField label="API key" type="password" autoComplete="off" value={key} onChange={setKey} placeholder="Paste the key from the provider’s dashboard" hint="Saving replaces any key already set. The key isn’t shown again after it’s saved." />
        <div><Button iconStart={<Icon name="Key" size="sm" />} busy={busy} disabled={!name || !key.trim() || busy} onClick={() => void save()}>Save key</Button></div>
      </Stack>
    </Panel>
  );
}

function BlueskyForm({ configured, username, notify, onSaved }: { configured?: boolean; username?: string; notify: (m: string) => void; onSaved: () => void }) {
  const [handle, setHandle] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  // The saved handle fills the field, as on the old page; the password never comes back
  useEffect(() => {
    if (username) setHandle(username);
  }, [username]);
  const save = async () => {
    setBusy(true);
    try {
      await saveBluesky(handle.trim(), password);
      notify('Bluesky credentials saved');
      setPassword('');
      onSaved();
    } catch (e) {
      notify(`Bluesky credentials not saved: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel title="Bluesky" description="The account used to collect Bluesky posts.">
      <Stack gap="md">
        {configured && <Banner tone="info" title="Bluesky credentials are set" description="Enter new values to replace them." />}
        <TextField label="Bluesky handle" value={handle} onChange={setHandle} placeholder="e.g. name.bsky.social, or the account email" autoComplete="off" />
        <TextField label="Password" type="password" value={password} onChange={setPassword} autoComplete="new-password" hint="The account password or an app password (Settings → App passwords on Bluesky). An app password is safer." />
        <div><Button busy={busy} disabled={!handle.trim() || !password || busy} onClick={() => void save()}>Save Bluesky credentials</Button></div>
      </Stack>
    </Panel>
  );
}

function GooglePseForm({ configured, notify, onSaved }: { configured?: boolean; notify: (m: string) => void; onSaved: () => void }) {
  const [key, setKey] = useState('');
  const [cse, setCse] = useState('');
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      await saveGooglePse(key.trim(), cse.trim());
      notify('Google Programmable Search credentials saved');
      setKey('');
      setCse('');
      onSaved();
    } catch (e) {
      notify(`Google Programmable Search credentials not saved: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel title="Google Programmable Search" description="Web search for research features, through a Google Programmable Search Engine.">
      <Stack gap="md">
        {configured && <Banner tone="info" title="Google Programmable Search is set" description="Enter both values again to replace them." />}
        <TextField label="Google API key" type="password" autoComplete="off" value={key} onChange={setKey} hint={<>A Google Cloud key with the Custom Search API switched on, from the <TextLink href="https://console.cloud.google.com/apis/credentials" external>Google Cloud Console</TextLink>.</>} />
        <TextField label="Search engine ID (CSE ID)" value={cse} onChange={setCse} autoComplete="off" hint={<>Create one at <TextLink href="https://programmablesearchengine.google.com/" external>Programmable Search Engine</TextLink>.</>} />
        <div><Button busy={busy} disabled={!key.trim() || !cse.trim() || busy} onClick={() => void save()}>Save Google credentials</Button></div>
      </Stack>
    </Panel>
  );
}
