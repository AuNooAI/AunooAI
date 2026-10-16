import { useEffect, useState } from 'react';
import { Button, Checkbox, Dialog, DialogClose, Eyebrow, Grid, Select, SettingRow, Skeleton, Stack, Switch, Text, TextField } from '@aunoo/ui';
import { evaluateAlertsNow, getAlertConfig, updateAlertConfig, type BWAlertConfig } from '@monolith/brandWatcherApi';
import { errorText } from '../../../../shell';

/*
 * Adverse-media alerting, on GET/PUT the alert config routes as the old modal did. The rules run
 * on the server about every 15 minutes; "Check now" runs them once. None of this calls an AI model.
 */

const RULES: { key: string; label: string; params: { k: string; label: string; def: number; step?: number }[] }[] = [
  { key: 'neg_social_spike', label: 'Negative social posts spike', params: [{ k: 'min_prior', label: 'At least this many before', def: 2 }, { k: 'multiplier', label: 'Times the earlier count', def: 2, step: 0.5 }] },
  { key: 'high_reach_negative', label: 'High-reach negative post', params: [{ k: 'min_engagement', label: 'Engagement at least', def: 50 }, { k: 'window_hours', label: 'Window (hours)', def: 24 }] },
  { key: 'news_net_negative', label: 'News sentiment turns negative', params: [{ k: 'net_threshold', label: 'Net sentiment at or below', def: -20 }, { k: 'min_scored', label: 'Scored articles at least', def: 5 }, { k: 'window_days', label: 'Window (days)', def: 7 }] },
  { key: 'category_spike', label: 'Category coverage spike', params: [{ k: 'multiplier', label: 'Times normal', def: 2, step: 0.5 }, { k: 'min_count', label: 'Articles at least', def: 5 }] },
  { key: 'high_risk_finding', label: 'High-severity risk finding', params: [{ k: 'window_hours', label: 'Window (hours)', def: 24 }] },
  { key: 'neg_consensus_story', label: 'Story negative across sources', params: [{ k: 'min_scored', label: 'Sources at least', def: 3 }, { k: 'neg_share', label: 'Negative share at least', def: 0.7, step: 0.05 }, { k: 'window_hours', label: 'Window (hours)', def: 48 }] },
  { key: 'new_critic', label: 'New critic', params: [{ k: 'recent_hours', label: 'Window (hours)', def: 48 }, { k: 'min_recent_neg', label: 'Negative posts at least', def: 2 }, { k: 'min_engagement_single', label: 'Or one post with engagement', def: 50 }, { k: 'lookback_days', label: 'Look back (days)', def: 30 }] },
  { key: 'coordinated_negative', label: 'Coordinated negativity', params: [{ k: 'min_authors', label: 'Accounts at least', def: 3 }, { k: 'window_hours', label: 'Window (hours)', def: 72 }] },
  { key: 'glassdoor_deterioration', label: 'Glassdoor rating falls', params: [{ k: 'rating_drop', label: 'Rating drop at least', def: 0.2, step: 0.1 }, { k: 'outlook_drop', label: 'Outlook drop at least', def: 0.1, step: 0.05 }, { k: 'lookback_days', label: 'Look back (days)', def: 35 }] },
];
const HOURS = Array.from({ length: 24 }, (_, h) => ({ value: String(h), label: `${String(h).padStart(2, '0')}:00 UTC` }));

interface Props {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  notify: (m: string) => void;
}

export function AlertSettingsDialog({ open, onOpenChange, notify }: Props) {
  const [cfg, setCfg] = useState<BWAlertConfig | null>(null);
  const [recipients, setRecipients] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setCfg(null);
    getAlertConfig().then(
      (c) => { setCfg(c); setRecipients((c.email_recipients || []).join(', ')); },
      (e: unknown) => { notify(`Alert settings didn’t load: ${errorText(e)}`); onOpenChange(false); },
    );
  }, [open, notify, onOpenChange]);

  const set = (patch: Partial<BWAlertConfig>) => setCfg((c) => (c ? { ...c, ...patch } : c));
  const channels = cfg?.channels ?? {};
  const digest = channels.digest ?? {};
  const setChannels = (patch: Partial<BWAlertConfig['channels']>) => set({ channels: { ...channels, ...patch } });

  const save = async () => {
    if (!cfg) return;
    setBusy(true);
    try {
      await updateAlertConfig({
        enabled: cfg.enabled, rules: cfg.rules, channels: cfg.channels, webhook_url: cfg.webhook_url, cooldown_hours: cfg.cooldown_hours,
        email_recipients: recipients.split(',').map((x) => x.trim()).filter(Boolean),
      });
      notify('Alert settings saved');
      onOpenChange(false);
    } catch (e) {
      notify(`Not saved: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const checkNow = async () => {
    setBusy(true);
    try {
      const r = await evaluateAlertsNow();
      notify(r.created ? `${r.created} new ${r.created === 1 ? 'alert' : 'alerts'} raised` : 'Checked: no new alerts');
    } catch (e) {
      notify(`Check failed: ${errorText(e)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Adverse-media alerts"
      description="The rules run on the server about every 15 minutes."
      footer={
        <>
          <Button variant="ghost" size="lg" disabled={busy || !cfg} onClick={() => void checkNow()}>Check now</Button>
          <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
          <Button size="lg" disabled={busy || !cfg} onClick={() => void save()}>Save</Button>
        </>
      }
    >
      {!cfg ? <Skeleton variant="text" lines={8} /> : (
        <Stack gap="lg">
          <Switch label="Alerts on" checked={cfg.enabled} onCheckedChange={(enabled) => set({ enabled })} />
          <Stack gap="sm">
            <Eyebrow as="h3">Send alerts by</Eyebrow>
            <Stack direction="row" gap="md">
              <Checkbox label="In the app" checked={!!channels.in_app} onCheckedChange={(in_app) => setChannels({ in_app })} />
              <Checkbox label="Email" checked={!!channels.email} onCheckedChange={(email) => setChannels({ email })} />
              <Checkbox label="Webhook" checked={!!channels.webhook} onCheckedChange={(webhook) => setChannels({ webhook })} />
            </Stack>
          </Stack>
          <Stack gap="sm">
            <Switch
              label="Digest email"
              description="Sentiment, findings, alerts and case actions, sent to the recipients below."
              checked={!!digest.enabled}
              onCheckedChange={(enabled) => setChannels({ digest: { ...digest, enabled } })}
            />
            <Grid columns={2} stackAt="small" gap="md">
              <Select
                label="How often"
                fullWidth
                options={[{ value: 'daily', label: 'Daily' }, { value: 'weekly', label: 'Weekly, on Mondays' }]}
                value={digest.frequency || 'daily'}
                onValueChange={(v) => setChannels({ digest: { ...digest, frequency: v as 'daily' | 'weekly' } })}
              />
              <Select label="At" fullWidth options={HOURS} value={String(digest.hour_utc ?? 6)} onValueChange={(v) => setChannels({ digest: { ...digest, hour_utc: Number(v) } })} />
            </Grid>
          </Stack>
          <TextField label="Email recipients" hint="Separate addresses with commas." value={recipients} onChange={setRecipients} />
          <TextField label="Webhook URL" hint="A Slack incoming webhook works." value={cfg.webhook_url ?? ''} onChange={(webhook_url) => set({ webhook_url })} />
          <Select
            label="Quiet period"
            hint="The same rule for the same brand alerts at most once in this time."
            fullWidth
            options={[6, 12, 24, 48, 72].map((h) => ({ value: String(h), label: `${h} hours` }))}
            value={String(cfg.cooldown_hours)}
            onValueChange={(v) => set({ cooldown_hours: Number(v) })}
          />
          <Stack gap="sm">
            <Eyebrow as="h3">Rules</Eyebrow>
            <Text variant="caption">The numbers are the server’s defaults until you change them.</Text>
            {RULES.map((rd) => {
              const r = (cfg.rules || {})[rd.key] || {};
              const on = r.enabled !== false;
              const setRule = (patch: Record<string, unknown>) => set({ rules: { ...(cfg.rules || {}), [rd.key]: { ...r, ...patch } } });
              return (
                <SettingRow key={rd.key} title={rd.label} actions={<Switch label={<span className="visually-hidden">{rd.label}</span>} checked={on} onCheckedChange={(enabled) => setRule({ enabled })} />}>
                  {on && (
                    <Grid columns={2} stackAt="small" gap="sm">
                      {rd.params.map((pm) => (
                        <TextField
                          key={pm.k}
                          label={pm.label}
                          type="number"
                          step={pm.step ?? 1}
                          value={String(r[pm.k] ?? pm.def)}
                          onChange={(v) => setRule({ [pm.k]: v === '' ? pm.def : Number(v) })}
                        />
                      ))}
                    </Grid>
                  )}
                </SettingRow>
              );
            })}
          </Stack>
        </Stack>
      )}
    </Dialog>
  );
}
