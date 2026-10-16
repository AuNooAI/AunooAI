import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Banner, Button, CodeBlock, Collapsible, CollapsibleContent, CollapsibleTrigger, DiffView, EmptyState, Grid, Icon, Panel, Select, Skeleton, Stack, Table, Text, TextArea,
} from '@aunoo/ui';
import { errorText } from '../../shell';
import {
  DEFAULT_VARIABLES, deleteVersion, getVersion, joinUserPrompt, listTypes, listVersions, restoreVersion, saveVersion, splitUserPrompt,
  type PromptType, type PromptVersion,
} from '../prompts/api';
import type { SettingsPageProps } from '../types';

/*
 * Prompt Engineering, as the old /promptmanager page: pick a prompt, read or edit its role (system
 * prompt) and instructions (user prompt), save a new version, and restore, compare or delete older
 * ones. Dashboard prompts end with a fixed output format that the pages rely on; it is shown but
 * can't be edited, and is put back on save.
 */

const when = (iso?: string) => (iso ? new Date(iso).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' }) : '');

export function PromptManager({ notify, askConfirm }: SettingsPageProps) {
  const [types, setTypes] = useState<PromptType[] | null>(null);
  const [typeError, setTypeError] = useState<string | null>(null);
  const [type, setType] = useState('');
  const [versions, setVersions] = useState<PromptVersion[] | null>(null);
  const [hash, setHash] = useState('current');
  const [loaded, setLoaded] = useState<PromptVersion | null>(null);
  const [current, setCurrent] = useState<PromptVersion | null>(null);
  const [system, setSystem] = useState('');
  const [instructions, setInstructions] = useState('');
  const [busy, setBusy] = useState<null | 'load' | 'save' | 'restore' | 'delete'>(null);
  const [error, setError] = useState<string | null>(null);
  const [comparing, setComparing] = useState(false);

  useEffect(() => {
    listTypes().then(setTypes, (e) => {
      setTypes([]);
      setTypeError(errorText(e));
    });
  }, []);

  const format = loaded ? splitUserPrompt(loaded.user_prompt ?? '').format : null;
  const dirty = !!loaded && (system !== (loaded.system_prompt ?? '') || instructions !== splitUserPrompt(loaded.user_prompt ?? '').instructions);

  const openVersion = useCallback(async (t: string, h: string) => {
    setBusy('load');
    setError(null);
    setComparing(false);
    try {
      const v = await getVersion(t, h);
      setLoaded(v);
      setHash(h);
      setSystem(v.system_prompt ?? '');
      setInstructions(splitUserPrompt(v.user_prompt ?? '').instructions);
      if (h === 'current') setCurrent(v);
    } catch (e) {
      setError(`The prompt didn’t load: ${errorText(e)}`);
    } finally {
      setBusy(null);
    }
  }, []);

  const openType = useCallback(async (t: string) => {
    setType(t);
    setVersions(null);
    setLoaded(null);
    setCurrent(null);
    if (!t) return;
    listVersions(t).then(setVersions, (e) => {
      setVersions([]);
      setError(`Versions didn’t load: ${errorText(e)}`);
    });
    await openVersion(t, 'current');
  }, [openVersion]);

  // Switching away from unsaved edits asks first
  const guard = (go: () => void) => {
    if (!dirty) return go();
    askConfirm({ title: 'Discard your edits?', message: 'The changes on this page haven’t been saved as a version.', action: 'Discard edits', onConfirm: go });
  };

  const reloadVersions = () => type && listVersions(type).then(setVersions, () => undefined);

  const save = async () => {
    if (!type || !loaded) return;
    setBusy('save');
    setError(null);
    try {
      // Keep the prompt's other fields (schema, variables, metadata…) as the old page did
      const { hash: _h, version: _v, created_at: _c, updated_at: _u, restored_from_default: _r, ...rest } = loaded as PromptVersion & { updated_at?: string; restored_from_default?: boolean };
      void _h; void _v; void _c; void _u; void _r;
      await saveVersion(type, { ...rest, system_prompt: system, user_prompt: joinUserPrompt(instructions, format) });
      notify('New version saved and made active');
      await reloadVersions();
      await openVersion(type, 'current');
    } catch (e) {
      // The old page reported success even when the server refused the prompt
      setError(`Not saved: ${errorText(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const restore = () => {
    if (!type || hash === 'current') return;
    askConfirm({
      title: `Make version ${loaded?.version ?? ''} active?`,
      message: 'It replaces the active prompt. Every AI step that uses this prompt runs with it from now on. The version that’s active now stays in the history.',
      action: 'Make it active',
      onConfirm: async () => {
        setBusy('restore');
        setError(null);
        try {
          await restoreVersion(type, hash);
          notify(`Version ${loaded?.version ?? ''} is active again`);
          await reloadVersions();
          await openVersion(type, 'current');
        } catch (e) {
          setError(`Not restored: ${errorText(e)}`);
        } finally {
          setBusy(null);
        }
      },
    });
  };

  const remove = () => {
    if (!type || hash === 'current') return;
    askConfirm({
      title: `Delete version ${loaded?.version ?? ''}?`,
      message: 'It’s removed from the history and can’t be brought back. The active prompt doesn’t change.',
      action: 'Delete version',
      onConfirm: async () => {
        setBusy('delete');
        setError(null);
        try {
          await deleteVersion(type, hash);
          notify('Version deleted');
          await reloadVersions();
          await openVersion(type, 'current');
        } catch (e) {
          setError(`Not deleted: ${errorText(e)}`);
        } finally {
          setBusy(null);
        }
      },
    });
  };

  const compare = async () => {
    if (!type) return;
    if (!current) {
      try {
        setCurrent(await getVersion(type, 'current'));
      } catch (e) {
        setError(`The active version didn’t load: ${errorText(e)}`);
        return;
      }
    }
    setComparing(true);
  };

  const sorted = useMemo(
    () => [...(versions ?? [])].sort((a, b) => (a.hash === 'current' ? -1 : b.hash === 'current' ? 1 : (b.created_at ?? '').localeCompare(a.created_at ?? ''))),
    [versions],
  );
  const versionOptions = sorted.map((v) => ({ value: v.hash, label: v.hash === 'current' ? `Active (version ${v.version})` : `Version ${v.version} · ${when(v.created_at)}` }));

  if (!types) return <Skeleton variant="block" size="card" />;

  return (
    <Stack gap="lg">
      <Panel title="Prompt Engineering" description="Manage and version the prompts the AI uses. Saving makes a new version and makes it active straight away.">
        <Stack gap="md">
          {typeError && <Banner tone="error" title="Prompt types didn’t load" description={typeError} />}
          <Stack direction="row" gap="sm">
            <Select
              label="Prompt"
              placeholder="Pick a prompt"
              options={types.map((t) => ({ value: t.name, label: t.display_name }))}
              value={type || undefined}
              onValueChange={(t) => guard(() => void openType(t))}
            />
            {type && (
              <Select
                label="Version"
                options={versionOptions.length ? versionOptions : [{ value: 'current', label: 'Active' }]}
                value={hash}
                onValueChange={(h) => guard(() => void openVersion(type, h))}
                disabled={!versions || busy !== null}
              />
            )}
          </Stack>
          {error && <Banner tone="error" title="Something went wrong" description={error} action={<Button variant="secondary" size="sm" onClick={() => setError(null)}>Dismiss</Button>} />}
        </Stack>
      </Panel>

      {!type ? (
        <Panel title="Editor"><EmptyState icon="Terminal" title="No prompt picked">Pick a prompt above to read or edit it.</EmptyState></Panel>
      ) : busy === 'load' && !loaded ? <Skeleton variant="block" size="card" /> : loaded && (
        <>
          <Panel
            title={hash === 'current' ? 'Active version' : `Version ${loaded.version}`}
            description={[loaded.description, loaded.created_at ? `Saved ${when(loaded.created_at)}` : '', loaded.author ? `by ${loaded.author}` : ''].filter(Boolean).join(' · ') || undefined}
          >
            <Stack gap="md">
              {hash !== 'current' && <Banner tone="info" title="You’re looking at an older version" description="Saving from here makes these words a new active version. To switch back to this version as it is, use “Make this version active”." />}
              <TextArea label="1. Role (system prompt)" mono rows={6} value={system} onChange={setSystem} hint="Defines who the AI is meant to be for this step." />
              <TextArea
                label="2. Instructions (user prompt)"
                mono
                rows={14}
                value={instructions}
                onChange={setInstructions}
                hint="The core instructions. Use variables such as {topic}, {article_count} or {org_context}; the full list is below."
              />
              {format && (
                <Stack gap="sm">
                  <Text variant="label">3. Output format (fixed)</Text>
                  <Text variant="caption">The exact JSON the AI must return. It can’t be edited, so the pages that read the answer keep working; it’s added back on save.</Text>
                  <CodeBlock label="Output format" code={format} />
                </Stack>
              )}
              {loaded.expected_output_schema && (
                <Collapsible>
                  <CollapsibleTrigger variant="ghost" size="sm">4. JSON schema (for reference)</CollapsibleTrigger>
                  <CollapsibleContent>
                    <CodeBlock label="Expected output schema" code={JSON.stringify(loaded.expected_output_schema, null, 2)} />
                  </CollapsibleContent>
                </Collapsible>
              )}
              <Stack direction="row" gap="sm">
                <Button iconStart={<Icon name="Check" size="sm" />} busy={busy === 'save'} disabled={busy !== null || !dirty} onClick={() => void save()}>Save as a new version</Button>
                {dirty && <Button variant="ghost" disabled={busy !== null} onClick={() => void openVersion(type, hash)}>Discard edits</Button>}
                <Button variant="secondary" iconStart={<Icon name="ArrowsClockwise" size="sm" />} busy={busy === 'restore'} disabled={busy !== null || hash === 'current'} onClick={restore}>Make this version active</Button>
                <Button variant="secondary" iconStart={<Icon name="Eye" size="sm" />} disabled={busy !== null || hash === 'current'} onClick={() => void compare()}>Compare with the active version</Button>
                <Button variant="danger" iconStart={<Icon name="Trash" size="sm" />} busy={busy === 'delete'} disabled={busy !== null || hash === 'current'} onClick={remove}>Delete this version</Button>
              </Stack>
            </Stack>
          </Panel>

          {comparing && current && (
            <Panel
              title={`Version ${loaded.version} against the active version`}
              headerAside={<Button variant="ghost" size="sm" onClick={() => setComparing(false)}>Close</Button>}
            >
              <Stack gap="lg">
                <DiffView label="Role (system prompt)" before={loaded.system_prompt ?? ''} after={current.system_prompt ?? ''} beforeLabel={`Version ${loaded.version}`} afterLabel="Active" sameText="The role is the same." />
                <DiffView label="Instructions (user prompt)" before={loaded.user_prompt ?? ''} after={current.user_prompt ?? ''} beforeLabel={`Version ${loaded.version}`} afterLabel="Active" sameText="The instructions are the same." />
              </Stack>
            </Panel>
          )}

          <Grid columns={2} stackAt="wide" gap="md">
            <Panel title="Available variables" description="Written in curly brackets in the instructions, e.g. {title}. The AI step fills them in.">
              {loaded.variables && Object.keys(loaded.variables).length > 0 ? (
                <Table
                  caption="Variables for this prompt"
                  hideCaption
                  rowKey={(r) => r[0]}
                  rows={Object.entries(loaded.variables).map(([k, v]) => [k, String(v)] as [string, string])}
                  columns={[
                    { key: 'name', header: 'Variable', rowHeader: true, render: (r) => `{${r[0]}}` },
                    { key: 'what', header: 'What it holds', wrap: true, render: (r) => r[1] },
                  ]}
                />
              ) : (
                <Stack gap="md">
                  {DEFAULT_VARIABLES.map((g) => (
                    <Table
                      key={g.group}
                      caption={g.group}
                      rowKey={(r) => r[0]}
                      rows={g.vars}
                      columns={[
                        { key: 'name', header: 'Variable', rowHeader: true, render: (r) => `{${r[0]}}` },
                        { key: 'what', header: 'What it holds', wrap: true, render: (r) => r[1] },
                      ]}
                    />
                  ))}
                </Stack>
              )}
            </Panel>

            <Panel title="Version history" description="Every saved version of this prompt, newest first.">
              {!versions ? <Skeleton variant="text" lines={5} /> : (
                <Table
                  caption="Version history"
                  hideCaption
                  scroll
                  rowKey={(v) => v.hash}
                  rows={sorted}
                  emptyText="No versions saved yet."
                  columns={[
                    { key: 'version', header: 'Version', rowHeader: true, render: (v) => (v.hash === 'current' ? `${v.version} (active)` : v.version) },
                    { key: 'created_at', header: 'Saved', render: (v) => when(v.created_at) },
                    {
                      key: 'open', header: '', align: 'end',
                      render: (v) => (
                        <Button variant="ghost" size="sm" disabled={v.hash === hash || busy !== null} onClick={() => guard(() => void openVersion(type, v.hash))}>
                          {v.hash === hash ? 'Showing' : 'Open'}
                        </Button>
                      ),
                    },
                  ]}
                />
              )}
            </Panel>
          </Grid>
        </>
      )}
    </Stack>
  );
}
