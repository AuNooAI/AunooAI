import { useEffect, useState } from 'react';
import {
  Banner, Button, CodeBlock, Collapsible, CollapsibleContent, CollapsibleTrigger, Dialog, DialogClose, Eyebrow, Icon, LineItems, Panel,
  Skeleton, Stack, Table, Text, TextArea,
} from '@aunoo/ui';
import type { OrganizationalProfile } from '@monolith/api';
import { api, errorText } from '../../shell';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tabLabel: string;
  /** Backend tab id (strategic, signals…). The save endpoints accept only these; the old page sent UI ids and got a 400. */
  backendTab: string;
  topic: string;
  profile: OrganizationalProfile | undefined;
  notify: (message: string) => void;
  /** After a save: regenerate with the new prompt. */
  onSaved: () => void;
}

interface Preview {
  prompt?: string;
  template?: { system_prompt?: string; user_prompt?: string; output_format?: string; variables?: Record<string, string> | { name: string; description: string }[] };
}

const variablesOf = (v: Record<string, string> | { name: string; description: string }[] | undefined) =>
  Array.isArray(v) ? v : Object.entries(v ?? {}).map(([name, description]) => ({ name, description: String(description) }));

/** Edit this tab's prompt role and instructions; the output format is fixed so the page can render it. */
export function TuneDialog({ open, onOpenChange, tabLabel, backendTab, topic, profile, notify, onSaved }: Props) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [role, setRole] = useState('');
  const [instructions, setInstructions] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    setPreview(null);
    setError(null);
    const q = new URLSearchParams({ topic });
    if (profile?.id != null) q.set('profile_id', String(profile.id));
    api<Preview>(`/api/trend-convergence/prompt-preview/${backendTab}?${q}`).then(
      (p) => {
        setPreview(p);
        setRole(p.template?.system_prompt ?? '');
        setInstructions(p.template?.user_prompt ?? '');
      },
      (e) => setError(errorText(e)),
    );
  };
  useEffect(() => {
    if (open) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, backendTab, topic, profile?.id]);

  const save = async () => {
    setBusy(true);
    try {
      const r = await api<{ message?: string }>(`/api/trend-convergence/prompts/${backendTab}`, { method: 'POST', json: { system_prompt: role, user_prompt: instructions } });
      notify(r.message || `Prompt saved for ${tabLabel}`);
      onOpenChange(false);
      onSaved();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    setBusy(true);
    try {
      const r = await api<{ message?: string }>(`/api/trend-convergence/prompts/${backendTab}/restore-default`, { method: 'POST' });
      notify(r.message || 'Default prompt restored');
      load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  const vars = variablesOf(preview?.template?.variables);

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      title={`Tune: ${tabLabel}`}
      footer={
        <>
          <Button variant="ghost" size="lg" iconStart={<Icon name="ArrowClockwise" size="sm" />} disabled={busy} onClick={reset}>Reset to default</Button>
          <DialogClose>
            <Button variant="secondary" size="lg">Cancel</Button>
          </DialogClose>
          <Button size="lg" busy={busy} disabled={!role.trim() || !instructions.trim() || !preview} onClick={save}>Save and regenerate</Button>
        </>
      }
    >
      <Stack gap="lg">
        {error && <Banner tone="error" icon="WarningCircle" title="Something went wrong" description={error} />}
        <Panel title={profile?.name ?? 'No organisational profile'} description={profile?.organization_type} headingLevel={3}>
          {profile ? (
            <Stack gap="sm">
              <LineItems
                label="Organisation profile"
                items={[
                  ...(profile.industry ? [{ id: 'industry', label: 'Industry', amount: profile.industry }] : []),
                  ...(profile.region ? [{ id: 'region', label: 'Region', amount: profile.region }] : []),
                ]}
              />
              {/* Long lists: as text, so they wrap instead of running off a line item */}
              {profile.key_concerns?.length > 0 && <Text variant="hint"><strong>Key concerns:</strong> {profile.key_concerns.join('; ')}</Text>}
              {profile.strategic_priorities?.length > 0 && <Text variant="hint"><strong>Strategic priorities:</strong> {profile.strategic_priorities.join('; ')}</Text>}
            </Stack>
          ) : (
            <Text variant="hint">Choose a profile under Configure; prompts use it as context.</Text>
          )}
        </Panel>
        {!preview && !error ? (
          <Skeleton variant="block" />
        ) : (
          <>
            <TextArea label="1. Role" value={role} onChange={setRole} rows={4} mono />
            <TextArea label="2. Instructions" value={instructions} onChange={setInstructions} rows={10} mono hint="Use the variables listed below; they’re filled in when the analysis runs." />
            {preview?.template?.output_format && (
              <Stack gap="sm">
                <Eyebrow as="h3">3. Output format (read-only)</Eyebrow>
                <Text variant="caption">The format is fixed so the page can render the result.</Text>
                <CodeBlock label="Output format — locked" code={preview.template.output_format} />
              </Stack>
            )}
            {preview?.prompt && (
              <Collapsible>
                <Stack gap="sm">
                  <CollapsibleTrigger variant="secondary">Preview — final rendered prompt</CollapsibleTrigger>
                  <CollapsibleContent>
                    <CodeBlock label="Rendered prompt" code={preview.prompt} />
                  </CollapsibleContent>
                </Stack>
              </Collapsible>
            )}
            {vars.length > 0 && (
              <Table caption="Available variables" rowKey={(v) => v.name} rows={vars} columns={[{ key: 'name', header: 'Variable', rowHeader: true }, { key: 'description', header: 'Filled with', wrap: true }]} />
            )}
          </>
        )}
      </Stack>
    </Dialog>
  );
}
