import { useEffect, useState } from 'react';
import { ActivityRow, Banner, Button, Checkbox, Dialog, DialogClose, EmptyState, Skeleton, Stack, Text } from '@aunoo/ui';
import { fetchComposeConfig, saveComposeConfig, streamComposeDailyBriefing, type ComposeProgressEvent } from '@monolith/briefingDeskApi';
import { errorText } from '../../../shell';

/*
 * "Compose today's briefing", as the old Briefing Desk: creates a draft, runs Emerging Topics
 * detection for each picked topic and stages the strongest themes and the most relevant news for the
 * reader to curate. It calls the AI for every topic, so it runs only from the Compose button.
 */

const STAGES = ['create', 'gather', 'emerging', 'incidents', 'curate', 'stage', 'complete'];

export function ComposeDialog({ open, onOpenChange, model, onComposed }: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  model: string;
  onComposed: (briefingId: number) => void;
}) {
  const [topics, setTopics] = useState<{ name: string; description?: string }[] | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [composing, setComposing] = useState(false);
  const [log, setLog] = useState<ComposeProgressEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setTopics(null);
    setSaved(false);
    setError(null);
    setLog([]);
    fetchComposeConfig().then(
      (cfg) => {
        setTopics(cfg.available_topics);
        setPicked(cfg.selected_topics);
      },
      (e) => {
        setTopics([]);
        setError(`Topics didn’t load: ${errorText(e)}`);
      },
    );
  }, [open]);

  const toggle = (name: string, on: boolean) => {
    setSaved(false);
    setPicked((p) => (on ? [...p, name] : p.filter((t) => t !== name)));
  };

  const saveDefault = async () => {
    setSaving(true);
    setError(null);
    try {
      await saveComposeConfig(picked);
      setSaved(true);
    } catch (e) {
      setError(`Not saved: ${errorText(e)}`);
    } finally {
      setSaving(false);
    }
  };

  const compose = async () => {
    setComposing(true);
    setError(null);
    setLog([]);
    // Remember the selection for next time; compose still runs if this fails
    saveComposeConfig(picked).catch(() => undefined);
    try {
      const final = await streamComposeDailyBriefing(picked.length ? picked : undefined, model ? { model } : undefined, (evt) =>
        setLog((prev) => [...prev.filter((e) => e.stage !== evt.stage), evt]),
      );
      if (final?.briefing_id) {
        onOpenChange(false);
        onComposed(final.briefing_id);
      } else {
        setError('Composing finished without a briefing. Check the steps above for the one that stopped.');
      }
    } catch (e) {
      setError(`Composing stopped: ${errorText(e)}`);
    } finally {
      setComposing(false);
    }
  };

  const steps = STAGES.map((s) => log.find((e) => e.stage === s)).filter((e): e is ComposeProgressEvent => Boolean(e));

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => !composing && onOpenChange(o)}
      title="Compose today’s briefing"
      description="Creates a draft, runs Emerging Topics detection on each topic you pick, and stages the strongest themes and the most relevant news for you to curate. The AI reads each topic, which takes a minute or two per topic and costs about the same as a detection run."
      footer={
        <>
          <DialogClose><Button variant="secondary" size="lg" disabled={composing}>Cancel</Button></DialogClose>
          <Button size="lg" busy={composing} disabled={composing || picked.length === 0} onClick={() => void compose()}>
            {composing ? 'Composing…' : `Compose from ${picked.length} topic${picked.length === 1 ? '' : 's'}`}
          </Button>
        </>
      }
    >
      <Stack gap="md">
        {error && <Banner tone="error" title="Something went wrong" description={error} />}
        {composing || steps.length > 0 ? (
          <Stack as="ul" gap="sm" label="Progress">
            {steps.map((e) => {
              const done = e.status === 'completed' || e.stage === 'complete';
              return (
                <ActivityRow
                  key={e.stage}
                  as="li"
                  primary={`${e.message ?? e.stage}${e.fallback ? ' (rule-based fallback, not the AI)' : ''}`}
                  dotTone={done ? 'live' : 'pending'}
                  dotLabel={done ? 'Done' : 'Running'}
                />
              );
            })}
            {composing && <li><Text variant="caption">Detecting and curating can take a minute or two per topic.</Text></li>}
          </Stack>
        ) : !topics ? (
          <Skeleton variant="text" lines={5} />
        ) : topics.length === 0 ? (
          <EmptyState icon="Tag" title="No topics set up">Add a topic first; the briefing is composed from your topics.</EmptyState>
        ) : (
          <Stack gap="sm">
            <Stack direction="row" justify="between" gap="sm">
              <Text variant="label" as="span">{`Topics (${picked.length} picked)`}</Text>
              <Stack direction="row" gap="sm">
                <Button variant="ghost" size="sm" onClick={() => { setSaved(false); setPicked(topics.map((t) => t.name)); }}>Pick all</Button>
                <Button variant="ghost" size="sm" onClick={() => { setSaved(false); setPicked([]); }}>Clear</Button>
              </Stack>
            </Stack>
            <div>
              {topics.map((t) => (
                <Checkbox key={t.name} label={t.description ? `${t.name}: ${t.description}` : t.name} checked={picked.includes(t.name)} onCheckedChange={(on) => toggle(t.name, on)} />
              ))}
            </div>
            <div>
              <Button variant="ghost" size="sm" busy={saving} disabled={saving} onClick={() => void saveDefault()}>
                {saved ? 'Saved as the default' : 'Save this selection as the default'}
              </Button>
            </div>
          </Stack>
        )}
      </Stack>
    </Dialog>
  );
}
