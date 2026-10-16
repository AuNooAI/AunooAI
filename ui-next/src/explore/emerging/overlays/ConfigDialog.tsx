import { useEffect, useState } from 'react';
import { Banner, Button, Checkbox, Chip, Dialog, Eyebrow, Grid, Icon, LineItems, Select, Slider, Stack, Switch, TabPanel, Tabs, TagInput, Text, TextField } from '@aunoo/ui';
import { api, errorText } from '../../../shell';

/*
 * Emerging Topics settings, as the old EmergingTopicsConfigModal.tsx. Detection settings live in
 * this browser (localStorage "emergingTopicsConfig", shared with the old page); alert settings are
 * the site's own (GET/POST /api/emerging-topics/notifications/settings, admin only).
 */

export interface EmergingTopicsConfig {
  sampleSize: number;
  daysBack: number;
  distanceThreshold: number;
  minArticlesPerTheme: number;
  maxArticlesPerTheme: number;
  model: string;
}

interface AIModel {
  id: string;
  name: string;
  provider?: string;
}

interface NotificationSettings {
  notifications_enabled: boolean;
  notification_channels: { email?: boolean; in_app?: boolean; bluesky?: boolean };
  min_confidence: number;
  cooldown_minutes: number;
  email_recipients: string[];
  bluesky_handle: string | null;
  detection_type_filters: string[];
}

const DEFAULT_CONFIG: EmergingTopicsConfig = {
  sampleSize: 250,
  daysBack: 7,
  distanceThreshold: 0.85,
  minArticlesPerTheme: 3,
  maxArticlesPerTheme: 30,
  model: 'claude-sonnet-5-5',
};

const STORAGE_KEY = 'emergingTopicsConfig';

/**
 * What the pipeline can notify on, mirroring app/services/emerging_topics/notification_filters.py.
 * Detection writes two types, llm_proposed and ongoing_topic; "accelerating" is matched against the
 * topic's velocity, not its type.
 */
export const NOTIFICATION_FILTER_OPTIONS: { value: string; label: string; description: string }[] = [
  { value: 'llm_proposed', label: 'new theme', description: 'A theme proposed for the first time in this scope' },
  { value: 'ongoing_topic', label: 'ongoing topic', description: 'A theme that already had coverage before the analysis window' },
  { value: 'accelerating', label: 'accelerating', description: 'Coverage is growing faster in the second half of the window' },
];

export const DEFAULT_NOTIFICATION_FILTERS = ['llm_proposed', 'accelerating'];

export function loadEmergingTopicsConfig(): EmergingTopicsConfig {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) return { ...DEFAULT_CONFIG, ...JSON.parse(saved) };
  } catch {
    // unreadable storage: fall back to the defaults
  }
  return DEFAULT_CONFIG;
}

export function saveEmergingTopicsConfigToStorage(config: EmergingTopicsConfig): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
  } catch {
    // per visit only
  }
}

const FALLBACK_MODELS: AIModel[] = [
  { id: 'claude-sonnet-5-5', name: 'Claude Sonnet 5.5', provider: 'bedrock' },
  { id: 'claude-sonnet-4-5', name: 'Claude Sonnet 4.5', provider: 'bedrock' },
  { id: 'claude-haiku-4-5', name: 'Claude Haiku 4.5', provider: 'bedrock' },
  { id: 'nova-pro', name: 'Nova Pro', provider: 'bedrock' },
  { id: 'nova-lite', name: 'Nova Lite', provider: 'bedrock' },
  { id: 'bedrock-kimi-k2-5', name: 'Kimi K2.5', provider: 'bedrock' },
];

const DEFAULT_ALERTS: NotificationSettings = {
  notifications_enabled: false,
  notification_channels: { email: false, in_app: true, bluesky: false },
  min_confidence: 0.7,
  cooldown_minutes: 360,
  email_recipients: [],
  bluesky_handle: null,
  detection_type_filters: [...DEFAULT_NOTIFICATION_FILTERS],
};

interface Props {
  open: boolean;
  onClose: () => void;
  config: EmergingTopicsConfig;
  onSave: (config: EmergingTopicsConfig) => void;
  availableModels: AIModel[];
}

export function EmergingTopicsConfigModal({ open, onClose, config: initialConfig, onSave, availableModels }: Props) {
  const [config, setConfig] = useState<EmergingTopicsConfig>(initialConfig);
  const [tab, setTab] = useState('detection');
  const [alerts, setAlerts] = useState<NotificationSettings>(DEFAULT_ALERTS);
  // Whether the saved alert settings came back; unsaved edits are compared against them
  const [savedAlerts, setSavedAlerts] = useState<NotificationSettings | null>(null);
  const [alertsError, setAlertsError] = useState<string | null>(null);
  const [busy, setBusy] = useState<null | 'save' | 'test'>(null);
  const [note, setNote] = useState<{ tone: 'success' | 'error' | 'info'; text: string } | null>(null);

  const loadAlerts = () =>
    api<Partial<NotificationSettings>>('/api/emerging-topics/notifications/settings').then(
      (d) => {
        const next: NotificationSettings = {
          notifications_enabled: d.notifications_enabled || false,
          notification_channels: d.notification_channels || DEFAULT_ALERTS.notification_channels,
          min_confidence: d.min_confidence || 0.7,
          cooldown_minutes: d.cooldown_minutes || 360,
          email_recipients: d.email_recipients || [],
          bluesky_handle: d.bluesky_handle || null,
          detection_type_filters: d.detection_type_filters?.length ? d.detection_type_filters : [...DEFAULT_NOTIFICATION_FILTERS],
        };
        setAlerts(next);
        setSavedAlerts(next);
        setAlertsError(null);
      },
      // Alert settings are admin-only; say so instead of showing defaults as if they were saved
      (e: unknown) => setAlertsError(errorText(e)),
    );

  useEffect(() => {
    if (!open) return;
    setConfig(initialConfig);
    setNote(null);
    void loadAlerts();
  }, [open, initialConfig]);

  const models = availableModels.length > 0 ? availableModels : FALLBACK_MODELS;
  // Keep a saved model selected even when it is no longer offered, rather than silently saving the first option
  const selectedModel = config.model || models[0]?.id || DEFAULT_CONFIG.model;
  const modelOptions = [
    ...(selectedModel && !models.some((m) => m.id === selectedModel) ? [{ value: selectedModel, label: `${selectedModel} (no longer offered)` }] : []),
    ...models.map((m) => ({ value: m.id, label: m.provider ? `${m.name} (${m.provider})` : m.name })),
  ];

  const set = <K extends keyof EmergingTopicsConfig>(k: K, v: EmergingTopicsConfig[K]) => setConfig((c) => ({ ...c, [k]: v }));
  const setA = (patch: Partial<NotificationSettings>) => setAlerts((a) => ({ ...a, ...patch }));
  const setChannel = (k: 'in_app' | 'email' | 'bluesky', on: boolean) => setA({ notification_channels: { ...alerts.notification_channels, [k]: on } });
  const toggleType = (t: string) =>
    setA({ detection_type_filters: alerts.detection_type_filters.includes(t) ? alerts.detection_type_filters.filter((x) => x !== t) : [...alerts.detection_type_filters, t] });

  const alertsDirty = savedAlerts !== null && JSON.stringify(alerts) !== JSON.stringify(savedAlerts);

  const saveDetection = () => {
    saveEmergingTopicsConfigToStorage(config);
    onSave(config);
    onClose();
  };

  const saveAlerts = async () => {
    setBusy('save');
    setNote(null);
    try {
      await api('/api/emerging-topics/notifications/settings', { method: 'POST', json: alerts });
      await loadAlerts();
      setNote({ tone: 'success', text: 'Alert settings saved.' });
    } catch (e) {
      // The old dialog only logged a failed save to the console
      setNote({ tone: 'error', text: `Not saved: ${errorText(e)}` });
    } finally {
      setBusy(null);
    }
  };

  const testAlerts = async () => {
    setBusy('test');
    setNote(null);
    try {
      const r = await api<{ results?: Record<string, { sent?: boolean; error?: string }> }>('/api/emerging-topics/notifications/test', { method: 'POST' });
      const entries = Object.entries(r.results ?? {});
      const sent = entries.filter(([, v]) => v?.sent).map(([k]) => k);
      const failed = entries.filter(([, v]) => !v?.sent).map(([k, v]) => (v?.error ? `${k} (${v.error})` : k));
      setNote(
        sent.length
          ? { tone: 'success', text: `Test sent via ${sent.join(', ')}.${failed.length ? ` Not sent via ${failed.join(', ')}.` : ''}` }
          : { tone: 'error', text: failed.length ? `Nothing was sent. Failed: ${failed.join(', ')}.` : 'Nothing was sent: no channel is switched on in the saved settings.' },
      );
    } catch (e) {
      setNote({ tone: 'error', text: `Test failed: ${errorText(e)}` });
    } finally {
      setBusy(null);
    }
  };

  const footer = (
    <>
      <Button variant="secondary" size="lg" onClick={onClose}>Close</Button>
      {tab === 'detection' && (
        <>
          <Button variant="ghost" size="lg" iconStart={<Icon name="ArrowClockwise" size="sm" />} onClick={() => setConfig(DEFAULT_CONFIG)}>Reset to defaults</Button>
          <Button size="lg" onClick={saveDetection}>Save</Button>
        </>
      )}
      {tab === 'alerts' && !alertsError && (
        <>
          <Button variant="ghost" size="lg" iconStart={<Icon name="Bell" size="sm" />} disabled={busy !== null || savedAlerts === null} onClick={() => void testAlerts()}>
            {busy === 'test' ? 'Sending…' : 'Send a test'}
          </Button>
          <Button size="lg" disabled={busy !== null || savedAlerts === null || !alertsDirty} onClick={() => void saveAlerts()}>
            {busy === 'save' ? 'Saving…' : 'Save alert settings'}
          </Button>
        </>
      )}
    </>
  );

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()} size="lg" title="Emerging Topics settings" description="How detection runs, and who gets told when it finds something." footer={footer}>
      <Tabs
        label="Settings sections"
        value={tab}
        onValueChange={setTab}
        items={[
          { value: 'detection', label: 'Detection', icon: <Icon name="SlidersHorizontal" size="sm" /> },
          { value: 'alerts', label: 'Alerts', icon: <Icon name="Bell" size="sm" /> },
          { value: 'about', label: 'How it works', icon: <Icon name="Info" size="sm" /> },
        ]}
      >
        <TabPanel value="detection">
          <Stack gap="lg">
            <Text variant="caption">These settings are kept in this browser and apply to detection runs you start from this page.</Text>
            <Select label="AI model" options={modelOptions} value={selectedModel} onValueChange={(v) => set('model', v)} fullWidth />
            <Slider
              label="Sample size"
              value={config.sampleSize}
              onValueChange={(v) => set('sampleSize', v)}
              min={50}
              max={500}
              step={50}
              valueText={`${config.sampleSize} articles`}
              hint="How many recent high-novelty articles the AI reads to propose themes. More articles cost more."
            />
            <Slider label="Days back" value={config.daysBack} onValueChange={(v) => set('daysBack', v)} min={1} max={30} step={1} valueText={`${config.daysBack} days`} />
            <Slider
              label="Distance threshold"
              value={Math.round(config.distanceThreshold * 100)}
              onValueChange={(v) => set('distanceThreshold', v / 100)}
              min={30}
              max={100}
              step={5}
              valueText={config.distanceThreshold.toFixed(2)}
              hint="How close an article must be to a proposed theme to count as evidence for it."
            />
            <Grid columns={2}>
              <Slider label="Fewest articles per theme" value={config.minArticlesPerTheme} onValueChange={(v) => set('minArticlesPerTheme', v)} min={2} max={20} step={1} valueText={String(config.minArticlesPerTheme)} />
              <Slider label="Most articles per theme" value={config.maxArticlesPerTheme} onValueChange={(v) => set('maxArticlesPerTheme', v)} min={10} max={100} step={5} valueText={String(config.maxArticlesPerTheme)} />
            </Grid>
          </Stack>
        </TabPanel>

        <TabPanel value="alerts">
          <Stack gap="lg">
            {alertsError ? (
              <Banner tone="error" title="Alert settings didn’t load" description={`${alertsError}. Only an administrator can see and change them.`} />
            ) : (
              <>
                <Text variant="caption">Alert settings apply to the whole site, including scheduled runs.</Text>
                <Switch
                  label="Send alerts"
                  description="Tell people when detection finds a new emerging topic."
                  checked={alerts.notifications_enabled}
                  onCheckedChange={(on) => setA({ notifications_enabled: on })}
                />
                <Stack gap="sm">
                  <Eyebrow as="h3">Where alerts go</Eyebrow>
                  <Checkbox label="In the app" checked={!!alerts.notification_channels.in_app} onCheckedChange={(on) => setChannel('in_app', on)} />
                  <Checkbox label="Email" checked={!!alerts.notification_channels.email} onCheckedChange={(on) => setChannel('email', on)} />
                  <Checkbox label="Bluesky direct message" checked={!!alerts.notification_channels.bluesky} onCheckedChange={(on) => setChannel('bluesky', on)} />
                </Stack>
                {alerts.notification_channels.email && (
                  <TagInput
                    label="Email recipients"
                    tags={alerts.email_recipients}
                    onChange={(tags) => setA({ email_recipients: tags.filter((t) => t.includes('@')) })}
                    placeholder="email@example.com"
                    hint="Press Enter after each address."
                  />
                )}
                {alerts.notification_channels.bluesky && (
                  <TextField label="Bluesky handle" placeholder="@handle.bsky.social" value={alerts.bluesky_handle ?? ''} onChange={(v) => setA({ bluesky_handle: v || null })} />
                )}
                <Slider
                  label="Lowest confidence to alert on"
                  value={Math.round(alerts.min_confidence * 100)}
                  onValueChange={(v) => setA({ min_confidence: v / 100 })}
                  min={50}
                  max={100}
                  step={5}
                  valueText={`${Math.round(alerts.min_confidence * 100)}%`}
                  hint="Only topics the detection is at least this sure about trigger an alert."
                />
                <Slider
                  label="Quiet period between alerts"
                  value={alerts.cooldown_minutes}
                  onValueChange={(v) => setA({ cooldown_minutes: v })}
                  min={60}
                  max={1440}
                  step={60}
                  valueText={`${alerts.cooldown_minutes / 60} hours`}
                  hint="The shortest time between two batches of alerts."
                />
                <Stack gap="sm">
                  <Eyebrow as="h3">Alert on</Eyebrow>
                  <Stack direction="row" gap="sm">
                    {NOTIFICATION_FILTER_OPTIONS.map((o) => {
                      const on = alerts.detection_type_filters.includes(o.value);
                      return (
                        <Chip key={o.value} tone={on ? 'accent' : 'neutral'} variant={on ? 'fill' : 'outline'} icon={on ? <Icon name="Check" size="sm" /> : undefined} label={`${on ? 'Stop alerting' : 'Alert'} on ${o.label}: ${o.description}`} onClick={() => toggleType(o.value)}>
                          {o.label}
                        </Chip>
                      );
                    })}
                  </Stack>
                  {NOTIFICATION_FILTER_OPTIONS.map((o) => <Text key={o.value} variant="caption">{`${o.label}: ${o.description}.`}</Text>)}
                  {alerts.notifications_enabled && alerts.detection_type_filters.length === 0 && (
                    <Text variant="caption" tone="error">Nothing is picked, so no alert will ever be sent.</Text>
                  )}
                </Stack>
                {/* The test reads the saved settings on the server, not the edits on screen */}
                <Text variant="caption">{alertsDirty ? 'You have unsaved changes. “Send a test” uses the saved settings, so save first to test these.' : '“Send a test” sends one message through each channel switched on in the saved settings.'}</Text>
              </>
            )}
            {note && <Banner tone={note.tone} title={note.tone === 'error' ? 'Something went wrong' : 'Done'} description={note.text} />}
          </Stack>
        </TabPanel>

        <TabPanel value="about">
          <Stack gap="lg">
            <Stack gap="sm">
              <Eyebrow as="h3">How detection works</Eyebrow>
              <Text>
                Detection finds new developments in your collected articles. It takes a sample of recent articles that look unlike earlier coverage, has the AI
                propose specific themes, then checks each theme against the wider collection by meaning, keeping only those with enough supporting articles.
              </Text>
            </Stack>
            <Stack gap="sm">
              <Eyebrow as="h3">How a theme’s score is made up</Eyebrow>
              <LineItems
                label="Score weights"
                items={[
                  { label: 'Volume: how many articles', amount: '25%' },
                  { label: 'Velocity: how fast coverage is growing', amount: '30%' },
                  { label: 'Diversity: how many different sources', amount: '20%' },
                  { label: 'Novelty: how unlike earlier coverage', amount: '25%' },
                ]}
              />
            </Stack>
          </Stack>
        </TabPanel>
      </Tabs>
    </Dialog>
  );
}
