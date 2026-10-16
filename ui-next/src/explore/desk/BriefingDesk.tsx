import { useCallback, useEffect, useState } from 'react';
import { Banner, Button, EmptyState, Icon, IconButton, Panel, Skeleton, Stack } from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import {
  deleteBriefing, downloadBriefing, downloadBriefingPdf, fetchBriefing, fetchBriefings, finalizeBriefing, removeArticleFromBriefing,
  removeEmergingTopicFromBriefing, removeIncidentFromBriefing, reopenBriefing, updateBriefingPriorityActions, updateBriefingSynthesis,
  updateBriefingThemes,
  type BriefingAction, type BriefingSummary, type BriefingTheme, type DeskBriefing, type FinalizeProgressEvent,
} from '@monolith/briefingDeskApi';
import { loadDeployedModelNames } from '@monolith/aiDisclosureModels';
import { errorText } from '../../shell';
import { BriefingDetail } from './tab/BriefingDetail';
import { BriefingList } from './tab/BriefingList';
import { ComposeDialog } from './tab/ComposeDialog';
import { CreateDialog } from './tab/CreateDialog';

/*
 * The Briefing Desk, on the routes the old tab uses (/api/desk-briefings, see
 * ui/src/components/newsfeed/BriefingDeskSection.tsx). A briefing is a curated set of articles,
 * incidents and emerging themes, added from the other tabs with "Add to briefing", plus a written
 * summary, themes and actions. The reader writes those, or has the AI write them ("Write with AI");
 * an AI reviewer then checks them against the sources and can hold the briefing as a draft.
 * Composing today's briefing and writing with AI are the only AI calls, and both are buttons.
 */

export interface BriefingDeskProps {
  /** Model, organisational profile name and persona picked in the Explore filter bar */
  model: string;
  profileName?: string;
  persona: string;
  notify: (m: string) => void;
  askConfirm: (c: Confirm) => void;
}

export function BriefingDesk({ model, profileName, persona, notify, askConfirm }: BriefingDeskProps) {
  const [briefings, setBriefings] = useState<BriefingSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<DeskBriefing | null>(null);
  const [opening, setOpening] = useState<number | null>(null);
  const [dialog, setDialog] = useState<null | 'create' | 'compose'>(null);
  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState<FinalizeProgressEvent | null>(null);
  const [modelNames, setModelNames] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setBriefings(await fetchBriefings());
    } catch (e) {
      setBriefings((b) => b ?? []);
      setError(`Briefings didn’t load: ${errorText(e)}`);
    }
  }, []);
  useEffect(() => {
    void load();
    // The models this site actually ran, for the disclosure under a summary
    loadDeployedModelNames().then(setModelNames, () => undefined);
  }, [load]);
  // The Explore filter bar's Refresh button
  useEffect(() => {
    const onRefresh = () => void load();
    window.addEventListener('explore:refresh', onRefresh);
    return () => window.removeEventListener('explore:refresh', onRefresh);
  }, [load]);

  const open = async (id: number) => {
    setOpening(id);
    try {
      setSelected(await fetchBriefing(id));
    } catch (e) {
      notify(`The briefing didn’t open: ${errorText(e)}`);
    } finally {
      setOpening(null);
    }
  };
  const reloadSelected = async (id: number) => {
    setSelected(await fetchBriefing(id));
    void load();
  };

  // Runs a write against the open briefing, then reloads it; a failure says what failed
  const act = async (what: string, fn: (id: number) => Promise<unknown>) => {
    if (!selected) return;
    try {
      await fn(selected.id);
      await reloadSelected(selected.id);
    } catch (e) {
      notify(`${what} failed: ${errorText(e)}`);
    }
  };
  // Editor saves rethrow, so the editor stays open on a failure
  const save = (fn: (id: number) => Promise<unknown>) => async () => {
    if (!selected) return;
    await fn(selected.id);
    await reloadSelected(selected.id);
  };

  const remove = (b: { id: number; name: string }) =>
    askConfirm({
      title: `Delete “${b.name}”?`,
      message: 'The briefing and its summary are deleted. The articles, incidents and themes in it stay where they were.',
      action: 'Delete briefing',
      onConfirm: () => {
        deleteBriefing(b.id).then(
          () => {
            if (selected?.id === b.id) setSelected(null);
            notify(`Deleted “${b.name}”`);
            void load();
          },
          (e) => notify(`Not deleted: ${errorText(e)}`),
        );
      },
    });

  const runGenerate = async () => {
    if (!selected) return;
    const id = selected.id;
    setGenerating(true);
    setProgress(null);
    try {
      await finalizeBriefing(id, model || 'claude-sonnet-5-5', setProgress, { organizational_profile: profileName, persona });
      await reloadSelected(id);
    } catch (e) {
      notify(`Writing stopped: ${errorText(e)}`);
      void reloadSelected(id).catch(() => undefined);
    } finally {
      setGenerating(false);
      setProgress(null);
    }
  };
  // Writing again replaces the summary, themes and actions, hand edits included, so it asks first
  const generate = () => {
    if (!selected) return;
    const hasText = Boolean(selected.synthesis || selected.themes?.length || selected.priority_actions?.length);
    if (!hasText) {
      void runGenerate();
      return;
    }
    askConfirm({
      title: 'Write the summary again with AI?',
      message: 'The AI rewrites the executive summary, key themes and priority actions from the items in this briefing. The current text, including any edits you made, is replaced and not kept.',
      action: 'Write it again',
      onConfirm: () => void runGenerate(),
    });
  };
  const override = (note: string) =>
    void act('Finalizing', (id) => finalizeBriefing(id, model || 'claude-sonnet-5-5', () => undefined, { override_review: true, override_note: note }));

  const exportAs = (format: 'pdf' | 'markdown' | 'html' | 'json') => {
    if (!selected) return;
    const p = format === 'pdf' ? downloadBriefingPdf(selected.id, selected.name) : downloadBriefing(selected.id, selected.name, format);
    p.catch((e: unknown) => notify(`Download failed: ${errorText(e)}`));
  };

  if (selected) {
    return (
      <BriefingDetail
        briefing={selected}
        modelNames={modelNames}
        generating={generating}
        progress={progress}
        onBack={() => setSelected(null)}
        onGenerate={generate}
        onOverride={override}
        onReopen={() => void act('Reopening', reopenBriefing)}
        onExport={exportAs}
        onDelete={() => remove(selected)}
        onRemoveArticle={(uri) => void act('Removing the article', (id) => removeArticleFromBriefing(id, uri))}
        onRemoveIncident={(name) => void act('Removing the incident', (id) => removeIncidentFromBriefing(id, name))}
        onRemoveTopic={(name) => void act('Removing the theme', (id) => removeEmergingTopicFromBriefing(id, name))}
        onSaveSummary={(v: string) => save((id) => updateBriefingSynthesis(id, v))()}
        onSaveThemes={(v: BriefingTheme[]) => save((id) => updateBriefingThemes(id, v))()}
        onSaveActions={(v: BriefingAction[]) => save((id) => updateBriefingPriorityActions(id, v))()}
        notify={notify}
      />
    );
  }

  return (
    <>
      <Panel
        title="Briefing Desk"
        description={briefings ? `${briefings.length} briefing${briefings.length === 1 ? '' : 's'}. Collect articles, incidents and emerging themes with “Add to briefing” on the other tabs, then write them up here.` : undefined}
        headerAside={
          <Stack direction="row" gap="sm">
            <Button iconStart={<Icon name="Sparkle" size="sm" />} onClick={() => setDialog('compose')}>Compose today’s briefing</Button>
            <Button variant="secondary" iconStart={<Icon name="Plus" size="sm" />} onClick={() => setDialog('create')}>New briefing</Button>
            <IconButton icon={<Icon name="ArrowClockwise" size="sm" />} label="Reload briefings" onClick={() => void load()} />
          </Stack>
        }
      />
      {error && <Banner tone="error" title="Something went wrong" description={error} action={<Button variant="secondary" size="sm" onClick={() => void load()}>Try again</Button>} />}
      {!briefings ? (
        <Skeleton variant="block" size="card" />
      ) : briefings.length === 0 && !error ? (
        <Panel title="No briefings yet">
          <EmptyState
            icon="Newspaper"
            title="Start a briefing"
            action={<Button iconStart={<Icon name="Plus" size="sm" />} onClick={() => setDialog('create')}>Create your first briefing</Button>}
          >
            Create an empty one and fill it from the other tabs, or compose today’s from your topics with the AI.
          </EmptyState>
        </Panel>
      ) : (
        <BriefingList briefings={briefings} onOpen={(id) => void open(id)} onDelete={remove} busyId={opening} />
      )}

      <CreateDialog open={dialog === 'create'} onOpenChange={(o) => setDialog(o ? 'create' : null)} onCreated={() => { notify('Briefing created'); void load(); }} />
      <ComposeDialog
        open={dialog === 'compose'}
        onOpenChange={(o) => setDialog(o ? 'compose' : null)}
        model={model}
        onComposed={(id) => { notify('Today’s briefing is ready to curate'); void load(); void open(id); }}
      />
    </>
  );
}
