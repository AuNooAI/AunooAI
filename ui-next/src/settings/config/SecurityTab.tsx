import { useState } from 'react';
import { Banner, Button, Grid, Icon, Panel, Stack, Text, TextField } from '@aunoo/ui';
import { api, errorText } from '../../shell';
import type { SettingsPageProps } from '../types';

/*
 * Change your own password, as the old Security tab. The old page listed the rules but sent any
 * password; this one checks them before sending, and shows which are met as you type.
 */

const RULES: { label: string; ok: (p: string) => boolean }[] = [
  { label: 'At least 8 characters', ok: (p) => p.length >= 8 },
  { label: 'At least one capital letter', ok: (p) => /[A-Z]/.test(p) },
  { label: 'At least one number', ok: (p) => /\d/.test(p) },
  { label: 'At least one special character', ok: (p) => /[^A-Za-z0-9]/.test(p) },
];

export function SecurityTab({ notify }: Pick<SettingsPageProps, 'notify'>) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rulesMet = RULES.every((r) => r.ok(next));
  const matches = next === confirm;

  const save = async () => {
    setError(null);
    if (!rulesMet) return setError('The new password doesn’t meet every rule.');
    if (!matches) return setError('The two new passwords don’t match.');
    setBusy(true);
    try {
      await api('/api/change-password', { method: 'POST', json: { current_password: current, new_password: next } });
      notify('Password changed');
      setCurrent('');
      setNext('');
      setConfirm('');
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Grid columns="main-aside" stackAt="wide" gap="md">
      <Panel title="Change password" description="Change the password for your own account. Use a strong one you don’t use anywhere else.">
        <Stack gap="md">
          <TextField label="Current password" type="password" autoComplete="current-password" value={current} onChange={setCurrent} />
          <TextField label="New password" type="password" autoComplete="new-password" value={next} onChange={setNext} />
          <TextField label="Confirm the new password" type="password" autoComplete="new-password" value={confirm} onChange={setConfirm} error={confirm && !matches ? 'Doesn’t match the new password.' : undefined} />
          {error && <Banner tone="error" title="Password not changed" description={error} />}
          <div><Button iconStart={<Icon name="Lock" size="sm" />} busy={busy} disabled={!current || !next || !confirm || busy} onClick={() => void save()}>Change password</Button></div>
        </Stack>
      </Panel>
      <Panel title="Password rules" description="The new password needs all of these.">
        <Stack as="ul" gap="sm" label="Password rules">
          {RULES.map((r) => (
            <li key={r.label}>
              <Stack direction="row" gap="sm" wrap={false}>
                <Icon name={next && r.ok(next) ? 'CheckCircle' : 'Minus'} size="sm" />
                <Text as="span">{r.label}</Text>
              </Stack>
            </li>
          ))}
        </Stack>
      </Panel>
    </Grid>
  );
}
