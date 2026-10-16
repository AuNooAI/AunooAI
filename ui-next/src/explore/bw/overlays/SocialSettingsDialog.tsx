import { useEffect, useMemo, useState } from 'react';
import { Banner, Button, Dialog, DialogClose, Skeleton, Stack, Text } from '@aunoo/ui';
import type { Confirm } from '@aunoo/shell';
import * as g from '@monolith/gatherApi';
import type { AvailableModel, AvailableProvider } from '@monolith/gatherApi';
import { setupSocialMonitoring, type Brand } from '@monolith/brandWatcherApi';
import { errorText } from '../../../shell';
import { GroupSettingsDialog } from '../../../gather/overlays/GroupSettingsDialog';
import { modelOptions, toCollectSettings, type CollectSettings, type KeywordGroup } from '../../../gather/model';

/*
 * Social settings for the picked brand: the platforms its "{Brand} - Social" keyword group collects
 * from (each platform costs provider credits) and how often. A dedicated Brand Watcher site has no
 * Gather page, so the old tab offered Gather's group settings here; this opens the same dialog the
 * new Gather page uses (gather/overlays/GroupSettingsDialog.tsx), loaded only when asked for.
 */

type Load =
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'missing' }
  | { state: 'ready'; group: KeywordGroup; global: CollectSettings; providers: AvailableProvider[]; models: AvailableModel[] };

export function SocialSettingsDialog({ brand, open, onClose, notify, askConfirm, onChanged }: {
  brand: Brand | null;
  open: boolean;
  onClose: () => void;
  notify: (m: string) => void;
  askConfirm: (c: Confirm) => void;
  /** After social monitoring is set up or its settings are saved */
  onChanged?: () => void;
}) {
  const [load, setLoad] = useState<Load>({ state: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const [settingUp, setSettingUp] = useState(false);
  const groupName = brand ? `${brand.display_name} - Social` : '';

  useEffect(() => {
    if (!open || !brand) return;
    let alive = true;
    setLoad({ state: 'loading' });
    Promise.all([g.getGroupSummaries(), g.getSettings(), g.getAvailableProviders().catch(() => []), g.getAvailableModels().catch(() => [])]).then(
      ([groups, settings, providers, models]) => {
        if (!alive) return;
        const match = groups.find((x) => x.name === groupName);
        if (!match) return setLoad({ state: 'missing' });
        // The settings dialog only reads the group's id and name
        const group = { id: String(match.id), name: match.name, topic: match.topic } as KeywordGroup;
        setLoad({ state: 'ready', group, global: toCollectSettings(settings), providers, models });
      },
      (e) => alive && setLoad({ state: 'error', message: errorText(e) }),
    );
    return () => {
      alive = false;
    };
  }, [open, brand, groupName, attempt]);

  const models = useMemo(() => (load.state === 'ready' ? modelOptions(load.models, load.global.model ?? '') : []), [load]);

  const setUp = () => {
    if (!brand) return;
    askConfirm({
      title: `Set up social monitoring for ${brand.display_name}?`,
      message: 'This creates a keyword group that collects posts about the brand from X, Bluesky, Reddit, Instagram and TikTok every 24 hours. Each collection uses provider credits; you can switch platforms off in these settings afterwards.',
      action: 'Set up',
      onConfirm: async () => {
        setSettingUp(true);
        try {
          const r = await setupSocialMonitoring(brand.id, 24);
          notify(`Social monitoring ${r.created ? 'on' : 'updated'}: “${r.group_name}”, ${r.keywords_added} keywords, collected every ${r.interval_hours} hours.`);
          onChanged?.();
          setAttempt((a) => a + 1);
        } catch (e) {
          notify(`Not set up: ${errorText(e)}`);
        } finally {
          setSettingUp(false);
        }
      },
    });
  };

  if (!open) return null;
  if (load.state === 'ready') {
    return (
      <GroupSettingsDialog
        group={load.group}
        onClose={onClose}
        global={load.global}
        providers={load.providers}
        models={models}
        onSaved={() => {
          notify('Social settings saved');
          onChanged?.();
        }}
      />
    );
  }
  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={`Social settings${brand ? `: ${brand.display_name}` : ''}`}
      description="Which networks this brand’s posts are collected from, and how often."
      footer={<DialogClose><Button variant="secondary" size="lg">Close</Button></DialogClose>}
    >
      {!brand ? (
        <Text>Pick one brand in the header first.</Text>
      ) : load.state === 'loading' ? (
        <Skeleton variant="text" lines={4} />
      ) : load.state === 'error' ? (
        <Banner tone="error" title="The settings didn’t load" description={load.message} action={<Button variant="secondary" size="sm" onClick={() => setAttempt((a) => a + 1)}>Try again</Button>} />
      ) : (
        <Stack gap="md">
          <Text>{brand.display_name} has no social monitoring yet, so there is nothing to set. Setting it up creates the “{groupName}” keyword group.</Text>
          <div><Button busy={settingUp} disabled={settingUp} onClick={setUp}>Set up social monitoring</Button></div>
        </Stack>
      )}
    </Dialog>
  );
}
