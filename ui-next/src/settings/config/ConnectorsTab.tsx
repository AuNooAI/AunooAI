import { useCallback, useEffect, useState } from 'react';
import {
  Banner, Button, Chip, CodeBlock, Collapsible, CollapsibleContent, CollapsibleTrigger, CopyField, Grid, Icon, Panel, Skeleton, Stack, Table, Text,
  TextField,
} from '@aunoo/ui';
import { ApiError, api, errorText } from '../../shell';
import type { SettingsPageProps } from '../types';
import { fmtDate, type McpCall, type McpConnection, type McpInstall, type McpKey } from './api';

/*
 * Connectors (MCP), as the old Connectors tab: the server address and setup snippets, your own keys
 * (a new key is shown once), assistants you've connected, and for admins every key on the site and
 * the recent calls. Everything acts as the signed-in account.
 */

const SNIPPETS: { id: string; label: string }[] = [
  { id: 'claude_code', label: 'Claude Code' },
  { id: 'cursor', label: 'Cursor (mcp.json)' },
  { id: 'claude_desktop', label: 'Claude Desktop (claude_desktop_config.json)' },
];

export function ConnectorsTab({ notify, askConfirm }: SettingsPageProps) {
  const [install, setInstall] = useState<McpInstall | null>(null);
  const [keys, setKeys] = useState<McpKey[] | null>(null);
  const [connections, setConnections] = useState<McpConnection[] | null>(null);
  const [adminKeys, setAdminKeys] = useState<McpKey[] | null>(null);
  const [calls, setCalls] = useState<McpCall[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [days, setDays] = useState('90');
  const [minting, setMinting] = useState(false);
  const [newKey, setNewKey] = useState<string | null>(null);

  const loadMine = useCallback(() => {
    api<McpKey[]>('/api/mcp/me/keys').then((r) => setKeys((r ?? []).filter((k) => k.is_active)), (e) => setError(errorText(e)));
    api<McpConnection[]>('/api/mcp/me/connections').then((r) => setConnections(r ?? []), (e) => setError(errorText(e)));
  }, []);
  // Admin lists answer 403 for everyone else, which just hides them
  const loadAdmin = useCallback(() => {
    api<McpKey[]>('/api/mcp-keys').then(
      (r) => {
        setAdminKeys(r ?? []);
        api<McpCall[]>('/api/mcp-keys/calls?limit=50').then((c) => setCalls(c ?? []), () => setCalls([]));
      },
      (e) => {
        if (!(e instanceof ApiError && e.status === 403)) setError(errorText(e));
        setAdminKeys(null);
      },
    );
  }, []);
  useEffect(() => {
    api<McpInstall>('/api/mcp/me/install').then(setInstall, (e) => setError(errorText(e)));
    loadMine();
    loadAdmin();
  }, [loadMine, loadAdmin]);

  const mint = async () => {
    if (!name.trim()) return;
    setMinting(true);
    try {
      const n = parseInt(days, 10);
      const row = await api<{ plaintext: string }>('/api/mcp/me/keys', { method: 'POST', json: { name: name.trim(), expires_days: Number.isFinite(n) && n > 0 ? n : null } });
      setNewKey(row.plaintext);
      setName('');
      loadMine();
      loadAdmin();
    } catch (e) {
      notify(`Key not created: ${errorText(e)}`);
    } finally {
      setMinting(false);
    }
  };
  const revoke = (k: McpKey, admin = false) =>
    askConfirm({
      title: admin ? `Revoke key #${k.id}?` : `Revoke “${k.name}”?`,
      message: 'Anything using this key stops working straight away.',
      action: 'Revoke key',
      onConfirm: async () => {
        try {
          await api(admin ? `/api/mcp-keys/${k.id}` : `/api/mcp/me/keys/${k.id}`, { method: 'DELETE' });
          notify('Key revoked');
          loadMine();
          loadAdmin();
        } catch (e) {
          notify(`Not revoked: ${errorText(e)}`);
        }
      },
    });
  const disconnect = (c: McpConnection) =>
    askConfirm({
      title: `Disconnect ${c.client_name}?`,
      message: 'It loses access within the hour and has to ask for access again.',
      action: 'Disconnect',
      onConfirm: async () => {
        try {
          await api(`/api/mcp/me/connections/${encodeURIComponent(c.client_id)}`, { method: 'DELETE' });
          notify(`${c.client_name} disconnected`);
          loadMine();
        } catch (e) {
          notify(`Not disconnected: ${errorText(e)}`);
        }
      },
    });

  return (
    <Grid columns="main-aside" stackAt="wide" gap="md">
      <Stack gap="lg">
        {error && <Banner tone="error" title="Something didn’t load" description={error} />}
        <Panel
          title="Connect an assistant"
          description={install ? `Use this site from Claude, ChatGPT, Cursor or any assistant that speaks the Model Context Protocol (MCP). Everything acts as ${install.username}.` : undefined}
        >
          {!install ? <Skeleton variant="text" lines={4} /> : (
            <Stack gap="md">
              <CopyField label="Server address" value={install.mcp_url} />
              <Text variant="caption">
                claude.ai and ChatGPT: add a custom connector with this address and leave the client fields empty. A browser tab opens this site’s sign-in,
                then an Allow screen; no key is needed. Claude Code, Cursor and Claude Desktop: create a key below and use one of these snippets.
              </Text>
              {SNIPPETS.map((s) => (
                <Collapsible key={s.id}>
                  <CollapsibleTrigger variant="ghost" size="sm">{s.label}</CollapsibleTrigger>
                  <CollapsibleContent>
                    <CodeBlock label={s.label} code={install.snippets?.[s.id] ?? ''} />
                  </CollapsibleContent>
                </Collapsible>
              ))}
            </Stack>
          )}
        </Panel>

        <Panel title="My keys" description="A key signs requests as you, and is shown once when it’s created. Revoke it here if a laptop or config file leaks.">
          <Stack gap="md">
            <Grid columns={2} stackAt="small" gap="md">
              <TextField label="Name" value={name} onChange={setName} onSubmit={() => void mint()} placeholder="e.g. claude-code on my laptop" />
              <TextField label="Expires in (days)" type="number" min={1} max={3650} value={days} onChange={setDays} />
            </Grid>
            <div><Button iconStart={<Icon name="Key" size="sm" />} busy={minting} disabled={!name.trim() || minting} onClick={() => void mint()}>Create key</Button></div>
            {newKey && (
              <Stack gap="sm">
                <Banner tone="success" title="Copy this key now" description="It won’t be shown again." action={<Button size="sm" variant="secondary" onClick={() => setNewKey(null)}>I’ve copied it</Button>} />
                <CopyField label="New key" value={newKey} />
              </Stack>
            )}
            {!keys ? <Skeleton variant="text" lines={3} /> : (
              <Table
                caption="My keys"
                hideCaption
                rows={keys}
                rowKey={(k) => String(k.id)}
                emptyText="No active keys."
                columns={[
                  { key: 'name', header: 'Name', rowHeader: true, wrap: true },
                  { key: 'prefix', header: 'Starts with', render: (k) => `${k.key_prefix}…` },
                  { key: 'created', header: 'Created', render: (k) => fmtDate(k.created_at) },
                  { key: 'expires', header: 'Expires', render: (k) => fmtDate(k.expires_at) },
                  { key: 'used', header: 'Last used', render: (k) => fmtDate(k.last_used_at) },
                  { key: 'actions', header: 'Actions', align: 'end', render: (k) => <Button size="sm" variant="ghost" onClick={() => revoke(k)}>Revoke</Button> },
                ]}
              />
            )}
          </Stack>
        </Panel>

        <Panel title="Connected apps" description="Assistants you allowed through the Allow screen. Disconnecting stops them within the hour.">
          {!connections ? <Skeleton variant="text" lines={3} /> : (
            <Table
              caption="Connected apps"
              hideCaption
              rows={connections}
              rowKey={(c) => c.client_id}
              emptyText="No connected apps."
              columns={[
                { key: 'app', header: 'App', rowHeader: true, render: (c) => c.client_name },
                { key: 'connected', header: 'Connected', render: (c) => fmtDate(c.connected_at) },
                { key: 'used', header: 'Last used', render: (c) => fmtDate(c.last_used_at) },
                { key: 'renews', header: 'Renews until', render: (c) => fmtDate(c.expires_at) },
                { key: 'actions', header: 'Actions', align: 'end', render: (c) => <Button size="sm" variant="ghost" onClick={() => disconnect(c)}>Disconnect</Button> },
              ]}
            />
          )}
        </Panel>

        {adminKeys && (
          <Panel title="All keys" description="Every key on this site. Only admins see this." headerAside={<Chip size="sm" tone="accent">Admin</Chip>}>
            <Table
              caption="All keys on this site"
              hideCaption
              scroll
              rows={adminKeys}
              rowKey={(k) => String(k.id)}
              emptyText="No keys on this site."
              columns={[
                { key: 'id', header: '#', render: (k) => k.id },
                { key: 'user', header: 'User', rowHeader: true, render: (k) => k.username ?? '—' },
                { key: 'name', header: 'Name', wrap: true },
                { key: 'prefix', header: 'Starts with', render: (k) => k.key_prefix },
                { key: 'active', header: 'Active', render: (k) => (k.is_active ? 'Yes' : 'No') },
                { key: 'expires', header: 'Expires', render: (k) => fmtDate(k.expires_at) },
                { key: 'used', header: 'Last used', render: (k) => fmtDate(k.last_used_at) },
                { key: 'actions', header: 'Actions', align: 'end', render: (k) => (k.is_active ? <Button size="sm" variant="ghost" onClick={() => revoke(k, true)}>Revoke</Button> : null) },
              ]}
            />
          </Panel>
        )}
        {adminKeys && calls && (
          <Panel title="Recent calls" description="The last 50 calls through connectors, by anyone." headerAside={<Chip size="sm" tone="accent">Admin</Chip>}>
            <Table
              caption="Recent connector calls"
              hideCaption
              scroll
              rows={calls}
              rowKey={(c) => `${c.created_at}-${c.tool_name}-${c.username}`}
              emptyText="No calls yet."
              columns={[
                { key: 'when', header: 'When', render: (c) => fmtDate(c.created_at) },
                { key: 'user', header: 'User', rowHeader: true, render: (c) => c.username },
                { key: 'via', header: 'Through', render: (c) => c.auth_kind },
                { key: 'tool', header: 'Tool', render: (c) => c.tool_name },
                { key: 'status', header: 'Result', render: (c) => c.status },
                { key: 'ms', header: 'Time (ms)', align: 'end', render: (c) => c.duration_ms ?? '—' },
              ]}
            />
          </Panel>
        )}
      </Stack>

      <Stack gap="lg">
        <Panel title="What a connected assistant can do">
          {!install ? <Skeleton variant="text" lines={6} /> : (
            <Stack gap="md">
              <Stack direction="row" gap="sm">{install.tools.map((t) => <Chip key={t} size="sm" tone="muted">{t}</Chip>)}</Stack>
              <Text variant="label">Playbooks</Text>
              <Stack direction="row" gap="sm">{install.prompts.map((p) => <Chip key={p} size="sm" tone="muted">{p}</Chip>)}</Stack>
            </Stack>
          )}
        </Panel>
        <Banner tone="warning" title="Access follows your account" description="Keys and connected apps see what you see, and stop working when your account is switched off. Every call is logged." />
      </Stack>
    </Grid>
  );
}
