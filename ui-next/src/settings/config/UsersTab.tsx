import { useCallback, useEffect, useState } from 'react';
import { Banner, Button, Checkbox, Chip, CopyField, Dialog, DialogClose, Grid, Icon, Panel, Select, Skeleton, Stack, Table, Text, TextField } from '@aunoo/ui';
import { ApiError, api, errorText } from '../../shell';
import type { SettingsPageProps } from '../types';
import { getMe, getUsers, type Me, type UserRow } from './api';

/*
 * User accounts, as the old Users tab. Everyone sees the list only if they're an admin; admins also
 * create accounts, reset passwords (by an emailed link, or a one-time temporary password) and
 * delete accounts. Nobody can reset or delete their own account from here.
 */

export function UsersTab({ notify, askConfirm }: SettingsPageProps) {
  const [me, setMe] = useState<Me | null>(null);
  const [users, setUsers] = useState<UserRow[] | null>(null);
  const [restricted, setRestricted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resetFor, setResetFor] = useState<UserRow | null>(null);

  const load = useCallback(() => {
    setError(null);
    getMe().then(setMe, () => setMe(null));
    getUsers().then(
      (u) => {
        setUsers(u);
        setRestricted(false);
      },
      (e) => {
        setUsers([]);
        if (e instanceof ApiError && e.status === 403) setRestricted(true);
        else setError(errorText(e));
      },
    );
  }, []);
  useEffect(load, [load]);

  const admin = me?.role === 'admin';
  const remove = (u: UserRow) =>
    askConfirm({
      title: `Delete the account “${u.username}”?`,
      message: 'They can no longer sign in. Topics and content they worked on stay. This can’t be undone.',
      action: 'Delete account',
      onConfirm: async () => {
        try {
          await api(`/api/users/${encodeURIComponent(u.username)}`, { method: 'DELETE' });
          notify(`${u.username} deleted`);
          load();
        } catch (e) {
          notify(`Not deleted: ${errorText(e)}`);
        }
      },
    });

  return (
    <Grid columns="main-aside" stackAt="wide" gap="md">
      <Stack gap="lg">
        {admin && <CreateUser notify={notify} onCreated={load} />}
        <Panel title="All users" description={me ? `You’re signed in as ${me.username} (${me.role}).` : undefined}>
          {restricted ? (
            <Banner tone="info" title="Only admins can see the user list" description="Ask an administrator if you need to manage accounts." />
          ) : error ? (
            <Banner tone="error" title="Users didn’t load" description={error} />
          ) : !users ? <Skeleton variant="text" lines={6} /> : (
            <Table
              caption="User accounts"
              hideCaption
              rows={users}
              rowKey={(u) => u.username}
              emptyText="No users found."
              columns={[
                { key: 'username', header: 'Username', rowHeader: true, render: (u) => (u.username === me?.username ? `${u.username} (you)` : u.username) },
                { key: 'email', header: 'Email', wrap: true },
                {
                  key: 'role', header: 'Role',
                  render: (u) => (
                    <Stack direction="row" gap="sm" wrap={false}>
                      <Chip size="sm" tone={u.role === 'admin' ? 'accent' : 'muted'}>{u.role === 'admin' ? 'Admin' : 'User'}</Chip>
                      {u.is_oauth && <Chip size="sm" tone="info">Single sign-on</Chip>}
                    </Stack>
                  ),
                },
                { key: 'status', header: 'Status', render: (u) => <Chip size="sm" tone={u.is_active ? 'success' : 'error'}>{u.is_active ? 'Active' : 'Inactive'}</Chip> },
                {
                  key: 'actions', header: 'Actions', align: 'end',
                  render: (u) =>
                    !admin || u.username === me?.username ? null : (
                      <Stack direction="row" gap="sm" wrap={false}>
                        {!u.is_oauth && <Button size="sm" variant="secondary" iconStart={<Icon name="Key" size="sm" />} onClick={() => setResetFor(u)}>Reset password</Button>}
                        <Button size="sm" variant="ghost" onClick={() => remove(u)}>Delete</Button>
                      </Stack>
                    ),
                },
              ]}
            />
          )}
        </Panel>
      </Stack>
      <Panel title="User roles" description="What each role can do.">
        <Stack gap="md">
          <Stack gap="sm">
            <Text variant="label">Admin</Text>
            <Text variant="caption">Everything a user can do, plus creating and managing accounts, every configuration setting and site-wide settings.</Text>
          </Stack>
          <Stack gap="sm">
            <Text variant="label">User</Text>
            <Text variant="caption">Views and creates content, uses the research features and changes their own password. Can’t manage other accounts.</Text>
          </Stack>
          <Banner tone="info" title="One shared workspace" description="Every user can see and manage all topics and content." />
        </Stack>
      </Panel>
      <ResetPasswordDialog user={resetFor} onClose={() => setResetFor(null)} notify={notify} />
    </Grid>
  );
}

function CreateUser({ notify, onCreated }: { notify: (m: string) => void; onCreated: () => void }) {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('user');
  const [force, setForce] = useState(true);
  const [skipOnboarding, setSkip] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const create = async () => {
    setError(null);
    if (password.length < 8) return setError(`The password needs at least 8 characters (it has ${password.length}).`);
    setBusy(true);
    try {
      await api('/api/users/', {
        method: 'POST',
        json: { username: username.trim(), email: email.trim(), password, role, force_password_change: force, completed_onboarding: skipOnboarding },
      });
      notify(`${username.trim()} created`);
      setUsername('');
      setEmail('');
      setPassword('');
      setRole('user');
      setForce(true);
      setSkip(false);
      onCreated();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel title="Create a user" description="Add an account for someone on your team.">
      <Stack gap="md">
        <Grid columns={2} stackAt="small" gap="md">
          <TextField label="Username" value={username} onChange={setUsername} autoComplete="off" />
          <TextField label="Email" type="email" value={email} onChange={setEmail} autoComplete="off" placeholder="user@example.com" />
          <TextField label="Password" type="password" value={password} onChange={setPassword} autoComplete="new-password" hint="At least 8 characters." />
          <Select label="Role" options={[{ value: 'user', label: 'User' }, { value: 'admin', label: 'Admin' }]} value={role} onValueChange={setRole} fullWidth />
        </Grid>
        <Checkbox label="Make them change the password when they first sign in" checked={force} onCheckedChange={setForce} />
        <Checkbox label="Skip the welcome wizard (mark onboarding as done)" checked={skipOnboarding} onCheckedChange={setSkip} />
        {error && <Banner tone="error" title="Account not created" description={error} />}
        <div><Button iconStart={<Icon name="UserPlus" size="sm" />} busy={busy} disabled={!username.trim() || !email.trim() || !password || busy} onClick={() => void create()}>Create user</Button></div>
      </Stack>
    </Panel>
  );
}

/** Email a reset link (24 hours, single use) or make a temporary password shown once, as the old page */
function ResetPasswordDialog({ user, onClose, notify }: { user: UserRow | null; onClose: () => void; notify: (m: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [temp, setTemp] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setTemp(null);
    setError(null);
  }, [user]);
  const hasEmail = !!user?.email?.includes('@');
  const reset = async (mode: 'email' | 'temp') => {
    if (!user) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ method: string; email?: string; expires_hours?: number; temp_password?: string }>(`/api/users/${encodeURIComponent(user.username)}/reset-password`, { method: 'POST', json: { mode } });
      if (r.method === 'email') {
        notify(`Reset link sent to ${r.email}. It works once, for ${r.expires_hours ?? 24} hours.`);
        onClose();
      } else {
        setTemp(r.temp_password ?? '');
      }
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog
      open={!!user}
      onOpenChange={(o) => !o && onClose()}
      title={user ? `Reset the password for ${user.username}` : 'Reset password'}
      description={temp === null ? (hasEmail ? `Email ${user?.email} a link to set a new password, or make a temporary password to pass on yourself.` : 'This account has no email address, so the only option is a temporary password.') : undefined}
      footer={
        temp !== null ? <DialogClose><Button size="lg">Done</Button></DialogClose> : (
          <>
            <DialogClose><Button variant="secondary" size="lg">Cancel</Button></DialogClose>
            <Button variant={hasEmail ? 'secondary' : 'primary'} size="lg" busy={busy} disabled={busy} onClick={() => void reset('temp')}>Make a temporary password</Button>
            {hasEmail && <Button size="lg" busy={busy} disabled={busy} onClick={() => void reset('email')}>Email a reset link</Button>}
          </>
        )
      }
    >
      <Stack gap="md">
        {temp !== null ? (
          <>
            <Banner tone="warning" title="Copy it now" description="This temporary password is shown only once. They must change it when they first sign in." />
            <CopyField label="Temporary password" value={temp} />
          </>
        ) : (
          <Text variant="caption">A reset link works once, for 24 hours. A temporary password replaces their current one straight away.</Text>
        )}
        {error && <Banner tone="error" title="Password not reset" description={error} />}
      </Stack>
    </Dialog>
  );
}
